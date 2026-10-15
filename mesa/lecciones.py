"""Lecciones aprendidas entre historias.

Es la forma práctica de "afinar" la siguiente historia sin reentrenar un modelo:
cada lección es una instrucción corta, con evidencia de dónde salió, que
`mesa contexto` inyecta al director al empezar cualquier partida.

Alcances:
  global               vale para cualquier historia y cualquier mesa
  jugadores            preferencias de este grupo de jugadores
  reglas:<ruleset>     ajustes a un reglamento concreto (p. ej. reglas:d20-simple)
  ambientacion:<tag>   solo para historias con esa etiqueta (p. ej. ambientacion:rusia-1917)

Estados: activa (se inyecta), retirada (dejó de valer) e incorporada (ya la dice AGENTS.md u
otro documento que el director lee siempre: repetirla solo mete ruido).
Fase opcional: «sesion-cero» solo se inyecta mientras la partida no ha jugado ninguna escena.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import estado

CATEGORIAS = ("agencia", "ritmo", "reglas", "dados", "tono", "formato", "mundo", "pnj", "seguridad", "visor")
FASES = ("sesion-cero",)


def ruta() -> Path:
    return estado.RAIZ / "lecciones" / "lecciones.jsonl"


def leer() -> list[dict]:
    if not ruta().exists():
        return []
    return [json.loads(l) for l in ruta().read_text(encoding="utf-8").splitlines() if l.strip()]


def _escribir(items: list[dict]) -> None:
    ruta().parent.mkdir(parents=True, exist_ok=True)
    ruta().write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")


def agregar(texto: str, alcance: str, categoria: str, evidencia: str, origen: str = "", fase: str | None = None) -> dict:
    if fase is not None and fase not in FASES:
        raise ValueError(f"fase desconocida: {fase} (usa: {', '.join(FASES)})")
    if categoria not in CATEGORIAS:
        raise ValueError(f"categoría desconocida: {categoria} (usa: {', '.join(CATEGORIAS)})")
    if not (alcance in ("global", "jugadores") or alcance.startswith(("reglas:", "ambientacion:"))):
        raise ValueError("alcance: global | jugadores | reglas:<ruleset> | ambientacion:<etiqueta>")
    items = leer()
    numero = max((int(i["id"][1:]) for i in items), default=0) + 1
    item = {
        "id": f"L{numero:03d}",
        "alcance": alcance,
        "categoria": categoria,
        "leccion": texto,
        "evidencia": evidencia,
        "origen": origen,
        "estado": "activa",
        "fecha": date.today().isoformat(),
        **({"fase": fase} if fase else {}),
    }
    _escribir(items + [item])
    return item


def _cambiar(id_: str, cambio) -> dict:
    items = leer()
    for item in items:
        if item["id"] == id_.upper():
            cambio(item)
            _escribir(items)
            return item
    raise ValueError(f"no existe la lección {id_}")


def retirar(id_: str, motivo: str) -> dict:
    return _cambiar(id_, lambda i: i.update(estado="retirada", motivo_retiro=motivo))


def incorporar(id_: str, donde: str) -> dict:
    """La lección ya está escrita donde el director la lee siempre: deja de inyectarse."""
    return _cambiar(id_, lambda i: i.update(estado="incorporada", incorporada_en=donde))


def fijar_fase(id_: str, fase: str) -> dict:
    """`sesion-cero` la limita a partidas sin escenas jugadas; `siempre` quita la fase."""
    if fase not in FASES + ("siempre",):
        raise ValueError(f"fase desconocida: {fase} (usa: {', '.join(FASES + ('siempre',))})")
    return _cambiar(id_, lambda i: i.pop("fase", None) if fase == "siempre" else i.update(fase=fase))


def aplicables(partida: dict | None = None) -> list[dict]:
    """Lecciones activas que corresponden a una partida (o todas las globales si no hay)."""
    alcances = {"global", "jugadores"}
    en_juego = False
    if partida:
        alcances.add(f"reglas:{partida.get('reglamento', 'd20-simple')}")
        alcances.update(f"ambientacion:{t}" for t in partida.get("ambientacion", {}).get("etiquetas", []))
        en_juego = int(partida.get("escenas_jugadas", 0)) > 0
    return [
        i for i in leer()
        if i["estado"] == "activa" and i["alcance"] in alcances and not (en_juego and i.get("fase") == "sesion-cero")
    ]


def como_markdown(items: list[dict]) -> str:
    if not items:
        return "_(sin lecciones)_\n"
    lineas = []
    for categoria in CATEGORIAS:
        grupo = [i for i in items if i["categoria"] == categoria]
        if not grupo:
            continue
        lineas.append(f"### {categoria.capitalize()}")
        for i in grupo:
            notas = [i["fase"]] if i.get("fase") else []
            if i["estado"] == "incorporada":
                notas.append(f"incorporada en {i.get('incorporada_en', '?')}")
            elif i["estado"] == "retirada":
                notas.append(f"retirada: {i.get('motivo_retiro', '')}")
            lineas.append(f"- **{i['id']}** ({', '.join([i['alcance'], *notas])}): {i['leccion']}")
        lineas.append("")
    return "\n".join(lineas)

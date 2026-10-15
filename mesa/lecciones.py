"""Lecciones aprendidas entre historias.

Es la forma práctica de "afinar" la siguiente historia sin reentrenar un modelo:
cada lección es una instrucción corta, con evidencia de dónde salió, que
`mesa contexto` inyecta al director al empezar cualquier partida.

Alcances:
  global               vale para cualquier historia y cualquier mesa
  jugadores            preferencias de este grupo de jugadores
  reglas:<ruleset>     ajustes a un reglamento concreto (p. ej. reglas:d20-simple)
  ambientacion:<tag>   solo para historias con esa etiqueta (p. ej. ambientacion:rusia-1917)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import estado

CATEGORIAS = ("agencia", "ritmo", "reglas", "dados", "tono", "formato", "mundo", "pnj", "seguridad", "visor")


def ruta() -> Path:
    return estado.RAIZ / "lecciones" / "lecciones.jsonl"


def leer() -> list[dict]:
    if not ruta().exists():
        return []
    return [json.loads(l) for l in ruta().read_text(encoding="utf-8").splitlines() if l.strip()]


def _escribir(items: list[dict]) -> None:
    ruta().parent.mkdir(parents=True, exist_ok=True)
    ruta().write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")


def agregar(texto: str, alcance: str, categoria: str, evidencia: str, origen: str = "") -> dict:
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
    }
    _escribir(items + [item])
    return item


def retirar(id_: str, motivo: str) -> dict:
    items = leer()
    for item in items:
        if item["id"] == id_:
            item["estado"] = "retirada"
            item["motivo_retiro"] = motivo
            _escribir(items)
            return item
    raise ValueError(f"no existe la lección {id_}")


def aplicables(partida: dict | None = None) -> list[dict]:
    """Lecciones activas que corresponden a una partida (o todas las globales si no hay)."""
    alcances = {"global", "jugadores"}
    if partida:
        alcances.add(f"reglas:{partida.get('reglamento', 'd20-simple')}")
        alcances.update(f"ambientacion:{t}" for t in partida.get("ambientacion", {}).get("etiquetas", []))
    return [i for i in leer() if i["estado"] == "activa" and i["alcance"] in alcances]


def como_markdown(items: list[dict]) -> str:
    if not items:
        return "_(sin lecciones)_\n"
    lineas = []
    for categoria in CATEGORIAS:
        grupo = [i for i in items if i["categoria"] == categoria]
        if not grupo:
            continue
        lineas.append(f"### {categoria.capitalize()}")
        lineas += [f"- **{i['id']}** ({i['alcance']}): {i['leccion']}" for i in grupo]
        lineas.append("")
    return "\n".join(lineas)

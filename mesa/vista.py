"""Lo que ven los jugadores: la partida filtrada por lo que sus personajes saben.

`partida.json` guarda la verdad de la mesa; el visor (y cualquiera que lea su API)
recibe esta proyección:

- Los PJ que juega una persona (todos salvo los que tienen `piloto: narrador`) se ven
  enteros: sus estadísticas son de la mesa.
- Los demás (enemigos, PNJ y PJ que pilota el narrador) muestran solo lo que se sabe por
  el lore. Sin `conocido`, su nombre real se cambia por su `apariencia_publica` (o
  «Figura desconocida», numerada si hay varias) en el estado, la zona, la bitácora y lo
  que escribe el narrador en el chat. Sin `revelar_stats` no viajan ni vida, ni CA, ni
  ataque, ni daño, ni modificadores: solo un estado aparente («herido»), que se ve a
  simple vista.

Los enemigos son desconocidos hasta que el narrador los revela (`enemigo revelar`); los
PNJ y los PJ, conocidos salvo `conocido: false`. La terminal del narrador no pasa por
aquí: la proyección protege el visor, que es lo que se comparte.
"""

from __future__ import annotations

import copy
import re

from .texto import norm

ALIAS_POR_DEFECTO = "Figura desconocida"

# Mecánica que no se ve a simple vista: se quita a quien no tiene `revelar_stats`.
STATS = (
    "vida", "vida_max", "vida_temporal", "defensa", "ca", "ataque", "dano", "tipo_dano", "proteccion",
    "atributos", "competencias", "competencia_bono", "nivel", "resistencias", "inmunidades",
    "vulnerabilidades", "salvaciones_muerte", "dados_golpe", "habilidades", "rasgos", "conjuros",
    "espacios_conjuro", "atributo_conjuro", "concentracion", "monedas", "inspiracion",
)
# Lo que delata quién es: se quita a quien no es conocido.
IDENTIDAD = ("id", "rol", "clase", "bueno_para", "personalidad", "notas", "nota", "conocido_por")


def humano(ficha: dict) -> bool:
    """¿Lo juega una persona? Todos los PJ salvo los que pilota el narrador (regla de la casa)."""
    return ficha.get("piloto") != "narrador"


def politica(datos: dict) -> dict:
    """Quién se ve con otro nombre (`alias`) y a quién no se le ven las estadísticas (`sin_stats`)."""
    alias: dict[str, str] = {}
    sin_stats: set[str] = set()
    usados: dict[str, int] = {}
    grupos = (
        (datos.get("enemigos") or [], False),
        (datos.get("pnj") or [], True),
        ([p for p in datos.get("personajes") or [] if not humano(p)], True),
    )
    for lista, conocido_por_defecto in grupos:
        for ficha in lista:
            nombre = str(ficha.get("nombre") or "")
            if not nombre:
                continue
            conocido = ficha.get("conocido")
            if not (conocido_por_defecto if conocido is None else conocido):
                base = str(ficha.get("apariencia_publica") or "").strip() or ALIAS_POR_DEFECTO
                usados[base] = usados.get(base, 0) + 1
                alias[nombre] = base if usados[base] == 1 else f"{base} {usados[base]}"
            if not ficha.get("revelar_stats"):
                sin_stats.add(nombre)
    # Quien salió de escena sin revelarse sigue oculto en la bitácora vieja (`enemigo quitar` lo anota).
    presentes = {str(f.get("nombre") or "") for lista, _ in grupos for f in lista}
    for real, guardado in (datos.get("identidades_ocultas") or {}).items():
        if real not in presentes and real not in alias:
            alias[real] = str(guardado)
            sin_stats.add(real)
    patron = None
    if alias:
        nombres = sorted(alias, key=len, reverse=True)
        patron = re.compile("|".join(rf"(?<!\w){re.escape(n)}(?!\w)" for n in nombres))
    return {
        "alias": alias,
        "alias_norm": {norm(k): v for k, v in alias.items()},
        "reales": {v: k for k, v in alias.items()},
        "sin_stats": sin_stats,
        "sin_stats_norm": {norm(n) for n in sin_stats},
        "patron": patron,
    }


def nombre_publico(pol: dict, nombre):
    """El nombre con el que los jugadores conocen a alguien (exacto o sin tildes ni mayúsculas)."""
    if not isinstance(nombre, str):
        return nombre
    return pol["alias"].get(nombre) or pol["alias_norm"].get(norm(nombre)) or nombre


def nombre_real(pol: dict, nombre: str | None) -> str | None:
    """Del nombre público al real, para que el motor resuelva lo que el visor pide."""
    return pol["reales"].get(nombre, nombre) if isinstance(nombre, str) else nombre


def oculto(pol: dict, nombre) -> bool:
    return isinstance(nombre, str) and (nombre in pol["sin_stats"] or norm(nombre) in pol["sin_stats_norm"])


def texto(pol: dict, s):
    """Cambia en un texto los nombres reales de quien no es conocido por su alias."""
    if not isinstance(s, str) or pol["patron"] is None:
        return s
    return pol["patron"].sub(lambda m: pol["alias"][m.group(0)], s)


def estado_aparente(ficha: dict) -> str:
    """Lo que se ve a simple vista de cómo está alguien, sin cifras."""
    if ficha.get("muerto"):
        return "muerto"
    try:
        vida = int(ficha.get("vida", 0))
        maximo = int(ficha.get("vida_max", ficha.get("vida", 0)) or 0)
    except (TypeError, ValueError):
        return "presente"
    if vida <= 0:
        return "fuera de combate"
    if not maximo or vida >= maximo:
        return "ileso"
    proporcion = vida / maximo
    return "herida leve" if proporcion > 0.5 else "herido" if proporcion > 0.25 else "grave"


def _estado_desde_cambio(vida: dict) -> str | None:
    if not isinstance(vida, dict) or "despues" not in vida:
        return None
    return estado_aparente({"vida": vida.get("despues"), "vida_max": vida.get("maximo")})


def _reemplazar(pol: dict, x):
    if isinstance(x, str):
        return texto(pol, x)
    if isinstance(x, list):
        return [_reemplazar(pol, v) for v in x]
    if isinstance(x, dict):
        return {(texto(pol, k) if isinstance(k, str) else k): _reemplazar(pol, v) for k, v in x.items()}
    return x


def _sin_vida(d: dict) -> None:
    estado = _estado_desde_cambio(d.pop("vida", None))
    d.pop("proteccion", None)
    if estado:
        d["estado"] = estado


def _entrada_iniciativa(pol: dict, x: dict) -> dict:
    if not oculto(pol, x.get("quien")):
        return x
    return {"quien": x.get("quien"), "oculto": True}


def evento(pol: dict, e: dict) -> dict:
    """Un evento de la bitácora como lo ven los jugadores."""
    e = copy.deepcopy(e)
    tipo, quien, objetivo = e.get("tipo"), e.get("quien"), e.get("objetivo")
    if tipo in ("prueba", "ataque") and oculto(pol, quien):
        e.update(partes=[], modificador=None, total=None, margen=None, redactado=True)
        if isinstance(e.get("dano"), dict):
            e["dano"].update(bonus_mod=None, fuente_mod=None)
            if isinstance(e["dano"].get("tirada"), dict):
                e["dano"]["tirada"]["expr"] = None
    if tipo in ("ataque", "dano") and oculto(pol, objetivo):
        if tipo == "ataque":
            e["cd"] = None
        for clave in ("dano", "dano_maestria"):
            if isinstance(e.get(clave), dict):
                _sin_vida(e[clave])
        if tipo == "dano":
            _sin_vida(e)
    if tipo == "dano" and oculto(pol, quien):
        e.update(expr=None, modificador=None)
    if tipo in ("vida", "vida_temporal", "vendaje") and oculto(pol, quien):
        estado = _estado_desde_cambio(e)
        for clave in ("antes", "despues", "maximo", "delta", "cantidad", "temporal_antes", "temporal_despues", "absorbido_temporal"):
            e.pop(clave, None)
        e["redactado"] = True
        if estado:
            e["estado"] = estado
    if tipo == "iniciativa":
        e["orden"] = [_entrada_iniciativa(pol, x) for x in e.get("orden") or [] if isinstance(x, dict)]
    if tipo == "conjuro":
        for r in e.get("resultados_objetivos") or []:
            if oculto(pol, r.get("objetivo")):
                _sin_vida(r)
                if isinstance(r.get("salvacion"), dict):
                    r["salvacion"] = evento(pol, r["salvacion"])
    return _reemplazar(pol, e)


def eventos(datos: dict, lista: list[dict], pol: dict | None = None) -> list[dict]:
    pol = pol or politica(datos)
    return [evento(pol, e) for e in lista]


def partida(datos: dict, pol: dict | None = None) -> dict:
    """El estado de la partida como lo ven los jugadores."""
    pol = pol or politica(datos)
    d = copy.deepcopy(datos)
    d.pop("identidades_ocultas", None)  # nombres reales de quien salió sin revelarse
    for clave in ("enemigos", "pnj", "personajes"):
        for ficha in d.get(clave) or []:
            nombre = ficha.get("nombre")
            if clave == "personajes" and humano(ficha):
                continue
            if nombre in pol["sin_stats"]:
                ficha["estado_aparente"] = estado_aparente(ficha)
                for campo in STATS:
                    ficha.pop(campo, None)
                if isinstance(ficha.get("armas"), list):
                    ficha["armas"] = [{"nombre": a.get("nombre")} for a in ficha["armas"] if isinstance(a, dict)]
                if isinstance(ficha.get("equipo"), list):
                    ficha["equipo"] = [{"nombre": x.get("nombre"), "equipado": True} for x in ficha["equipo"] if isinstance(x, dict) and x.get("equipado")]
            if nombre in pol["alias"]:
                ficha["nombre"] = pol["alias"][nombre]
                ficha["conocido"] = False
                for campo in IDENTIDAD:
                    ficha.pop(campo, None)
    escena = d.get("escena") or {}
    for pos in escena.get("posiciones") or []:
        pos["quien"] = nombre_publico(pol, pos.get("quien"))
        pos["donde"] = texto(pol, pos.get("donde"))
    combate = d.get("combate") or {}
    if isinstance(combate.get("orden_iniciativa"), list):
        combate["orden_iniciativa"] = [
            {**x, "quien": nombre_publico(pol, x.get("quien"))} for x in
            (_entrada_iniciativa(pol, x) for x in combate["orden_iniciativa"] if isinstance(x, dict))
        ]
    return d


def zona(proyeccion: dict, pol: dict) -> dict:
    """La proyección táctica con los nombres públicos: el motor ya resolvió con los reales."""
    p = copy.deepcopy(proyeccion)
    for f in p.get("fichas") or []:
        real = f.get("quien")
        if nombre_publico(pol, real) != real:
            f.update(quien=nombre_publico(pol, real), marca="?", clase="otro")
        f["donde"] = texto(pol, f.get("donde"))
    if isinstance(p.get("origen"), dict):
        p["origen"]["quien"] = nombre_publico(pol, p["origen"].get("quien"))
    if isinstance(p.get("linea"), dict):
        p["linea"]["quien_origen"] = nombre_publico(pol, p["linea"].get("quien_origen"))
    if isinstance(p.get("area"), dict):
        p["area"]["fichas"] = [nombre_publico(pol, x) for x in p["area"].get("fichas") or []]
    return p


def chat(mensajes: list[dict], pol: dict) -> list[dict]:
    """Lo que escriben el narrador y el sistema, con los nombres públicos. Lo del jugador, tal cual."""
    if pol["patron"] is None:
        return mensajes
    salida = []
    for m in mensajes:
        if m.get("rol") in ("narrador", "sistema"):
            m = copy.deepcopy(m)
            m["texto"] = texto(pol, m.get("texto"))
            for parte in m.get("partes") or []:
                if parte.get("tipo") == "texto":
                    parte["texto"] = texto(pol, parte.get("texto"))
        salida.append(m)
    return salida


def resolver_objetivo(datos: dict, pedido: str, pol: dict | None = None) -> dict:
    """Un objetivo de ataque por su nombre público: PJ o enemigo en pie. Un nombre oculto no se resuelve."""
    pol = pol or politica(datos)
    clave = norm(pedido or "")
    if not clave:
        raise ValueError("falta el objetivo")
    candidatos = []
    vivos = [e for e in datos.get("enemigos") or [] if int(e.get("vida", 1) or 0) > 0]
    for ficha in list(datos.get("personajes") or []) + vivos:
        publico = nombre_publico(pol, ficha.get("nombre"))
        claves = {norm(publico)}
        if publico == ficha.get("nombre") and ficha.get("id"):
            claves.add(norm(ficha["id"]))
        candidatos.append((publico, claves, ficha))
    exactos = [c for c in candidatos if clave in c[1]]
    if len(exactos) == 1:
        return exactos[0][2]
    elegibles = exactos or [c for c in candidatos if any(n.startswith(clave) for n in c[1] if n)]
    if len(elegibles) == 1:
        return elegibles[0][2]
    if elegibles:
        raise ValueError(f"{pedido!r} es ambiguo: {', '.join(c[0] for c in elegibles)}")
    raise ValueError(f"no hay nadie llamado {pedido!r} a la vista; objetivos: {', '.join(c[0] for c in candidatos) or 'nadie'}")

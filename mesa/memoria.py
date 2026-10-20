"""Memoria de la historia: lo que no puede olvidarse aunque la conversación se reinicie.

Vive en `partida.json` (público: el visor la muestra y el jugador la corrige):

  memoria.hasta_ahora   resumen corrido de la historia, editable
  memoria.hechos        hechos clave: id, texto, categoría, fijado, archivado, escena, autor
  memoria.escenas       crónica: una línea por escena cerrada
  memoria.presupuesto   caracteres que los hechos no fijados pueden ocupar en el contexto

Es la compactación de la mesa: el contexto del director crece con los hechos y la
crónica, no con cada turno jugado, y una sesión nueva del harness retoma sin perder
canon. Los fijados entran siempre; los demás, del más reciente al más antiguo, mientras
quepan en el presupuesto; los archivados no entran pero siguen a la vista. Lo secreto
no va aquí: sigue en director.md.

El narrador propone hechos (cada escena o cada pocos turnos) y el jugador los corrige,
fija o archiva desde el visor. Las dos vías pasan por `aplicar`, con el mismo efecto.
"""

from __future__ import annotations

from datetime import date

from .texto import norm

CATEGORIAS = ("personaje", "pnj", "lugar", "objeto", "promesa", "mundo", "trama", "otro")
ACCIONES_HECHO = ("agregar", "editar", "fijar", "soltar", "archivar", "restaurar")
ACCIONES = ACCIONES_HECHO + ("hasta-ahora", "escena")
AUTORES = ("narrador", "jugador")

PRESUPUESTO = 2400  # caracteres: unos 600 tokens de hechos no fijados por contexto
MAX_HECHO = 500
MAX_HASTA_AHORA = 4000
MAX_ESCENA = 600
TURNOS_SIN_HECHO = 5
ESCENAS_EN_CONTEXTO = 12


def leer(datos: dict) -> dict:
    """La memoria tal como está, sin crearla (para lecturas)."""
    return datos.get("memoria") or {}


def _mem(datos: dict) -> dict:
    m = datos.setdefault("memoria", {})
    m.setdefault("hasta_ahora", "")
    m.setdefault("hechos", [])
    m.setdefault("escenas", [])
    return m


def presupuesto(datos: dict) -> int:
    try:
        return max(0, int(leer(datos).get("presupuesto", PRESUPUESTO)))
    except (TypeError, ValueError):
        return PRESUPUESTO


def _texto(texto, maximo: int, que: str) -> str:
    limpio = str(texto or "").replace("\\n", "\n").strip()
    if not limpio:
        raise ValueError(f"{que} está vacío")
    if len(limpio) > maximo:
        raise ValueError(f"{que} tiene {len(limpio)} caracteres; el máximo es {maximo}: resúmelo o pártelo en dos")
    return limpio


def _categoria(categoria) -> str:
    clave = norm(str(categoria or "otro"))
    if clave not in CATEGORIAS:
        raise ValueError(f"categoría desconocida {categoria!r} (valen: {', '.join(CATEGORIAS)})")
    return clave


def buscar(datos: dict, ident) -> dict:
    """Un hecho por id («H3», «h3» o «3»)."""
    clave = norm(str(ident or "")).upper()
    if not clave:
        raise ValueError("falta el id del hecho (p. ej. H3)")
    if clave.isdigit():
        clave = f"H{clave}"
    for hecho in leer(datos).get("hechos", []):
        if hecho.get("id", "").upper() == clave:
            return hecho
    raise ValueError(f"no hay hecho {ident!r} (mira `hecho listar --todos`)")


def _hoy() -> str:
    return date.today().isoformat()


def _linea(hecho: dict) -> str:
    marca = " [fijado]" if hecho.get("fijado") else ""
    return f"- {hecho['id']} ({hecho.get('categoria', 'otro')}){marca}: {hecho['texto']}"


def en_contexto(datos: dict) -> tuple[list[dict], list[dict]]:
    """(los que entran al contexto, los vigentes que quedan fuera por presupuesto).

    Los fijados entran siempre. Los demás, del más reciente al más antiguo, mientras
    quepan; se devuelven en orden de id para que se lean como una historia.
    """
    vigentes = [h for h in leer(datos).get("hechos", []) if not h.get("archivado")]
    fijados = [h for h in vigentes if h.get("fijado")]
    libres, fuera, usado = [], [], 0
    limite = presupuesto(datos)
    for hecho in reversed([h for h in vigentes if not h.get("fijado")]):
        largo = len(_linea(hecho)) + 1
        if usado + largo <= limite:
            libres.append(hecho)
            usado += largo
        else:
            fuera.append(hecho)
    orden = {h["id"]: i for i, h in enumerate(vigentes)}
    return sorted(fijados + libres, key=lambda h: orden[h["id"]]), sorted(fuera, key=lambda h: orden[h["id"]])


def uso(datos: dict) -> dict:
    """Cuánto ocupa la memoria en el contexto: para el visor y los avisos."""
    dentro, fuera = en_contexto(datos)
    hechos = leer(datos).get("hechos", [])
    return {
        "presupuesto": presupuesto(datos),
        "fijados": sum(len(_linea(h)) + 1 for h in dentro if h.get("fijado")),
        "libres": sum(len(_linea(h)) + 1 for h in dentro if not h.get("fijado")),
        "en_contexto": [h["id"] for h in dentro],
        "fuera": [h["id"] for h in fuera],
        "archivados": [h["id"] for h in hechos if h.get("archivado")],
    }


# ---------- cambios: una sola puerta para la CLI y el visor ----------

def aplicar(datos: dict, accion: str, *, ident=None, texto=None, categoria=None, fijado: bool = False,
            numero=None, autor: str = "narrador") -> tuple[dict, str]:
    """Aplica un cambio de memoria sobre `datos` y devuelve (evento, texto para el chat)."""
    if accion not in ACCIONES:
        raise ValueError(f"acción de memoria desconocida {accion!r} (valen: {', '.join(ACCIONES)})")
    if autor not in AUTORES:
        raise ValueError(f"autor desconocido {autor!r}")
    m = _mem(datos)
    escena = (datos.get("escena") or {}).get("numero")
    if accion == "agregar":
        limpio = _texto(texto, MAX_HECHO, "el hecho")
        if any(norm(h["texto"]) == norm(limpio) for h in m["hechos"]):
            raise ValueError("ese hecho ya está anotado")
        numero_id = max((int(h["id"][1:]) for h in m["hechos"] if h.get("id", "")[1:].isdigit()), default=0) + 1
        hecho = {
            "id": f"H{numero_id}", "texto": limpio, "categoria": _categoria(categoria), "fijado": bool(fijado),
            "archivado": False, "escena": escena, "autor": autor, "desde": _hoy(),
        }
        m["hechos"].append(hecho)
        return _evento(accion, hecho, autor), f"Hecho clave {hecho['id']} ({hecho['categoria']}){' fijado' if fijado else ''}: {limpio}"
    if accion == "hasta-ahora":
        m["hasta_ahora"] = _texto(texto, MAX_HASTA_AHORA, "«Hasta ahora»")
        return {"tipo": "memoria", "accion": accion, "texto": m["hasta_ahora"], "autor": autor}, "«Hasta ahora» actualizado."
    if accion == "escena":
        try:
            n = int(numero if numero is not None else escena)
        except (TypeError, ValueError):
            raise ValueError("indica el número de escena") from None
        resumen = anotar_escena(datos, n, texto or "")
        return {"tipo": "memoria", "accion": accion, "numero": n, "texto": resumen["resumen"], "autor": autor}, f"Crónica, escena {n}: {resumen['resumen']}"
    hecho = buscar(datos, ident)
    if accion == "editar":
        if texto is None and categoria is None:
            raise ValueError("editar pide texto nuevo, categoría o ambas")
        if texto is not None:
            hecho["texto"] = _texto(texto, MAX_HECHO, "el hecho")
        if categoria is not None:
            hecho["categoria"] = _categoria(categoria)
        hecho["editado"] = _hoy()
        hecho["editado_por"] = autor
        texto_chat = f"Hecho {hecho['id']} corregido: {hecho['texto']}"
    else:
        campo, valor = {"fijar": ("fijado", True), "soltar": ("fijado", False), "archivar": ("archivado", True), "restaurar": ("archivado", False)}[accion]
        hecho[campo] = valor
        texto_chat = {
            "fijar": f"Hecho {hecho['id']} fijado: entra siempre al contexto.",
            "soltar": f"Hecho {hecho['id']} suelto: entra si cabe en el presupuesto.",
            "archivar": f"Hecho {hecho['id']} archivado: sigue a la vista, fuera del contexto.",
            "restaurar": f"Hecho {hecho['id']} restaurado.",
        }[accion]
    return _evento(accion, hecho, autor), texto_chat


def fijar_presupuesto(datos: dict, caracteres: int) -> tuple[dict, str]:
    """Cuántos caracteres de hechos no fijados entran al contexto (los fijados, siempre)."""
    n = int(caracteres)
    if not 400 <= n <= 20000:
        raise ValueError("el presupuesto va de 400 a 20000 caracteres")
    _mem(datos)["presupuesto"] = n
    return {"tipo": "memoria", "accion": "presupuesto", "presupuesto": n}, f"Presupuesto de hechos no fijados: {n} caracteres."


def _evento(accion: str, hecho: dict, autor: str) -> dict:
    return {"tipo": "hecho", "accion": accion, "id": hecho["id"], "texto": hecho["texto"], "categoria": hecho.get("categoria"), "autor": autor}


def anotar_escena(datos: dict, numero: int, resumen=None, titulo: str | None = None, lugar: str | None = None) -> dict:
    """Escribe (o corrige) la línea de crónica de una escena.

    Sin resumen solo deja el título y el lugar, para que la línea se pueda escribir luego
    (`memoria escena N "..."`) sin perder de qué escena se trataba.
    """
    if numero < 1:
        raise ValueError("la crónica empieza en la escena 1")
    limpio = None if resumen is None else _texto(resumen, MAX_ESCENA, "el resumen de la escena")
    m = _mem(datos)
    entrada = next((e for e in m["escenas"] if e.get("numero") == numero), None)
    if entrada is None:
        actual = datos.get("escena") or {}
        entrada = {"numero": numero}
        if actual.get("numero") == numero:
            entrada.update({k: actual[k] for k in ("titulo", "lugar") if actual.get(k)})
        m["escenas"].append(entrada)
        m["escenas"].sort(key=lambda e: e.get("numero", 0))
    if titulo:
        entrada["titulo"] = titulo
    if lugar:
        entrada["lugar"] = lugar
    if limpio:
        entrada["resumen"] = limpio
    return entrada


# ---------- lo que lee el director ----------

def markdown(datos: dict) -> str:
    """La sección de memoria del contexto, dentro del presupuesto."""
    m = leer(datos)
    if not (m.get("hasta_ahora") or m.get("hechos") or m.get("escenas")):
        return (
            "## Memoria de la historia\n"
            "(vacía: propón hechos clave con `hecho agregar \"...\"` y un «Hasta ahora» con `memoria hasta-ahora \"...\"`; "
            "el jugador los corrige en el visor)\n"
        )
    lineas = ["## Memoria de la historia (canon: manda sobre lo que recuerdes de la conversación)"]
    if m.get("hasta_ahora"):
        lineas += ["", "**Hasta ahora:** " + m["hasta_ahora"]]
    dentro, fuera = en_contexto(datos)
    if dentro or fuera:
        u = uso(datos)
        lineas += ["", f"### Hechos clave ({len(dentro)} en contexto · {u['libres']}/{u['presupuesto']} caracteres de no fijados)"]
        lineas += [_linea(h) for h in dentro]
        if fuera:
            lineas.append(f"- (+{len(fuera)} fuera por presupuesto: {', '.join(h['id'] for h in fuera)}; `hecho listar --todos`)")
    escenas = [e for e in m.get("escenas", []) if e.get("resumen")]
    if escenas:
        viejas, recientes = escenas[:-ESCENAS_EN_CONTEXTO], escenas[-ESCENAS_EN_CONTEXTO:]
        lineas += ["", "### Crónica de escenas"]
        if viejas:
            lineas.append(f"- (escenas {viejas[0]['numero']}–{viejas[-1]['numero']}: las resume «Hasta ahora»; `memoria ver --todo`)")
        lineas += [f"- Escena {e['numero']}{' · ' + e['titulo'] if e.get('titulo') else ''}: {e['resumen']}" for e in recientes]
    return "\n".join(lineas) + "\n"


def listado(datos: dict, todos: bool = False) -> str:
    """Todos los hechos, con su estado: para `hecho listar`."""
    hechos = leer(datos).get("hechos", [])
    if not hechos:
        return "Sin hechos clave todavía."
    u = uso(datos)
    dentro, fuera = set(u["en_contexto"]), set(u["fuera"])
    lineas = []
    for h in hechos:
        if h.get("archivado") and not todos:
            continue
        estado = "archivado" if h.get("archivado") else "en contexto" if h["id"] in dentro else "fuera por presupuesto" if h["id"] in fuera else ""
        lineas.append(f"{_linea(h)}  · {estado} · {h.get('autor', '?')}, escena {h.get('escena', '?')}")
    ocultos = len(u["archivados"]) if not todos else 0
    if ocultos:
        lineas.append(f"(+{ocultos} archivados: `hecho listar --todos`)")
    lineas.append(f"Presupuesto: fijados {u['fijados']} + no fijados {u['libres']}/{u['presupuesto']} caracteres.")
    return "\n".join(lineas)


def ver(datos: dict, todo: bool = False) -> str:
    """`memoria ver`: lo que entra al contexto (o todo, con --todo)."""
    if not todo:
        return markdown(datos)
    m = leer(datos)
    partes = [markdown(datos), "## Todos los hechos", listado(datos, todos=True)]
    escenas = m.get("escenas", [])
    if escenas:
        partes += ["## Crónica completa"] + [f"- Escena {e['numero']}{' · ' + e['titulo'] if e.get('titulo') else ''}: {e.get('resumen', '')}" for e in escenas]
    return "\n".join(partes) + "\n"


def avisos(datos: dict, eventos: list[dict] | None = None) -> list[str]:
    """Lo que la memoria pide al narrador: hechos nuevos, presupuesto y crónica."""
    salida = []
    if eventos is not None:
        sin_hecho = 0
        for e in reversed(eventos):
            if e.get("tipo") == "hecho" and e.get("accion") in ("agregar", "editar"):
                break
            if e.get("tipo") == "turno":
                sin_hecho += 1
        if sin_hecho >= TURNOS_SIN_HECHO:
            salida.append(
                f"Van {sin_hecho} turnos sin hechos clave nuevos: propón 1–3 con `--cambio 'hecho agregar \"...\" --categoria ...'` "
                "(nombres, promesas, objetos, lo que cambió) y dile al jugador que puede corregirlos en el visor."
            )
    u = uso(datos)
    if u["fijados"] > u["presupuesto"]:
        salida.append(
            f"Los hechos fijados ocupan {u['fijados']} caracteres, más que el presupuesto ({u['presupuesto']}): "
            "propón al jugador fusionar o soltar alguno."
        )
    if u["fuera"]:
        salida.append(
            f"{len(u['fuera'])} hechos quedan fuera del contexto por presupuesto ({', '.join(u['fuera'])}): "
            "fusiona los parecidos o archiva los que ya no pesan."
        )
    return salida

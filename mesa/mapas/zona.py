"""La zona en cuadrícula: fachada de terreno, visión, movimiento, luz y áreas.

Es lo que el narrador dibuja en texto, una fila por línea, con un carácter
por terreno y su leyenda. Cada casilla mide `celda` metros (1,5 por defecto,
la casilla de 5 pies de D&D); el espacio es «fuera del mapa» y los dígitos
quedan para las fichas. Las distancias cuentan casillas como en D&D 2024:
la diagonal vale una.

Las reglas de visión, cobertura, movimiento e iluminación salen de
`srd-2024_combat_cover`, `srd-2024_combat_movement-and-position` y
`srd-2024_exploration_vision-and-light`; son la única fuente de verdad y
el visor pinta lo que aquí se calcula.
"""

from __future__ import annotations

import re

from ..texto import norm
from .base import CELDA, COLUMNAS, FORMAS_AREA, LUCES, coordenada, distancia_casillas, metros, validar_celda
from .luz import _focos_efectivos, iluminacion_celda, mapa_iluminacion, poner_luz
from .movimiento import area_efecto, camino_movimiento, consultar_area, consultar_linea
from .terreno import (
    _resumen_terreno,
    _semanticas,
    inferir_terreno,
    leer_dibujo,
    leer_leyenda,
    nueva_zona,
    poner_terreno,
    semantica_terreno,
    terrenos_mapa,
)
from .tokens import fichas, resolver_punto
from .vision import linea_entre

def reubicar(datos: dict) -> list[str]:
    """Tras redibujar: quita la casilla a quien quedó fuera; devuelve sus nombres."""
    mapa = (datos.get("escena") or {}).get("mapa")
    perdidos = []
    for p in (datos.get("escena") or {}).get("posiciones") or []:
        if not p.get("celda"):
            continue
        try:
            if mapa is None:
                raise ValueError
            p["celda"] = validar_celda(mapa, p["celda"])
        except ValueError:
            p.pop("celda", None)
            perdidos.append(p["quien"])
    return perdidos


def zona_texto(datos: dict) -> str:
    """El mapa de zona tal como lo ve el narrador: cuadrícula, leyenda, fichas y distancias."""
    escena = datos.get("escena") or {}
    mapa = escena.get("mapa")
    if not mapa:
        return ""
    filas = mapa["filas"]
    ancho = len(filas[0])
    rejilla = [list(f) for f in filas]
    lista = fichas(datos)
    for f in lista:
        col, fila = coordenada(f["celda"])
        if fila < len(rejilla) and col < ancho:
            rejilla[fila][col] = f["marca"]
    nombre = mapa.get("nombre") or escena.get("lugar") or "la zona"
    luz_amb = mapa.get("luz")
    extra_luz = f"; luz: {luz_amb}" if luz_amb else ""
    lineas = [
        f"Mapa de la zona: {nombre} (casilla de {metros(mapa['celda'])}; columnas A–{COLUMNAS[ancho - 1]}, filas 1–{len(filas)}{extra_luz})",
        "     " + " ".join(COLUMNAS[:ancho]),
    ]
    lineas += [f"  {i + 1:>2} " + " ".join(fila).rstrip() for i, fila in enumerate(rejilla)]
    lineas.append("Leyenda: " + " · ".join(f"{c} {s}" for c, s in mapa["leyenda"].items()))
    sem_items = []
    for c in mapa["leyenda"]:
        res_sem = _resumen_terreno(semantica_terreno(mapa, c))
        if res_sem:
            sem_items.append(f"{c} [{res_sem}]")
    if sem_items:
        lineas.append("Terreno: " + " · ".join(sem_items))
    focos = _focos_efectivos(mapa)
    if focos:
        lineas.append(
            "Luces: "
            + " · ".join(
                f"{x['celda']} ({x.get('nombre', 'foco')}: {metros(x['brillante'])} brillante + {metros(x['penumbra'])} penumbra)"
                for x in focos
            )
        )
    if lista:
        etiqueta = {"personaje": "", "amenaza": ", amenaza", "otro": ""}
        lineas.append("Fichas: " + " · ".join(f"{f['marca']} {f['quien']} ({f['celda']}{etiqueta[f['clase']]})" for f in lista))
        juntas = {}
        for f in lista:
            juntas.setdefault(f["celda"], []).append(f["quien"])
        for celda, quienes in juntas.items():
            if len(quienes) > 1:
                lineas.append(f"Comparten {celda}: {', '.join(quienes)}")
        for f in [x for x in lista if x["clase"] == "personaje"]:
            otros = [x for x in lista if x is not f]
            if otros:
                lineas.append(
                    f"Desde {f['quien']}: "
                    + " · ".join(f"{o['quien']} {metros(distancia_casillas(f['celda'], o['celda']) * mapa['celda'])}" for o in otros)
                )
                detalles_tacticos = []
                for o in otros:
                    lin = linea_entre(mapa, f["celda"], o["celda"], datos=datos)
                    cam = camino_movimiento(mapa, f["celda"], o["celda"])
                    partes_o = []
                    if not lin["visible"]:
                        partes_o.append("sin visión")
                    elif lin["cobertura"] != "ninguna":
                        bono = lin["bono_cobertura"]
                        partes_o.append(f"cob. {lin['cobertura']}" + (f" +{bono}" if bono else ""))
                    if cam["alcanzable"] and cam["casillas_coste"] != lin["distancia_casillas"]:
                        partes_o.append(f"camino {metros(cam['metros_coste'])}")
                    elif not cam["alcanzable"]:
                        partes_o.append("paso bloqueado")
                    if partes_o:
                        detalles_tacticos.append(f"{o['quien']} ({', '.join(partes_o)})")
                if detalles_tacticos:
                    lineas.append(f"Táctica desde {f['quien']}: " + " · ".join(detalles_tacticos))
    sin = [p for p in escena.get("posiciones") or [] if not p.get("celda")]
    if sin:
        lineas.append("Sin casilla: " + " · ".join(f"{p['quien']} («{p.get('donde', '')}»)" for p in sin))
    return "\n".join(lineas)


# ---------- proyección para el visor ----------

# Cómo se pinta cada terreno en el visor. Vive aquí, junto a las reglas, para que el
# navegador no tenga su propia lista: si el narrador escribe «estalagmita de calcita»,
# el motor decide a la vez cómo se comporta y cómo se ve.
_CLASES_POR_CARACTER = {"#": "solido", "+": "puerta", "=": "ventana", "~": "agua", "^": "escalera"}
_CLASES_POR_PALABRA = (
    (re.compile(r"\b(muro|pared|roca|pena|acantilado)\b"), "solido"),
    (re.compile(r"\b(puerta|porton|trampilla)\b"), "puerta"),
    (re.compile(r"\b(ventana|reja|aspillera|parapeto|baranda|barandilla)\b"), "ventana"),
    (re.compile(r"\b(arbol|bosque|arbusto|hierba|seto|vegetacion|maleza|jardin|tronco|estalagmita)\b"), "planta"),
    (re.compile(r"\b(mesa|silla|mueble|barril|caja|cama|estante|mostrador|carro|banco|baul|cofre|altar|barra|puesto|fuente)\b"), "mueble"),
    (re.compile(r"\b(escalera|rampa|desnivel|escalon)\b"), "escalera"),
    (re.compile(r"\b(abismo|vacio|hoyo|pozo|precipicio|grieta)\b"), "vacio"),
    (re.compile(r"\b(fuego|hoguera|lava|brasa|chimenea|antorcha|farol)\b"), "fuego"),
    (re.compile(r"\b(suelo|piso|camino|calle|tierra|arena|empedrado|muelle|madera|plaza|pasillo|orilla)\b"), "suelo"),
)


def clase_pintado(caracter: str, significado: str = "") -> str:
    """La clase CSS con la que el visor pinta un terreno (`t-solido`, `t-agua`…)."""
    if caracter in _CLASES_POR_CARACTER:
        return _CLASES_POR_CARACTER[caracter]
    s = norm(significado or "")
    for patron, clase in _CLASES_POR_PALABRA:
        if patron.search(s):
            return clase
    return "otro"


def proyeccion_zona(datos: dict, *, origen: str | None = None, destino: str | None = None,
                    forma: str | None = None, tamano: float | None = None) -> dict:
    """Todo lo que el visor necesita para pintar la zona, resuelto por el motor.

    El navegador no vuelve a decidir qué es un muro, dónde llega la luz ni cuánto
    cuesta un paso: solo pinta lo que sale aquí. Sin zona activa devuelve las
    listas vacías, que es lo que el visor muestra cuando todavía no hay mapa.

    `origen` y `destino` son la medición que el jugador tiene seleccionada en
    pantalla (no estado de la partida), así que llegan en la consulta.
    """
    escena = datos.get("escena") or {}
    mapa = escena.get("mapa")
    lista_fichas = fichas(datos)
    vacio: dict = {
        "hay_mapa": False, "luz_base": "brillante", "focos": [], "terrenos": [],
        "luz": [], "celda": CELDA, "fichas": [], "origen": None,
        "linea": None, "camino": None, "area": None,
    }
    if not mapa or not (mapa.get("filas") or []):
        return vacio

    semanticas = _semanticas(mapa)
    luz_por_celda = mapa_iluminacion(mapa)
    luz_base = mapa.get("luz") if mapa.get("luz") in LUCES else "brillante"
    focos = [{"celda": f["celda"], "nombre": f.get("nombre", "foco"),
              "brillante": float(f.get("brillante", 0) or 0),
              "penumbra": float(f.get("penumbra", 0) or 0)}
             for f in _focos_efectivos(mapa)]

    # Un registro por carácter del dibujo, no por casilla: en una mazmorra de 26x40
    # son unas seis entradas en lugar de más de mil.
    usados = [c for c in dict.fromkeys("".join(mapa["filas"])) if c != " "]
    terrenos = []
    for c in usados:
        sem = semanticas[c]
        terrenos.append({
            "caracter": c,
            "significado": (mapa.get("leyenda") or {}).get(c, "?"),
            "clase": clase_pintado(c, (mapa.get("leyenda") or {}).get(c, "")),
            "bloquea_paso": bool(sem["bloquea_paso"]),
            "bloquea_vision": bool(sem["bloquea_vision"]),
            "cobertura": sem["cobertura"],
            "dificil": bool(sem["dificil"]),
            "resumen": _resumen_terreno(sem),
        })

    # La luz solo viaja donde no es la del ambiente: en una zona a plena luz no
    # hay ni una entrada que enviar.
    luz = [{"celda": c, "nivel": n} for c, n in luz_por_celda.items() if n != luz_base]

    color_por_quien = {}
    for p in datos.get("personajes", []):
        color_por_quien[norm(p.get("nombre", ""))] = p.get("color")
        color_por_quien[norm(p.get("id", ""))] = p.get("color")
    fichas_pintura = [dict(f, color=color_por_quien.get(norm(f["quien"]))) for f in lista_fichas]

    salida = {
        "hay_mapa": True,
        "luz_base": luz_base,
        "focos": focos,
        "terrenos": terrenos,
        "luz": luz,
        "fichas": fichas_pintura,
        "celda": float(mapa.get("celda", CELDA)),
        "linea": None,
        "camino": None,
        "area": None,
    }
    if not origen:
        return salida
    try:
        c_orig, quien_orig = resolver_punto(datos, mapa, origen)
    except ValueError:
        return salida

    # La distancia desde la casilla de origen la muestra la leyenda de fichas, así que
    # viaja con ellas aunque el jugador todavía no haya elegido destino.
    celda_m = salida["celda"]
    for f in fichas_pintura:
        try:
            f["distancia_casillas"] = distancia_casillas(c_orig, f["celda"])
            f["distancia_m"] = round(f["distancia_casillas"] * celda_m, 2)
        except (TypeError, ValueError):
            f["distancia_casillas"] = None
            f["distancia_m"] = None

    if not destino:
        salida["origen"] = {"celda": c_orig, "quien": quien_orig}
        return salida
    try:
        c_dest, _ = resolver_punto(datos, mapa, destino)
    except ValueError:
        salida["origen"] = {"celda": c_orig, "quien": quien_orig}
        return salida
    salida["origen"] = {"celda": c_orig, "quien": quien_orig}

    lin = linea_entre(mapa, c_orig, c_dest, datos, semanticas)
    salida["linea"] = {
        "origen": c_orig, "destino": c_dest, "quien_origen": quien_orig,
        "visible": lin["visible"], "cobertura": lin["cobertura"],
        "bono": lin["bono_cobertura"],
        "distancia_casillas": lin["distancia_casillas"],
        # El visor solo necesita saber qué casillas son obstáculo, no el motivo. Una
        # esquina («B3/A4») son dos casillas: se parten para poder marcarlas.
        "obstaculos": sorted({c for o in lin["obstaculos"] for c in o["celda"].split("/")}),
    }
    cam = camino_movimiento(mapa, c_orig, c_dest)
    salida["camino"] = {
        "alcanzable": cam["alcanzable"], "casillas_coste": cam["casillas_coste"],
        "metros_coste": cam["metros_coste"], "camino": cam["camino"],
    }
    tipo = norm(forma or "")
    if tipo and tipo != "ninguna" and tipo in FORMAS_AREA and tamano:
        res = area_efecto(mapa, tipo, float(tamano), c_orig, c_dest, None, datos)
        salida["area"] = {
            "forma": res["forma"], "casillas": res["casillas"],
            "sombra": res["bloqueadas"], "fichas": res["fichas"],
        }
    return salida


__all__ = [
    "area_efecto",
    "camino_movimiento",
    "clase_pintado",
    "consultar_area",
    "consultar_linea",
    "fichas",
    "iluminacion_celda",
    "inferir_terreno",
    "leer_dibujo",
    "leer_leyenda",
    "linea_entre",
    "mapa_iluminacion",
    "nueva_zona",
    "poner_luz",
    "poner_terreno",
    "proyeccion_zona",
    "resolver_punto",
    "reubicar",
    "semantica_terreno",
    "terrenos_mapa",
    "zona_texto",
    "_resumen_terreno",
]

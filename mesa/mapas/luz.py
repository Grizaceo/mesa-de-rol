"""Luz ambiente, focos y nivel de iluminación por casilla."""

from __future__ import annotations

import re

from ..texto import norm
from .base import CELDA, LUCES, distancia_casillas, nombre_celda, validar_celda
from .vision import linea_entre

def _parsear_foco(mapa: dict, espec: str) -> dict:
    """«G4:6:6:farol» → {celda, brillante, penumbra, nombre}."""
    partes = [p.strip() for p in str(espec or "").split(":")]
    if len(partes) < 2 or not partes[0]:
        raise ValueError(f"foco inválido {espec!r}: usa «CELDA:BRILLANTE_M[:PENUMBRA_M[:NOMBRE]]», p. ej. «G4:6:6:farol»")
    celda = validar_celda(mapa, partes[0])
    try:
        brillante = float(partes[1].replace(",", "."))
        penumbra = float(partes[2].replace(",", ".")) if len(partes) >= 3 and partes[2] else brillante
    except ValueError:
        raise ValueError(f"radios de luz inválidos en {espec!r}: deben ser metros numéricos") from None
    if brillante < 0 or penumbra < 0 or (brillante == 0 and penumbra == 0):
        raise ValueError("el foco de luz necesita un radio positivo en metros")
    foco = {"celda": celda, "brillante": brillante, "penumbra": penumbra}
    if len(partes) >= 4 and partes[3]:
        foco["nombre"] = ":".join(partes[3:]).strip()
    return foco


def poner_luz(mapa: dict, luz: str | None = None, focos: list[str] | None = None, limpiar_focos: bool = False) -> dict:
    """Configura la luz ambiental de la zona (`brillante|penumbra|oscuridad`) y sus focos puntuales."""
    if not mapa or not mapa.get("filas"):
        raise ValueError("no hay mapa de zona activo")
    if luz is not None:
        nivel = norm(luz)
        if nivel not in LUCES:
            raise ValueError(f"luz inválida {luz!r} (usa: {', '.join(LUCES)})")
        mapa["luz"] = nivel
    if limpiar_focos:
        mapa.pop("luces", None)
    for f in focos or []:
        nuevo = _parsear_foco(mapa, f)
        lista = mapa.setdefault("luces", [])
        lista[:] = [x for x in lista if x.get("celda") != nuevo["celda"]]
        lista.append(nuevo)
    return {"luz": mapa.get("luz", "brillante"), "luces": list(mapa.get("luces") or [])}


_FUEGO_RE = re.compile(r"\b(fuego|hoguera|antorcha|farol|linterna|brasa|chimenea|lava)\b")


def _caracteres_de_fuego(mapa: dict) -> set[str]:
    """Caracteres cuya leyenda describe una fuente de luz.

    Antes se normalizaba y se comparaba la leyenda *de cada casilla* para decidir
    si era un foco; en una rejilla de 26x40 (1.040 casillas) eso son 1.040
    normalizaciones de texto y 1.040 expresiones regulares por cada cálculo de
    iluminación. Un foco se decide por carácter, no por casilla, así que basta
    mirar los caracteres que de verdad aparecen en el dibujo.
    """
    leyenda = mapa.get("leyenda") or {}
    return {c for c in set("".join(mapa.get("filas") or [])) if _FUEGO_RE.search(norm(leyenda.get(c, "")))}


def _focos_efectivos(mapa: dict, fuegos: set[str] | None = None) -> list[dict]:
    focos = [dict(f) for f in (mapa.get("luces") or [])]
    Conocidas = {f["celda"] for f in focos}
    if fuegos is None:
        fuegos = _caracteres_de_fuego(mapa)
    if not fuegos:
        return focos
    leyenda = mapa.get("leyenda") or {}
    for fi, fila in enumerate(mapa.get("filas") or []):
        for co, ch in enumerate(fila):
            if ch not in fuegos:
                continue
            celda = nombre_celda(co, fi)
            if celda in Conocidas:
                continue
            focos.append({"celda": celda, "brillante": 6.0, "penumbra": 6.0, "nombre": leyenda.get(ch, "luz")})
    return focos


def iluminacion_celda(mapa: dict, celda: str, focos: list[dict] | None = None) -> str:
    """Nivel de luz en una casilla (`brillante|penumbra|oscuridad`) según ambiente y focos con visión.

    `focos` es para quien ilumina todo el mapa de una vez: sin él, cada llamada
    vuelve a recorrer el dibujo para reencontrar los focos.
    """
    c_norm = validar_celda(mapa, celda)
    base = mapa.get("luz", "brillante")
    if base not in LUCES:
        base = "brillante"
    indice = LUCES.index(base)
    if indice == 2:
        return "brillante"
    celda_m = float(mapa.get("celda", CELDA))
    for foco in (_focos_efectivos(mapa) if focos is None else focos):
        f_celda = foco["celda"]
        dist_m = distancia_casillas(f_celda, c_norm) * celda_m
        r_brill = float(foco.get("brillante", 0))
        r_pen = float(foco.get("penumbra", 0))
        if dist_m > r_brill + r_pen + 1e-6:
            continue
        if f_celda != c_norm and not linea_entre(mapa, f_celda, c_norm)["visible"]:
            continue
        if dist_m <= r_brill + 1e-6:
            return "brillante"
        indice = max(indice, 1)
    return LUCES[indice]


def mapa_iluminacion(mapa: dict) -> dict[str, str]:
    """Diccionario `{celda: nivel_luz}` para todas las casillas del mapa."""
    res: dict[str, str] = {}
    filas = mapa.get("filas") or []
    base = mapa.get("luz", "brillante")
    if base not in LUCES or LUCES.index(base) == 2:
        # Con luz ambiente brillante no hace falta ni buscar los focos: todo está iluminado.
        for fi, fila in enumerate(filas):
            for co, ch in enumerate(fila):
                if ch != " ":
                    res[nombre_celda(co, fi)] = "brillante"
        return res
    focos = _focos_efectivos(mapa)
    for fi, fila in enumerate(filas):
        for co, ch in enumerate(fila):
            if ch != " ":
                c = nombre_celda(co, fi)
                res[c] = iluminacion_celda(mapa, c, focos)
    return res

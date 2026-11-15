"""Fichas sobre la cuadrícula: quién ocupa cada casilla."""

from __future__ import annotations

from ..texto import norm
from .base import _CELDA_RE, validar_celda

def _clase(datos: dict, quien: str) -> str:
    clave = norm(quien)
    for p in datos.get("personajes", []):
        if clave in {norm(p.get("nombre", "")), norm(p.get("id", ""))}:
            return "personaje"
    for e in datos.get("enemigos", []):
        if clave == norm(e.get("nombre", "")):
            return "amenaza"
    return "otro"


def fichas(datos: dict) -> list[dict]:
    """Las posiciones con casilla, numeradas: personajes primero, luego amenazas y el resto."""
    posiciones = (datos.get("escena") or {}).get("posiciones") or []
    con_celda = [dict(p, clase=_clase(datos, p["quien"])) for p in posiciones if p.get("celda")]
    orden = {"personaje": 0, "amenaza": 1, "otro": 2}
    con_celda.sort(key=lambda p: orden[p["clase"]])
    for i, p in enumerate(con_celda, start=1):
        p["marca"] = str(i) if i <= 9 else "*"
    return con_celda


def resolver_punto(datos: dict | None, mapa: dict, ref: str) -> tuple[str, str | None]:
    """Acepta una casilla («F4») o el nombre de una ficha («Cris») y devuelve (celda, nombre_ficha)."""
    texto = str(ref or "").strip()
    if not texto:
        raise ValueError("falta indicar la casilla o el personaje")
    if _CELDA_RE.match(texto):
        celda = validar_celda(mapa, texto)
        ocupante = next((f["quien"] for f in fichas(datos or {}) if f["celda"] == celda), None)
        return celda, ocupante
    clave = norm(texto)
    lista = fichas(datos or {})
    exactos = [f for f in lista if clave == norm(f["quien"])]
    if len(exactos) == 1:
        return validar_celda(mapa, exactos[0]["celda"]), exactos[0]["quien"]
    prefijos = [f for f in lista if norm(f["quien"]).startswith(clave)]
    if len(prefijos) == 1:
        return validar_celda(mapa, prefijos[0]["celda"]), prefijos[0]["quien"]
    if prefijos:
        raise ValueError(f"{ref!r} es ambiguo en el mapa: {', '.join(f['quien'] for f in prefijos)}")
    raise ValueError(f"no hay casilla ni ficha {ref!r} en el mapa de zona")

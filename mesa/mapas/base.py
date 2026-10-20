"""Lo que comparten la zona, el mundo y los importadores.

Las constantes de la cuadrícula (columnas, casilla de 1,5 m, grados de
cobertura y niveles de luz del SRD 5.2.1) y la geometría mínima —leer,
validar y medir casillas—, que no pertenece a ningún mapa en concreto.
"""

from __future__ import annotations

import re
import string


COLUMNAS = string.ascii_uppercase  # A–Z: 26 columnas como máximo


MAX_FILAS = 40


CELDA = 1.5


LEYENDA_BASE = {"#": "muro", ".": "suelo", "+": "puerta", "~": "agua", "=": "ventana", "^": "escalera"}


_CELDA_RE = re.compile(r"^\s*([A-Za-z])\s*(\d{1,2})\s*$")


_ETIQUETAS_LEYENDA_RE = re.compile(r"^(.*?)\s*\[([^\]]+)\]\s*$")


UNIDAD = "km"


COBERTURAS = ("ninguna", "media", "tres-cuartos", "total")


BONO_COBERTURA = {"ninguna": 0, "media": 2, "tres-cuartos": 5, "total": None}


LUCES = ("oscuridad", "penumbra", "brillante")


FORMAS_AREA = ("cono", "esfera", "emanacion", "cilindro", "linea", "cubo")


TIPOS_ZONA = ("mazmorra", "taberna", "calle", "bosque", "cueva", "puente")


ALIAS_TIPO_ZONA = {
    "mazmorra": "mazmorra", "calabozo": "mazmorra", "cripta": "mazmorra",
    "taberna": "taberna", "interior": "taberna", "posada": "taberna",
    "calle": "calle", "plaza": "calle",
    "bosque": "bosque", "claro": "bosque",
    "cueva": "cueva", "caverna": "cueva",
    "puente": "puente",
}


DENSIDADES = ("baja", "normal", "alta")


_DIMENSIONES_BASE = {
    "mazmorra": (18, 12, "oscuridad", "Mazmorra"),
    "taberna": (14, 10, "brillante", "Taberna"),
    "calle": (16, 11, "brillante", "Plaza y calle"),
    "bosque": (16, 11, "brillante", "Claro del bosque"),
    "cueva": (16, 11, "oscuridad", "Caverna"),
    "puente": (16, 9, "brillante", "Puente"),
}


RUMBOS: dict[str, tuple[int, int]] = {
    "n": (0, -1), "norte": (0, -1),
    "ne": (1, -1), "noreste": (1, -1),
    "e": (1, 0), "este": (1, 0),
    "se": (1, 1), "sureste": (1, 1),
    "s": (0, 1), "sur": (0, 1),
    "so": (-1, 1), "suroeste": (-1, 1), "sw": (-1, 1),
    "o": (-1, 0), "oeste": (-1, 0), "w": (-1, 0),
    "no": (-1, -1), "noroeste": (-1, -1), "nw": (-1, -1),
}


def cifra(valor: float) -> str:
    """4.5 → «4,5»; 6.0 → «6»: un decimal como mucho, con coma."""
    return f"{round(float(valor), 1):.1f}".rstrip("0").rstrip(".").replace(".", ",")


def metros(valor: float) -> str:
    return f"{cifra(valor)} m"


def coordenada(celda: str) -> tuple[int, int]:
    """«C4» → (2, 3): columna y fila desde cero."""
    m = _CELDA_RE.match(str(celda or ""))
    if not m or int(m.group(2)) < 1:
        raise ValueError(f"casilla inválida {celda!r}: usa columna y fila, p. ej. C4")
    return COLUMNAS.index(m.group(1).upper()), int(m.group(2)) - 1


def nombre_celda(col: int, fila: int) -> str:
    return f"{COLUMNAS[col]}{fila + 1}"


def validar_celda(mapa: dict, celda: str) -> str:
    """Normaliza la casilla y comprueba que cae dentro del mapa."""
    col, fila = coordenada(celda)
    filas = mapa["filas"]
    if fila >= len(filas) or col >= len(filas[0]):
        raise ValueError(f"{celda} cae fuera del mapa (columnas A–{COLUMNAS[len(filas[0]) - 1]}, filas 1–{len(filas)})")
    if filas[fila][col] == " ":
        raise ValueError(f"{celda} está fuera del mapa dibujado (es un espacio)")
    return nombre_celda(col, fila)


def distancia_casillas(a: str, b: str) -> int:
    (c1, f1), (c2, f2) = coordenada(a), coordenada(b)
    return max(abs(c1 - c2), abs(f1 - f2))


def _semilla_entera(semilla: int | str | None, base: str = "") -> int:
    if semilla is None or str(semilla).strip() == "":
        h = 2166136261
        for b in (base or "mesa").encode("utf-8"):
            h = ((h ^ b) * 16777619) & 0x7FFFFFFF
        return h or 1
    try:
        return int(semilla)
    except (TypeError, ValueError):
        h = 2166136261
        for b in str(semilla).encode("utf-8"):
            h = ((h ^ b) * 16777619) & 0x7FFFFFFF
        return h or 1

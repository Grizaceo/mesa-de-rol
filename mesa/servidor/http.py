"""Constantes y utilidades HTTP del visor: tipos, CSP, JSON acotado y papeles de la sala."""

from __future__ import annotations

import hashlib
import ipaddress
import math
import mimetypes
import re

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")

# Lo que el visor puede servir como medio. El SVG solo aparece en la tarjeta que genera
# `imagen ninguna` con valores controlados; se sirve enjaulado por si quedó uno de antes.
TIPOS_RASTER = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TIPOS_MEDIO = TIPOS_RASTER | {".svg"}
CSP_SVG = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
# El visor no carga nada de fuera ni ejecuta scripts en línea: si algún día se colara un
# texto sin escapar, el navegador no lo ejecutaría.
CSP_VISOR = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "object-src 'none'; base-uri 'none'; form-action 'self'"
)
MAX_CUERPO = 16 * 1024
HOSTS_LOCALES = {"localhost", "127.0.0.1", "[::1]"}
MIN_CLAVE_SALA = 16
TTL_RECLAMO = 120.0  # segundos sin sondear antes de soltar el PJ reclamado
TTL_PRESENCIA = 6.0
MAX_PRESENCIA = 64
MAX_CAMPANAS_SALA = 5  # campañas nuevas que puede crear la sala por arranque del servidor
MARCA_BIBLIA = re.compile(r"<!-- generada por el visor · ([0-9a-f]{16}) -->\n")


def _es_loopback(direccion: str) -> bool:
    try:
        return ipaddress.ip_address(direccion).is_loopback
    except ValueError:
        return False


def _rechazar_constante(nombre: str):
    raise ValueError(f"número no válido en el JSON: {nombre}")


def _float_finito(texto: str) -> float:
    numero = float(texto)
    if not math.isfinite(numero):
        raise ValueError("número fuera de rango en el JSON")
    return numero


def _numero(cuerpo: dict, campo: str, defecto=None, *, minimo: float, maximo: float, entero: bool = True):
    """Un número del cuerpo dentro de un rango; None o "" devuelven el defecto."""
    valor = cuerpo.get(campo)
    if valor is None or valor == "":
        return defecto
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
        raise ValueError(f"«{campo}» tiene que ser un número")
    try:
        numero = float(valor)
    except ValueError:
        raise ValueError(f"«{campo}» tiene que ser un número") from None
    if not math.isfinite(numero) or not minimo <= numero <= maximo:
        raise ValueError(f"«{campo}» va de {minimo:g} a {maximo:g}")
    if not entero:
        return round(numero, 2)
    if not numero.is_integer():
        raise ValueError(f"«{campo}» tiene que ser un número entero")
    return int(numero)


def _texto(cuerpo: dict, campo: str, largo: int) -> str:
    valor = cuerpo.get(campo)
    if valor is None:
        return ""
    if not isinstance(valor, (str, int, float)) or isinstance(valor, bool):
        raise ValueError(f"«{campo}» tiene que ser texto")
    return str(valor).strip()[:largo]


def _huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def _ajustar_ca(ficha: dict, delta: int) -> None:
    """Equipar o quitar armadura y escudo mueve la CA guardada, que es la que usa el motor."""
    if not delta:
        return
    for campo in ("ca", "defensa"):
        if campo in ficha:
            ficha[campo] = int(ficha[campo]) + delta


def _bono_ca(objeto: dict) -> int:
    try:
        return int(objeto.get("bono_ca") or 0)
    except (TypeError, ValueError):
        return 0


class Prohibido(Exception):
    """La petición de escritura no viene del visor local."""


class SinNarrador(Exception):
    """El visor se arrancó sin agente: el chat es de solo lectura."""


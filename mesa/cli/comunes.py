"""Constantes y carga/cierre compartidos por los comandos de la CLI."""

from __future__ import annotations

import argparse
import json
from contextlib import nullcontext

from .. import bloqueo, capacidades, estado

# Comandos que escriben estado de la partida: `main` les toma el candado del archivo
# (bloqueo.py) antes de cargar, para que dos procesos no se pisen a media transacción.
# Los de solo lectura no lo toman: el visor puede leer mientras alguien escribe.
ESCRIBEN = frozenset({
    "retomar", "pausar", "tirar", "suerte", "prueba", "ataque", "dano",
    "vida", "condicion", "habilidad", "vendaje", "descanso", "enemigo", "nivel", "piloto",
    "iniciativa", "conjuro", "adjudicar",
    "escena", "pnj", "pista", "documento", "trama", "misterio", "recurso", "reloj",
    "turno", "regla", "nota", "imagen", "hecho", "memoria", "mapa", "mundo",
})

# Subacciones de solo lectura de comandos que en general escriben: no toman el candado.
SOLO_LECTURA = {
    "documento": {"ver"}, "imagen": {"buscar", "biblioteca-agregar"},
    "hecho": {"listar"}, "memoria": {"ver"},
    "mapa": {"ver", "linea", "area", "catalogo"},
    "mundo": {"ver", "viaje"},
}

# Comandos que `turno --cambio` puede aplicar junto con el turno: todos cargan el estado con
# _cargar y lo cierran con _cerrar, así que dentro de un lote comparten una sola carga y un
# solo guardado.
CAMBIOS = (
    "vida", "condicion", "habilidad", "vendaje", "descanso", "enemigo", "nivel",
    "iniciativa", "conjuro", "adjudicar", "escena", "pnj",
    "pista", "documento", "trama", "misterio", "recurso", "reloj", "regla", "hecho", "memoria", "mapa", "mundo",
)

# Lote en curso de `turno --cambio`: {"slug", "datos", "hechos": [(evento, texto)]}.
_lote: dict | None = None

# Perfil de capacidades de esta ejecución: la CLI completa o el MCP de juego (ver capacidades.py).
_perfil = capacidades.CLI


def _bono(texto: str) -> tuple[int, str]:
    valor, _, fuente = texto.partition(":")
    try:
        return int(valor), fuente.strip()
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"bono inválido {texto!r}: usa N o N:fuente (p. ej. 2:ayuda)") from e


def _imprimir(args, evento: dict, texto: str) -> None:
    print(json.dumps(evento, ensure_ascii=False, indent=2) if args.json else texto)


def _cargar(args) -> tuple[str, dict]:
    if _lote is not None:
        return _lote["slug"], _lote["datos"]
    slug = estado.slug_activo(args.partida)
    return slug, estado.cargar(slug)


def _cerrar(args, slug: str, datos: dict, evento: dict, texto: str) -> None:
    if _lote is not None:
        _lote["hechos"].append((evento, texto))
        return
    # Snapshot y bitácora en una sola transacción: un corte no deja medio cambio.
    (evento,) = estado.escribir(slug, datos=datos, eventos=[evento])
    _imprimir(args, evento, texto)


def _cerrar_mapa(args, slug: str, datos: dict, evento: dict, resumen: str) -> None:
    """Cierra una acción que deja un mapa de zona nuevo.

    Recoloca las fichas en la rejilla nueva y avisa de las que se quedaron fuera. Suelto,
    el narrador recibe el mapa entero en texto; dentro de `turno` ya se imprime al final,
    así que basta la línea de `resumen`. El evento lo arma cada acción porque cada una
    publica sus propios campos.
    """
    from .. import mapas
    perdidos = mapas.reubicar(datos)
    texto = mapas.zona_texto(datos) if _lote is None else resumen
    if perdidos:
        texto += f"\n⚠ Quedaron sin casilla (fuera del mapa nuevo): {', '.join(perdidos)}."
    _cerrar(args, slug, datos, evento, texto)


def _candado_de_escritura(args):
    """Toma el candado de la partida para el comando completo, si el comando escribe."""
    if args.comando not in ESCRIBEN or getattr(args, "accion", None) in SOLO_LECTURA.get(args.comando, ()):
        return nullcontext()
    try:
        ruta = estado.ruta_candado(estado.slug_activo(args.partida))
    except (ValueError, FileNotFoundError):
        # Sin partida activa (p. ej. `nueva`) o con un slug que no existe: el comando
        # fallará con su propio error; no hay estado que proteger.
        return nullcontext()
    return bloqueo.candado(ruta)


def _recargar(datos: dict, recargas: set[str], quienes: list[dict] | None = None) -> list[tuple[str, str]]:
    """Recarga las habilidades gastadas con esas recargas; devuelve (personaje, habilidad)."""
    recargadas = []
    for p in datos.get("personajes", []) if quienes is None else quienes:
        for h in p.get("habilidades", []):
            if h.get("recarga") in recargas and h.get("disponible") is False:
                h["disponible"] = True
                recargadas.append((p["nombre"], h["nombre"]))
    return recargadas

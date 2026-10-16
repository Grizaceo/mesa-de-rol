"""Capacidades por superficie: qué puede hacer el MCP de juego y qué la CLI.

El MCP ejecuta el mismo motor que la CLI para las acciones de mesa, pero no su
administración: instalar la skill de Hermes, regenerar adaptadores, servir el visor
o importar archivos de fuera de la partida son operaciones deliberadas de la CLI, no
algo que deba poder disparar el texto del narrador. La política vive aquí una sola
vez para que el comando directo y los cambios anidados de `turno` no divergan.
"""

from __future__ import annotations

import argparse

from . import imagenes

CLI = "cli"    # la CLI completa: incluye administración e importaciones deliberadas
JUEGO = "juego"  # el MCP: solo acciones de mesa

# Acciones de juego que el MCP puede ejecutar (subconjunto de la CLI). Todo lo que no
# esté aquí se rechaza con un motivo legible, también cuando va dentro de `turno --cambio`.
DE_JUEGO = frozenset({
    "partidas", "usar", "nueva", "estado", "revisar", "retomar", "pausar", "contexto",
    "tirar", "prueba", "ataque", "dano", "suerte",
    "vida", "condicion", "habilidad", "vendaje", "descanso", "enemigo", "nivel",
    "escena", "pnj", "pista", "documento", "trama", "misterio", "recurso", "reloj",
    "turno", "regla", "nota", "imagen", "guardar", "retro", "leccion",
})

# Campo del parseo → motivo: lee o publica archivos de fuera de la partida.
BANDERAS = {"documento": {"archivo": "lee archivos de fuera de la partida"}}

# Subacción → motivo: sale a la red, gasta crédito o importa archivos.
SUBACCIONES = {
    "imagen": {
        "generar": "gasta crédito de un proveedor externo",
        "biblioteca-agregar": "importa un archivo a la biblioteca",
    },
}


def revisar(args: argparse.Namespace, perfil: str = CLI) -> str | None:
    """Devuelve el motivo del rechazo, o None si la acción está permitida en ese perfil.

    Mira el comando y sus campos ya parseados: un cambio anidado de `turno` pasa por
    el mismo examen que el comando suelto, sin depender del primer token del texto.
    """
    if perfil != JUEGO:
        return None
    comando = getattr(args, "comando", "")
    if comando not in DE_JUEGO:
        return f"`{comando}` no es una acción de juego: la administración del repo y del harness va por la CLI"
    for campo, motivo in BANDERAS.get(comando, {}).items():
        if getattr(args, campo, None):
            return f"`{comando} --{campo}` {motivo}: hazlo con la CLI, no desde el MCP"
    subacciones = SUBACCIONES.get(comando) or {}
    accion = getattr(args, "accion", None)
    if isinstance(accion, str) and accion in subacciones:
        return f"`{comando} {accion}` {subacciones[accion]}: decídelo con la CLI, no desde el MCP"
    return None


def de_biblioteca(fuente: str) -> bool:
    """¿La fuente de `imagen elegir` es una entrada de la biblioteca curada?

    Las rutas y las URLs leen o descargan de fuera: desde el MCP solo se elige lo que
    una persona ya puso en biblioteca/imagenes/.
    """
    return any(item.get("id") == fuente or item.get("archivo") == fuente for item in imagenes.leer_biblioteca())

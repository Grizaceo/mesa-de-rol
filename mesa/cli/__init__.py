"""CLI `mesa`: la herramienta que usa el director (humano o IA) durante la partida.

Cada comando que tira dados o cambia el estado deja un evento en la bitácora,
y el visor (`mesa servir`) lo muestra en vivo.

La implementación está partida en módulos (comandos por dominio, parser cacheado),
pero esta fachada sigue exportando `main`: `from mesa import cli` no cambia.
"""

from __future__ import annotations

import sys

from .. import capacidades
from .comunes import CAMBIOS, ESCRIBEN, SOLO_LECTURA, _candado_de_escritura
from . import comunes

__all__ = ["CAMBIOS", "ESCRIBEN", "SOLO_LECTURA", "main"]

# Comando CLI → submódulo que define `c_<comando>`. La fachada los expone con
# `__getattr__` para no cargar combate/fuentes/visor al solo importar el paquete.
_MODULO_COMANDO = {
    "partidas": "partida", "usar": "partida", "nueva": "partida", "estado": "partida",
    "revisar": "partida", "retomar": "partida", "pausar": "partida", "contexto": "partida",
    "guardar": "partida",
    "harness": "admin", "recursos": "admin", "fuentes": "admin", "migrar": "admin",
    "imagen": "admin", "leccion": "admin", "retro": "admin", "servir": "admin",
    "tirar": "combate", "prueba": "combate", "ataque": "combate", "dano": "combate",
    "suerte": "combate", "vida": "combate", "condicion": "combate", "habilidad": "combate",
    "vendaje": "combate", "descanso": "combate", "enemigo": "combate", "piloto": "combate",
    "nivel": "combate", "iniciativa": "combate", "conjuro": "combate", "adjudicar": "combate",
    "escena": "escena", "hecho": "escena", "memoria": "escena", "mapa": "escena", "mundo": "escena",
    "pnj": "registro", "pista": "registro", "documento": "registro", "trama": "registro",
    "misterio": "registro", "recurso": "registro", "reloj": "registro", "turno": "registro",
    "regla": "registro", "nota": "registro",
}


def __getattr__(name: str):
    if name.startswith("c_"):
        sub = _MODULO_COMANDO.get(name[2:])
        if sub is not None:
            import importlib
            val = getattr(importlib.import_module(f".{sub}", __package__), name)
            globals()[name] = val
            return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main(
    argv: list[str] | None = None,
    prohibidos: frozenset[str] = frozenset(),
    perfil: str = capacidades.CLI,
) -> int:
    """Ejecuta un comando. `perfil=capacidades.JUEGO` aplica la política del MCP de juego."""
    from .parser import construir
    anterior, comunes._perfil = comunes._perfil, perfil
    try:
        args = construir().parse_args(argv)
        if args.comando in prohibidos:
            print(f"error: `{args.comando}` no se puede usar desde aquí", file=sys.stderr)
            return 1
        motivo = capacidades.revisar(args, comunes._perfil)
        if motivo:
            print(f"error: {motivo}", file=sys.stderr)
            return 1
        try:
            with _candado_de_escritura(args):
                args.funcion(args)
        except (ValueError, FileNotFoundError, FileExistsError, RuntimeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except OSError as e:  # red caída, permisos, disco: un error legible, no un traceback
            print(f"error de sistema o de red: {e}", file=sys.stderr)
            return 1
        return 0
    finally:
        comunes._perfil = anterior

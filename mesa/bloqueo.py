"""Un escritor a la vez por archivo de estado, con un candado de sistema de archivos.

El estado de una partida lo escriben la CLI y el MCP, a veces desde procesos
distintos. Cada comando que muta toma un candado exclusivo
(`partidas/<slug>/.candado`) antes de cargar el estado, y lo suelta al terminar:
el que no lo consigue en `MESA_ESPERA_CANDADO` segundos (5 por defecto) recibe un
error legible en vez de escribir a ciegas encima del otro.

Mecanismo: `fcntl.flock`, POSIX (Linux y macOS), sin dependencias ni servidor que
mantener. El candado lo libera el sistema si el proceso muere, así que un corte no
deja la partida bloqueada. En un sistema sin `fcntl` (Windows) no hay candado entre
procesos: se avisa una vez por stderr y se sigue con el candado de hilos, sin
prometer serialización entre procesos.

Reentrante por hilo: `main()` toma el candado del comando completo y
`estado.escribir` vuelve a pedirlo para su transacción sin bloquearse. Hilos del
mismo proceso se esperan entre sí (el candado es del archivo, no del hilo), y dos
procesos distintos se rechazan con `Ocupado` cuando se acaba la espera.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

ESPERA_POR_DEFECTO = 5.0


class Ocupado(RuntimeError):
    """Otro proceso tiene el candado y no lo soltó dentro de la espera."""


class _Entrada:
    __slots__ = ("rlock", "profundidad", "fd")

    def __init__(self) -> None:
        self.rlock = threading.RLock()
        self.profundidad = 0
        self.fd: int | None = None


_datos: dict[str, _Entrada] = {}
_guarda = threading.Lock()
_avisado = False


def espera(explicita: float | None = None) -> float:
    """Segundos de espera: la del argumento o `$MESA_ESPERA_CANDADO`."""
    if explicita is not None:
        return explicita
    try:
        return float(os.environ.get("MESA_ESPERA_CANDADO", ESPERA_POR_DEFECTO))
    except ValueError:
        return ESPERA_POR_DEFECTO


def _mensaje(ruta: Path) -> str:
    try:
        dueno = ruta.read_text(encoding="utf-8").strip()
    except OSError:
        dueno = ""
    quien = f" (lo tiene el proceso {dueno})" if dueno else ""
    return f"otro proceso está escribiendo en «{ruta.parent.name}»{quien}: reintenta en unos segundos"


def _tomar(ruta: Path, segundos: float) -> int | None:
    global _avisado
    if fcntl is None:  # pragma: no cover - Windows
        if not _avisado:
            _avisado = True
            print("aviso: sin `fcntl` no hay candado entre procesos; dos comandos a la vez pueden pisarse", file=sys.stderr)
        return None
    fd = os.open(ruta, os.O_CREAT | os.O_RDWR, 0o644)
    limite = time.monotonic() + segundos
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= limite:
                os.close(fd)
                raise Ocupado(_mensaje(ruta)) from None
            time.sleep(0.02)
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    os.fsync(fd)
    return fd


def _soltar(entrada: _Entrada) -> None:
    if entrada.fd is None:
        return
    try:
        fcntl.flock(entrada.fd, fcntl.LOCK_UN)
    finally:
        os.close(entrada.fd)
        entrada.fd = None


@contextmanager
def candado(ruta: Path | str, espera_segundos: float | None = None) -> Iterator[None]:
    """Toma el candado de `ruta` (creándolo si hace falta) y lo suelta al salir.

    Reentrante dentro del mismo hilo: el candado del archivo se toma una sola vez,
    cuando la profundidad pasa de 0 a 1, y se suelta al volver a 0.
    """
    clave = str(ruta)
    segundos = espera(espera_segundos)
    with _guarda:
        entrada = _datos.setdefault(clave, _Entrada())
    if not entrada.rlock.acquire(timeout=segundos):
        raise Ocupado(_mensaje(Path(clave)))
    try:
        if entrada.profundidad == 0:
            entrada.fd = _tomar(Path(clave), segundos)
        entrada.profundidad += 1
        try:
            yield
        finally:
            entrada.profundidad -= 1
            if entrada.profundidad == 0:
                _soltar(entrada)
    finally:
        entrada.rlock.release()

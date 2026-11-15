"""Servidor local del visor: solo 127.0.0.1 por defecto.

Sirve el visor, la partida, la bitácora y las imágenes. Nunca sirve director.md ni
biblia.md, y la partida sale filtrada por lo que saben los personajes (`vista.py`):
los PJ que juega una persona se ven enteros; los demás, solo por el lore.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import threading
from http.server import ThreadingHTTPServer

from .. import chat
from .http import MAX_CAMPANAS_SALA, MIN_CLAVE_SALA, Prohibido, SinNarrador
from .manejador import Manejador

__all__ = ["MAX_CAMPANAS_SALA", "Manejador", "Prohibido", "SinNarrador", "crear", "detectar_tailscale", "servir"]

def crear(host: str = "127.0.0.1", puerto: int = 8765, narrador: chat.Narrador | None = None,
          tailscale: dict | None = None, clave_sala: str | None = None) -> ThreadingHTTPServer:
    clave = clave_sala.strip() if isinstance(clave_sala, str) and clave_sala.strip() else None
    if clave is not None and len(clave) < MIN_CLAVE_SALA:
        # La clave abre la mesa a cualquiera que la tenga, por un túnel público: que no se adivine.
        raise ValueError(f"la clave de sala tiene que tener al menos {MIN_CLAVE_SALA} caracteres (o usa `--sala` y se genera sola)")
    servidor = ThreadingHTTPServer((host, puerto), Manejador)
    servidor.token = secrets.token_urlsafe(32)  # por ejecución: no se guarda en disco ni en la bitácora
    servidor.narrador = narrador
    servidor.tailscale = tailscale
    servidor.clave_sala = clave
    servidor.presencia = {}
    servidor.reclamos = {}
    servidor.campanas_sala = 0
    servidor.presencia_lock = threading.Lock()
    return servidor


def detectar_tailscale(usuarios: list[str] | None = None) -> dict:
    """El nombre del nodo en la tailnet y quién puede escribir: el dueño del nodo, o los indicados."""
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=10, check=True)
        datos = json.loads(r.stdout)
        propio = datos["Self"]
        host = propio["DNSName"].rstrip(".").lower()
        dueno = datos["User"][str(propio["UserID"])]["LoginName"]
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise RuntimeError(f"no pude leer el estado de Tailscale (`tailscale status --json`): {e}") from e
    return {"host": host, "usuarios": {u.strip().lower() for u in (usuarios or [dueno])}}


def servir(host: str = "127.0.0.1", puerto: int = 8765, agente: str | None = "hermes", comando: list[str] | None = None,
           tailscale: bool | None = None, usuarios: list[str] | None = None, clave_sala: str | None = None) -> None:
    narrador = chat.Narrador(agente or "agente", comando) if (agente or comando) else None
    ts = None
    if tailscale is True:
        ts = detectar_tailscale(usuarios)
    elif tailscale is None:
        try:
            ts = detectar_tailscale(usuarios)
        except RuntimeError:
            ts = None
    servidor = crear(host, puerto, narrador, ts, clave_sala=clave_sala)
    print(f"Visor en http://{host}:{servidor.server_address[1]}  (Ctrl+C para cerrar)", flush=True)
    if narrador:
        print(f"Narrador en el chat: {' '.join(narrador.comando)} (ACP)", flush=True)
    if servidor.clave_sala:
        print(f"Sala activa con clave: {servidor.clave_sala}  (añade ?sala={servidor.clave_sala} al link)", flush=True)
    if ts:
        print(f"Por Tailscale escriben: {', '.join(sorted(ts['usuarios']))} desde https://{ts['host']}:<puerto de `tailscale serve`>", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if narrador:
            narrador.cerrar()
        servidor.server_close()

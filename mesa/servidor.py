"""Servidor local del visor: solo lectura, solo 127.0.0.1 por defecto.

Sirve el visor, partida.json, la bitácora y las imágenes. Nunca sirve director.md
ni biblia.md: lo que está en partida.json es lo único que ven los jugadores.
"""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import estado
from .texto import slug_valido

VISOR = estado.RAIZ / "visor"
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")


class Manejador(BaseHTTPRequestHandler):
    server_version = "mesa-de-rol"

    def log_message(self, formato: str, *args) -> None:  # silencioso: el visor sondea cada segundo
        return

    def _enviar(self, codigo: int, cuerpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, datos, codigo: int = 200) -> None:
        self._enviar(codigo, json.dumps(datos, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _archivo(self, base: Path, relativo: str) -> None:
        base = base.resolve()
        objetivo = (base / unquote(relativo)).resolve()
        if not objetivo.is_relative_to(base) or not objetivo.is_file():
            self._json({"error": "no encontrado"}, 404)
            return
        tipo = mimetypes.guess_type(objetivo.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo.endswith("javascript"):
            tipo += "; charset=utf-8"
        self._enviar(200, objetivo.read_bytes(), tipo)

    def _slug(self, consulta: dict) -> str:
        slug = consulta.get("p", [None])[0] or estado.slug_activo()
        if not slug_valido(slug):
            raise ValueError("partida inválida")
        return slug

    def do_GET(self) -> None:
        url = urlparse(self.path)
        consulta = parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                return self._archivo(VISOR, "index.html")
            if url.path.startswith("/visor/"):
                return self._archivo(VISOR, url.path.removeprefix("/visor/"))
            if url.path == "/api/partidas":
                try:
                    activa = estado.slug_activo()
                except ValueError:
                    activa = None
                return self._json({"activa": activa, "partidas": estado.listar_partidas()})
            if url.path == "/api/estado":
                return self._json(estado.cargar(self._slug(consulta)))
            if url.path == "/api/eventos":
                desde = int(consulta.get("desde", ["0"])[0])
                limite = 400 if desde == 0 else None
                return self._json({"eventos": estado.leer_eventos(self._slug(consulta), desde, limite)})
            if url.path.startswith("/media/"):
                _, _, slug, *resto = url.path.split("/")
                if not slug_valido(slug):
                    raise ValueError("partida inválida")
                return self._archivo(estado.dir_partida(slug) / "imagenes", "/".join(resto))
            if url.path.startswith("/biblioteca/"):
                return self._archivo(estado.RAIZ / "biblioteca" / "imagenes", url.path.removeprefix("/biblioteca/"))
            self._json({"error": "no encontrado"}, 404)
        except FileNotFoundError as e:
            self._json({"error": str(e)}, 404)
        except ValueError as e:
            self._json({"error": str(e)}, 400)


def crear(host: str = "127.0.0.1", puerto: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, puerto), Manejador)


def servir(host: str = "127.0.0.1", puerto: int = 8765) -> None:
    servidor = crear(host, puerto)
    print(f"Visor en http://{host}:{servidor.server_address[1]}  (Ctrl+C para cerrar)", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()

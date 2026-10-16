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

from . import distribucion, estado
from .texto import slug_valido

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")

# Lo que el visor puede servir como medio. El SVG solo aparece en la tarjeta que genera
# `imagen ninguna` con valores controlados; se sirve enjaulado por si quedó uno de antes.
TIPOS_RASTER = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TIPOS_MEDIO = TIPOS_RASTER | {".svg"}
CSP_SVG = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


class Manejador(BaseHTTPRequestHandler):
    server_version = "mesa-de-rol"

    def log_message(self, formato: str, *args) -> None:  # silencioso: el visor sondea cada segundo
        return

    def _enviar(self, codigo: int, cuerpo: bytes, tipo: str, cabeceras: dict | None = None) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for nombre, valor in (cabeceras or {}).items():
            self.send_header(nombre, valor)
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, datos, codigo: int = 200) -> None:
        self._enviar(codigo, json.dumps(datos, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _archivo(self, base: Path, relativo: str, permitidos: set[str] | None = None) -> None:
        base = base.resolve()
        objetivo = (base / unquote(relativo)).resolve()
        if not objetivo.is_relative_to(base) or not objetivo.is_file():
            self._json({"error": "no encontrado"}, 404)
            return
        if permitidos is not None and objetivo.suffix.lower() not in permitidos:
            self._json({"error": "no encontrado"}, 404)
            return
        tipo = mimetypes.guess_type(objetivo.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo.endswith("javascript") or tipo.startswith("image/svg"):
            tipo += "; charset=utf-8"
        cabeceras = {"Content-Security-Policy": CSP_SVG} if tipo.startswith("image/svg") else None
        self._enviar(200, objetivo.read_bytes(), tipo, cabeceras)

    def _slug(self, consulta: dict) -> str:
        slug = consulta.get("p", [None])[0] or estado.slug_activo()
        if not slug_valido(slug):
            raise ValueError("partida inválida")
        return slug

    def do_GET(self) -> None:
        url = urlparse(self.path)
        consulta = parse_qs(url.query)
        try:
            visor = distribucion.visor()  # se resuelve por petición: el checkout manda si está
            if url.path in ("/", "/index.html"):
                return self._archivo(visor, "index.html")
            if url.path.startswith("/visor/"):
                return self._archivo(visor, url.path.removeprefix("/visor/"))
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
                return self._archivo(estado.dir_partida(slug) / "imagenes", "/".join(resto), TIPOS_MEDIO)
            if url.path.startswith("/biblioteca/"):
                return self._archivo(estado.RAIZ / "biblioteca" / "imagenes", url.path.removeprefix("/biblioteca/"), TIPOS_RASTER)
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

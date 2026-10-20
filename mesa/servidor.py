"""Servidor local del visor: solo 127.0.0.1 por defecto.

Sirve el visor, partida.json, la bitácora y las imágenes. Nunca sirve director.md
ni biblia.md: lo que está en partida.json es lo único que ven los jugadores.

Escribe una sola cosa: la memoria de la historia (hechos clave, «Hasta ahora» y
crónica), que el jugador corrige desde el visor. `POST /api/memoria` pasa por la
misma puerta que la CLI (`memoria.aplicar`), bajo el candado de la partida y con su
evento en la bitácora, y solo se acepta si:

- el cliente es este equipo (dirección de loopback) y el `Host` es local, para que
  una página ajena no llegue por DNS rebinding;
- trae el token de esta ejecución del servidor (`X-Mesa-Token`, que entrega
  `GET /api/visor` solo con `Host` local) y, si el navegador manda `Origin`, es de este
  equipo (cualquier puerto: un proxy local lo cambia);
- el cuerpo es JSON (lo que obliga a un preflight CORS que aquí nadie responde) y
  pesa menos de 16 KiB.

Nada más se escribe desde el navegador: fichas, dados y escena siguen siendo del narrador.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import secrets
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import bloqueo, chat, distribucion, estado, mapas, memoria
from .texto import slug_valido

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")

# Lo que el visor puede servir como medio. El SVG solo aparece en la tarjeta que genera
# `imagen ninguna` con valores controlados; se sirve enjaulado por si quedó uno de antes.
TIPOS_RASTER = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TIPOS_MEDIO = TIPOS_RASTER | {".svg"}
CSP_SVG = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
MAX_CUERPO = 16 * 1024
HOSTS_LOCALES = {"localhost", "127.0.0.1", "[::1]"}


def _es_loopback(direccion: str) -> bool:
    try:
        return ipaddress.ip_address(direccion).is_loopback
    except ValueError:
        return False


class Prohibido(Exception):
    """La petición de escritura no viene del visor local."""


class SinNarrador(Exception):
    """El visor se arrancó sin agente: el chat es de solo lectura."""


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

    def _nombre_host(self) -> str:
        host = (self.headers.get("Host") or "").strip().lower()
        return host.split("]")[0] + "]" if host.startswith("[") else host.rsplit(":", 1)[0]

    def _host_local(self) -> bool:
        return self._nombre_host() in HOSTS_LOCALES

    def _usuario_tailscale(self) -> str | None:
        """Con `servir --tailscale`: el usuario que `tailscale serve` acredita, si está autorizado.

        tailscaled atiende la conexión de la tailnet y la pasa a este servidor desde 127.0.0.1
        con `Host` del nodo (`<equipo>.<tailnet>.ts.net`) y la cabecera `Tailscale-User-Login`,
        que él mismo pone y que un cliente de fuera no puede falsificar.
        """
        ts = getattr(self.server, "tailscale", None)
        if not ts or not _es_loopback(self.client_address[0]) or self._nombre_host() != ts["host"]:
            return None
        login = (self.headers.get("Tailscale-User-Login") or "").strip().lower()
        return login if login in ts["usuarios"] else None

    def _puede_escribir(self) -> bool:
        return _es_loopback(self.client_address[0]) and (self._host_local() or self._usuario_tailscale() is not None)

    def _autor(self) -> str:
        if self._usuario_tailscale():
            return (self.headers.get("Tailscale-User-Name") or self._usuario_tailscale()).strip()[:80]
        return "jugador"

    def _exigir_visor_local(self) -> None:
        if not self._puede_escribir():
            raise Prohibido("desde aquí el visor es de solo lectura: se escribe desde este equipo (o por Tailscale con `servir --tailscale`)")
        # Un proxy local (la vista previa de un harness, por ejemplo) cambia el puerto del origen:
        # basta con que sea de este equipo, o el propio nodo de Tailscale. Una página de fuera no pasa, ni con token.
        origen = self.headers.get("Origin")
        if origen is not None:
            url = urlparse(origen)
            propios = {"localhost", "127.0.0.1", "::1"} | ({self.server.tailscale["host"]} if getattr(self.server, "tailscale", None) else set())
            if url.scheme not in ("http", "https") or (url.hostname or "") not in propios:
                raise Prohibido("origen ajeno al visor")
        token = (self.headers.get("X-Mesa-Token") or "").encode()
        if not secrets.compare_digest(token, self.server.token.encode()):
            raise Prohibido("falta el token del visor: recarga la página")

    def _leer_json(self) -> dict:
        if self.headers.get_content_type() != "application/json":
            raise ValueError("el cuerpo tiene que ser JSON")
        largo = int(self.headers.get("Content-Length") or 0)
        if not 0 < largo <= MAX_CUERPO:
            raise ValueError(f"el cuerpo tiene que pesar entre 1 byte y {MAX_CUERPO} bytes")
        cuerpo = json.loads(self.rfile.read(largo))
        if not isinstance(cuerpo, dict):
            raise ValueError("el cuerpo tiene que ser un objeto JSON")
        return cuerpo

    def _cambiar_memoria(self, slug: str, cuerpo: dict) -> dict:
        accion = cuerpo.get("accion")
        if not isinstance(accion, str):
            raise ValueError("falta «accion»")
        for campo in ("id", "texto", "categoria"):
            if cuerpo.get(campo) is not None and not isinstance(cuerpo[campo], str):
                raise ValueError(f"«{campo}» tiene que ser texto")
        numero = cuerpo.get("numero")
        if numero is not None and (not isinstance(numero, int) or isinstance(numero, bool)):
            raise ValueError("«numero» tiene que ser un entero")
        with bloqueo.candado(estado.ruta_candado(slug)):
            datos = estado.cargar(slug)
            evento, texto = memoria.aplicar(
                datos, accion, ident=cuerpo.get("id"), texto=cuerpo.get("texto"), categoria=cuerpo.get("categoria"),
                fijado=cuerpo.get("fijado") is True, numero=numero, autor="jugador",
            )
            (evento,) = estado.escribir(slug, datos=datos, eventos=[{**evento, "via": "visor"}])
        return {"ok": True, "texto": texto, "evento": evento, "memoria": datos["memoria"]}

    def _narrador(self) -> chat.Narrador:
        narrador = getattr(self.server, "narrador", None)
        if narrador is None:
            raise SinNarrador("este visor no tiene narrador: arráncalo con `bin/mesa servir --agente hermes` (o narra desde la terminal)")
        return narrador

    def _chat(self, accion: str, slug: str, cuerpo: dict) -> tuple[dict, int]:
        narrador = self._narrador()
        estado.dir_partida(slug)  # 404 legible si la partida no existe
        if accion == "":
            texto = cuerpo.get("texto")
            if not isinstance(texto, str):
                raise ValueError("falta «texto»")
            return {"ok": True, "mensaje": narrador.enviar(slug, texto, self._autor())}, 202
        if accion == "cancelar":
            return {"ok": narrador.cancelar(slug)}, 200
        if accion == "sesion-nueva":
            narrador.nueva_sesion(slug)
            return {"ok": True}, 200
        if accion == "agente":
            if not isinstance(cuerpo.get("agente"), str):
                raise ValueError("falta «agente»")
            narrador.cambiar_agente(slug, cuerpo["agente"])
            return {"ok": True, "narrador": narrador.vista(slug)}, 200
        if accion == "permiso":
            if not isinstance(cuerpo.get("id"), str):
                raise ValueError("falta «id»")
            narrador.responder_permiso(slug, cuerpo["id"], cuerpo.get("permitir") is True)
            return {"ok": True}, 200
        raise FileNotFoundError("no encontrado")

    def do_POST(self) -> None:
        url = urlparse(self.path)
        try:
            if url.path != "/api/memoria" and url.path != "/api/chat" and not url.path.startswith("/api/chat/"):
                return self._json({"error": "no encontrado"}, 404)
            self._exigir_visor_local()
            cuerpo = self._leer_json()
            slug = self._slug(parse_qs(url.query))
            if url.path == "/api/memoria":
                return self._json(self._cambiar_memoria(slug, cuerpo))
            respuesta, codigo = self._chat(url.path.removeprefix("/api/chat").strip("/"), slug, cuerpo)
            return self._json(respuesta, codigo)
        except Prohibido as e:
            self._json({"error": str(e)}, 403)
        except FileNotFoundError as e:
            self._json({"error": str(e)}, 404)
        except ValueError as e:  # incluye JSON mal formado y Content-Length inválido
            self._json({"error": str(e)}, 400)
        except chat.Ocupado as e:
            self._json({"error": str(e)}, 409)
        except SinNarrador as e:
            self._json({"error": str(e)}, 409)
        except RuntimeError as e:  # candado ocupado o conflicto: que el jugador reintente
            self._json({"error": str(e)}, 503)

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
            if url.path == "/api/visor":
                escritura = self._puede_escribir()
                return self._json({
                    "escritura": escritura, "token": self.server.token if escritura else None,
                    "chat": getattr(self.server, "narrador", None) is not None, "autor": self._autor() if escritura else None,
                })
            if url.path == "/api/chat":
                slug = self._slug(consulta)
                desde = int(consulta.get("desde", ["0"])[0])
                narrador = getattr(self.server, "narrador", None)
                return self._json({
                    "mensajes": chat.leer_chat(slug, desde),
                    "narrador": narrador.vista(slug) if narrador else {"activo": False},
                })
            if url.path == "/api/estado":
                datos = estado.cargar(self._slug(consulta))
                datos["memoria_uso"] = memoria.uso(datos)  # derivado para el visor: qué entra al contexto
                return self._json(datos)
            if url.path == "/api/eventos":
                desde = int(consulta.get("desde", ["0"])[0])
                limite = 400 if desde == 0 else None
                return self._json({"eventos": estado.leer_eventos(self._slug(consulta), desde, limite)})
            if url.path == "/api/zona":
                # La proyección táctica la resuelve el motor, no el navegador: el visor
                # pinta lo que sale de aquí, sin una segunda copia de las reglas del SRD.
                # `origen`/`destino` son la medición que el jugador tiene en pantalla,
                # no estado de la partida, así que viajan en la consulta.
                datos = estado.cargar(self._slug(consulta))
                def uno(clave: str) -> str | None:
                    return (consulta.get(clave, [""])[0] or "").strip() or None
                proyeccion = mapas.proyeccion_zona(
                    datos,
                    origen=uno("origen"), destino=uno("destino"),
                    forma=uno("forma"),
                    tamano=float(uno("tamano")) if uno("tamano") else None,
                )
                return self._json(proyeccion)
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
        except RuntimeError as e:  # conflicto o candado ocupado: un JSON legible, no una conexión rota
            self._json({"error": str(e)}, 503)


def crear(host: str = "127.0.0.1", puerto: int = 8765, narrador: chat.Narrador | None = None,
          tailscale: dict | None = None) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer((host, puerto), Manejador)
    servidor.token = secrets.token_urlsafe(32)  # por ejecución: no se guarda en disco ni en la bitácora
    servidor.narrador = narrador
    servidor.tailscale = tailscale
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
           tailscale: bool | None = None, usuarios: list[str] | None = None) -> None:
    narrador = chat.Narrador(agente or "agente", comando) if (agente or comando) else None
    ts = None
    if tailscale is True:
        ts = detectar_tailscale(usuarios)
    elif tailscale is None:
        try:
            ts = detectar_tailscale(usuarios)
        except RuntimeError:
            ts = None
    servidor = crear(host, puerto, narrador, ts)
    print(f"Visor en http://{host}:{servidor.server_address[1]}  (Ctrl+C para cerrar)", flush=True)
    if narrador:
        print(f"Narrador en el chat: {' '.join(narrador.comando)} (ACP)", flush=True)
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

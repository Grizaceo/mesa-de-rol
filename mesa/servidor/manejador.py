"""Manejador HTTP del visor: GET de la mesa y POST de escritura."""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .. import chat, distribucion, estado, mapas, memoria, vista
from ..texto import slug_valido
from .campanas import CampanaMixin
from .http import (
    CSP_SVG, CSP_VISOR, Prohibido, SinNarrador, TIPOS_MEDIO, TIPOS_RASTER,
)
from .sala import SalaMixin
from .tiradas import TiradasMixin

class Manejador(SalaMixin, CampanaMixin, TiradasMixin, BaseHTTPRequestHandler):
    server_version = "mesa-de-rol"
    timeout = 30  # una conexión que no termina de mandar su petición no retiene un hilo para siempre

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
        politica = CSP_SVG if tipo.startswith("image/svg") else CSP_VISOR if tipo.startswith("text/html") else None
        self._enviar(200, objetivo.read_bytes(), tipo, {"Content-Security-Policy": politica} if politica else None)

    def _narrador(self) -> chat.Narrador:
        narrador = getattr(self.server, "narrador", None)
        if narrador is None:
            raise SinNarrador("este visor no tiene narrador: arráncalo con `bin/mesa servir --agente hermes` (o narra desde la terminal)")
        return narrador

    def _chat(self, accion: str, slug: str, cuerpo: dict) -> tuple[dict, int]:
        narrador = self._narrador()
        estado.dir_partida(slug)  # 404 legible si la partida no existe
        # Elegir el DM (de la lista fija de agentes) lo puede cualquiera de la mesa; aprobar lo que
        # el agente quiere ejecutar en el equipo y reiniciar su sesión, solo el anfitrión.
        solo_anfitrion = {
            "sesion-nueva": "Abrir una sesión nueva del narrador",
            "permiso": "Responder a los permisos del agente",
        }
        if accion in solo_anfitrion:
            self._exigir_anfitrion(solo_anfitrion[accion])
        if accion == "":
            texto = cuerpo.get("texto")
            if not isinstance(texto, str):
                raise ValueError("falta «texto»")
            autor = self._autor_de(slug, cuerpo.get("autor"))
            fuera_de_personaje = bool(cuerpo.get("fuera_de_personaje"))
            return {"ok": True, "mensaje": narrador.enviar(slug, texto, autor, fuera_de_personaje=fuera_de_personaje)}, 202
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
            if url.path not in ("/api/memoria", "/api/campana", "/api/tirar", "/api/reclamar", "/api/chat") and not url.path.startswith("/api/chat/"):
                return self._json({"error": "no encontrado"}, 404)
            self._exigir_visor_local()
            cuerpo = self._leer_json()
            consulta = parse_qs(url.query)
            if url.path == "/api/campana":
                return self._json(self._configurar_campana(consulta, cuerpo))
            slug = self._slug(consulta)
            if url.path == "/api/reclamar":
                return self._json(self._reclamar(slug, cuerpo))
            if url.path == "/api/memoria":
                return self._json(self._cambiar_memoria(slug, cuerpo))
            if url.path == "/api/tirar":
                return self._json(self._tirar_desde_visor(slug, cuerpo))
            respuesta, codigo = self._chat(url.path.removeprefix("/api/chat").strip("/"), slug, cuerpo)
            return self._json(respuesta, codigo)
        except Prohibido as e:
            self._json({"error": str(e)}, 403)
        except FileNotFoundError as e:
            self._json({"error": str(e)}, 404)
        except ValueError as e:  # incluye JSON mal formado y Content-Length inválido
            self._json({"error": str(e)}, 400)
        except (TypeError, OverflowError):  # un campo con un tipo que el motor no espera: 400, no una conexión cortada
            self._json({"error": "algún campo trae un tipo de dato inválido"}, 400)
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
            if url.path.startswith("/api/") and url.path != "/api/visor" and not self._puede_leer():
                raise Prohibido("esta mesa es privada: entra con la clave de sala")
            if url.path == "/api/partidas":
                try:
                    activa = estado.slug_activo()
                except ValueError:
                    activa = None
                return self._json({"activa": activa, "partidas": estado.listar_partidas()})
            if url.path == "/api/visor":
                escritura = self._puede_escribir()
                pedida = consulta.get("p", [""])[0]
                return self._json({
                    "escritura": escritura, "token": self.server.token if escritura else None,
                    "chat": getattr(self.server, "narrador", None) is not None, "autor": self._autor() if escritura else None,
                    "sala": bool(getattr(self.server, "clave_sala", None)),
                    "anfitrion": self._es_anfitrion(), "lectura": self._puede_leer(),
                    "pj": self._pj_reclamado(pedida) if escritura and slug_valido(pedida or "") else None,
                })
            if url.path == "/api/chat":
                slug = self._slug(consulta)
                desde = int(consulta.get("desde", ["0"])[0])
                pol = vista.politica(estado.cargar(slug))
                narrador = getattr(self.server, "narrador", None)
                vista_narrador = narrador.vista(slug) if narrador else {"activo": False}
                if vista_narrador.get("en_curso"):
                    vista_narrador["en_curso"]["partes"] = vista.chat([{"rol": "narrador", "partes": vista_narrador["en_curso"]["partes"]}], pol)[0]["partes"]
                respuesta_chat = {"mensajes": vista.chat(chat.leer_chat(slug, desde), pol), "narrador": vista_narrador}
                if self.headers.get("X-Mesa-Cliente"):
                    respuesta_chat["conectados"] = self._presencia(slug)
                return self._json(respuesta_chat)
            if url.path == "/api/estado":
                datos = estado.cargar(self._slug(consulta))
                publico = vista.partida(datos)  # lo que saben los personajes, no lo que sabe el narrador
                publico["memoria_uso"] = memoria.uso(datos)  # derivado para el visor: qué entra al contexto
                return self._json(publico)
            if url.path == "/api/eventos":
                slug = self._slug(consulta)
                desde = int(consulta.get("desde", ["0"])[0])
                limite = 400 if desde == 0 else None
                return self._json({"eventos": vista.eventos(estado.cargar(slug), estado.leer_eventos(slug, desde, limite))})
            if url.path == "/api/zona":
                # La proyección táctica la resuelve el motor, no el navegador: el visor
                # pinta lo que sale de aquí, sin una segunda copia de las reglas del SRD.
                # `origen`/`destino` son la medición que el jugador tiene en pantalla,
                # no estado de la partida, así que viajan en la consulta (con el nombre público).
                datos = estado.cargar(self._slug(consulta))
                pol = vista.politica(datos)
                def uno(clave: str) -> str | None:
                    return (consulta.get(clave, [""])[0] or "").strip() or None
                proyeccion = mapas.proyeccion_zona(
                    datos,
                    origen=vista.nombre_real(pol, uno("origen")), destino=vista.nombre_real(pol, uno("destino")),
                    forma=uno("forma"),
                    tamano=float(uno("tamano")) if uno("tamano") else None,
                )
                return self._json(vista.zona(proyeccion, pol))
            if url.path.startswith("/media/"):
                _, _, slug, *resto = url.path.split("/")
                if not slug_valido(slug):
                    raise ValueError("partida inválida")
                return self._archivo(estado.dir_partida(slug) / "imagenes", "/".join(resto), TIPOS_MEDIO)
            if url.path.startswith("/biblioteca/"):
                return self._archivo(estado.RAIZ / "biblioteca" / "imagenes", url.path.removeprefix("/biblioteca/"), TIPOS_RASTER)
            self._json({"error": "no encontrado"}, 404)
        except Prohibido as e:
            self._json({"error": str(e)}, 403)
        except FileNotFoundError as e:
            self._json({"error": str(e)}, 404)
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except RuntimeError as e:  # conflicto o candado ocupado: un JSON legible, no una conexión rota
            self._json({"error": str(e)}, 503)

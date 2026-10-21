"""Servidor local del visor: solo 127.0.0.1 por defecto.

Sirve el visor, la partida, la bitácora y las imágenes. Nunca sirve director.md ni
biblia.md, y la partida sale filtrada por lo que saben los personajes (`vista.py`):
los PJ que juega una persona se ven enteros; los demás, solo por el lore.

Quién escribe:

- **El anfitrión**: este equipo (dirección de loopback y `Host` local, lo que corta el
  DNS rebinding) o el dueño del nodo por `servir --tailscale`. Puede todo lo del visor.
- **Un invitado de la sala** (`servir --sala`, cabecera `X-Mesa-Sala`): juega con el PJ
  que reclamó (`POST /api/reclamar`): chat, tiradas y su propia ficha, y también crea o
  configura campañas (nunca pisa PJ ni una biblia escrita a mano; hasta MAX_CAMPANAS_SALA
  nuevas por arranque). No aprueba permisos del agente ni cambia de agente o de sesión:
  eso pone a trabajar herramientas del equipo y es del anfitrión.

Toda escritura trae además el token de esta ejecución (`X-Mesa-Token`, que entrega
`GET /api/visor` a quien puede escribir), un `Origin` propio si el navegador lo manda y
un cuerpo JSON de menos de 16 KiB (lo que obliga a un preflight CORS que aquí nadie
responde). Con sala activa, leer la API también pide la clave.

Las escrituras pasan por el motor de la CLI, bajo el candado de la partida y con su
evento en la bitácora (`via: visor`).
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import mimetypes
import re
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import bloqueo, chat, dados, distribucion, esquemas, estado, mapas, memoria, reglas, reglas_2024, vista
from .texto import con_signo, norm, slug_valido

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


class Manejador(BaseHTTPRequestHandler):
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

    def _tiene_clave_sala(self) -> bool:
        clave = getattr(self.server, "clave_sala", None)
        if not clave:
            return False
        recibida = (self.headers.get("X-Mesa-Sala") or "").strip()
        return bool(recibida) and secrets.compare_digest(recibida.encode(), clave.encode())

    def _es_anfitrion(self) -> bool:
        """Quien lleva la mesa: este equipo (loopback y `Host` local) o un usuario autorizado por Tailscale."""
        return _es_loopback(self.client_address[0]) and (self._host_local() or self._usuario_tailscale() is not None)

    def _puede_escribir(self) -> bool:
        return self._es_anfitrion() or self._tiene_clave_sala()

    def _puede_leer(self) -> bool:
        """Sin sala, leer es libre (el servidor escucha en 127.0.0.1); con sala, pide la clave o ser el anfitrión."""
        return not getattr(self.server, "clave_sala", None) or self._puede_escribir()

    def _exigir_anfitrion(self, que: str) -> None:
        if not self._es_anfitrion():
            raise Prohibido(f"{que} es del anfitrión de la mesa (desde su equipo o por Tailscale), no de la sala")

    def _token_reclamo(self) -> str:
        return (self.headers.get("X-Mesa-Reclamo") or "").strip()[:64]

    def _pj_reclamado(self, slug: str) -> str | None:
        """El PJ que este cliente reclamó en la sala, si sigue vigente (se renueva al sondear)."""
        token = self._token_reclamo()
        if not token:
            return None
        ahora_t = time.monotonic()
        with self.server.presencia_lock:
            info = self.server.reclamos.get(slug, {}).get(token)
            if info is None or ahora_t - info["ts"] > TTL_RECLAMO:
                return None
            info["ts"] = ahora_t
            return info["pj"]

    def _reclamar(self, slug: str, cuerpo: dict) -> dict:
        """Este cliente juega con un PJ: firma con su nombre y solo actúa con su ficha."""
        pedido = cuerpo.get("pj")
        if not isinstance(pedido, str) or not pedido.strip():
            raise ValueError("falta «pj»: el personaje que juegas")
        datos = estado.cargar(slug)
        clave = norm(pedido)
        ficha = next((p for p in datos.get("personajes") or [] if clave in {norm(p.get("nombre", "")), norm(p.get("id", ""))}), None)
        if ficha is None:
            nombres = ", ".join(p["nombre"] for p in datos.get("personajes") or []) or "ninguno"
            raise ValueError(f"no hay un PJ llamado {pedido.strip()[:40]!r}; PJ: {nombres}")
        if not vista.humano(ficha):
            raise ValueError(f"a {ficha['nombre']} lo lleva el narrador (`piloto: narrador`): para jugarlo, `bin/mesa piloto {ficha['nombre']} jugador`")
        anterior = self._token_reclamo()
        ahora_t = time.monotonic()
        with self.server.presencia_lock:
            sala = self.server.reclamos.setdefault(slug, {})
            for token, info in list(sala.items()):
                if ahora_t - info["ts"] > TTL_RECLAMO:
                    sala.pop(token)
            if not self._es_anfitrion() and any(info["pj"] == ficha["nombre"] and token != anterior for token, info in sala.items()):
                raise chat.Ocupado(f"{ficha['nombre']} ya lo juega otra persona en la sala: elige otro PJ")
            sala.pop(anterior, None)
            token = secrets.token_urlsafe(18)
            sala[token] = {"pj": ficha["nombre"], "ts": ahora_t}
        return {"ok": True, "pj": ficha["nombre"], "reclamo": token}

    def _autor(self, sugerido: str | None = None) -> str:
        for candidato in (sugerido, self.headers.get("X-Mesa-Autor")):
            if isinstance(candidato, str) and candidato.strip():
                return candidato.strip()[:40]
        if self._usuario_tailscale():
            return (self.headers.get("Tailscale-User-Name") or self._usuario_tailscale()).strip()[:80]
        return "jugador"

    def _autor_de(self, slug: str, sugerido=None) -> str:
        """Quién firma: el anfitrión elige (en su pantalla juegan varios); un invitado es siempre su PJ."""
        if self._es_anfitrion():
            return self._autor(sugerido)
        pj = self._pj_reclamado(slug)
        if pj is None:
            raise Prohibido("elige tu personaje («Juego como») antes de escribir en la sala")
        if isinstance(sugerido, str) and sugerido.strip() and norm(sugerido) != norm(pj):
            raise Prohibido(f"en la sala hablas como {pj}, no como {sugerido.strip()[:40]}")
        return pj

    def _presencia(self, slug: str) -> dict:
        """Quién está mirando esta partida: el PJ reclamado, o «Espectador»; el anfitrión dice a quién lleva."""
        ahora_t = time.monotonic()
        cliente = (self.headers.get("X-Mesa-Cliente") or "").strip()[:48]
        pj = self._pj_reclamado(slug)
        if pj:
            nombre = pj
        elif self._es_anfitrion():
            nombre = unquote((self.headers.get("X-Mesa-Jugador") or "").strip())[:40] or "Anfitrión"
        else:
            nombre = "Espectador"
        with self.server.presencia_lock:
            mapa = self.server.presencia
            for otro in list(mapa):
                for cid in [c for c, info in mapa[otro].items() if ahora_t - info["ts"] > TTL_PRESENCIA]:
                    mapa[otro].pop(cid, None)
                if not mapa[otro] and otro != slug:
                    mapa.pop(otro)
            sala_p = mapa.setdefault(slug, {})
            if cliente and (cliente in sala_p or len(sala_p) < MAX_PRESENCIA):
                sala_p[cliente] = {"ts": ahora_t, "nombre": nombre}
            nombres = [x["nombre"] for x in sala_p.values()]
        return {"total": len(nombres), "jugadores": nombres}

    def _exigir_visor_local(self) -> None:
        if not self._puede_escribir():
            raise Prohibido("desde aquí el visor es de solo lectura: se escribe desde este equipo, por Tailscale o con la clave de sala")
        # Un proxy local (la vista previa de un harness, por ejemplo) cambia el puerto del origen:
        # basta con que sea de este equipo, el propio nodo de Tailscale o el host de la sala autenticada.
        origen = self.headers.get("Origin")
        if origen is not None:
            url = urlparse(origen)
            propios = {"localhost", "127.0.0.1", "::1"} | ({self.server.tailscale["host"]} if getattr(self.server, "tailscale", None) else set())
            if self._tiene_clave_sala():
                propios.add(self._nombre_host())
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
        try:
            cuerpo = json.loads(self.rfile.read(largo), parse_constant=_rechazar_constante, parse_float=_float_finito)
        except RecursionError:
            raise ValueError("el JSON está demasiado anidado") from None
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

    def _crear_partida(self, base: str, titulo: str) -> str:
        """Una partida nueva con un slug libre; si otro la crea a la vez, se prueba el siguiente."""
        base_slug = re.sub(r"[^a-z0-9]+", "-", norm(base)).strip("-")[:48].strip("-") or "campana"
        for n in range(1, 200):
            slug = base_slug if n == 1 else f"{base_slug}-{n}"
            if (estado.dir_partidas() / slug).exists():
                continue
            try:
                estado.nueva_partida(slug, titulo)
            except FileExistsError:
                continue
            return slug
        raise ValueError("ya hay demasiadas campañas con ese nombre: elige otro título")

    @staticmethod
    def _sumar_personajes(datos: dict, pjs_txt: str, reemplazar: bool) -> list[str]:
        """Añade los PJ nuevos de la lista; los que ya existen no se tocan (salvo la ficha de muestra de una partida nueva)."""
        if esquemas.version_de(datos) != esquemas.VERSION_2024:
            return ["en una partida d20-simple los personajes los crea el narrador: no se añadió ninguno"]
        existentes = [] if reemplazar else list(datos.get("personajes") or [])
        claves = {norm(p.get(c, "")) for p in existentes for c in ("nombre", "id")} - {""}
        nuevos, avisos = [], []
        for item in [x.strip() for x in re.split(r"[\n,;]+", pjs_txt) if x.strip()][:6]:
            m = re.match(r"^([^(–\-:]+?)(?:\s*[\(–\-:]\s*([^)]+)\)?\s*)?$", item)
            nombre_pj = (m.group(1) if m else item).strip()[:40]
            rol_pj = (m.group(2) if m and m.group(2) else "Aventurero").strip()[:80]
            if not nombre_pj:
                continue
            if norm(nombre_pj) in claves:
                if not reemplazar:
                    avisos.append(f"{nombre_pj} ya está en la partida: su ficha no se tocó")
                continue
            claves.add(norm(nombre_pj))
            nuevos.append(reglas_2024.ficha_inicial(
                nombre_pj, rol_pj, len(existentes) + len(nuevos), monedas=reglas_2024.monedas_de(datos.get("ambientacion") or {}),
            ))
        if nuevos:
            datos["personajes"] = existentes + nuevos
        return avisos

    @staticmethod
    def _biblia_rehacible(ruta: Path) -> bool:
        """Solo se escribe una biblia que no existe, que es la de la plantilla o que generó el visor y nadie editó."""
        if not ruta.exists():
            return True
        actual = ruta.read_text(encoding="utf-8")
        plantilla = distribucion.plantilla() / "biblia.md"
        if plantilla.exists() and actual == plantilla.read_text(encoding="utf-8"):
            return True
        marca = MARCA_BIBLIA.match(actual)
        return bool(marca) and _huella(actual[marca.end():]) == marca.group(1)

    def _eliminar_campana(self, slug: str, confirmar: str) -> dict:
        """La campaña va a `partidas/.papelera/` (se recupera moviéndola de vuelta), nunca se borra en el acto.

        Hay que escribir su nombre corto; la partida activa del narrador no se elimina, y la sala
        solo elimina campañas que creó la sala.
        """
        if confirmar != slug:
            raise ValueError(f"para eliminarla, escribe su nombre corto exacto: {slug}")
        try:
            activa = estado.slug_activo()
        except ValueError:
            activa = None
        if slug == activa:
            raise ValueError("es la partida activa del narrador: cambia antes de partida (`bin/mesa usar <otra>`)")
        if not self._es_anfitrion() and estado.cargar(slug).get("creada_por") != "sala":
            raise Prohibido("desde la sala solo se eliminan campañas creadas por la sala; las demás, el anfitrión")
        papelera = estado.dir_partidas() / ".papelera"
        papelera.mkdir(exist_ok=True)
        destino = papelera / f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}"
        with bloqueo.candado(estado.ruta_candado(slug)):
            estado.dir_partida(slug).rename(destino)
        return {"ok": True, "eliminada": slug, "papelera": str(destino.relative_to(estado.RAIZ))}

    def _configurar_campana(self, consulta: dict, cuerpo: dict) -> dict:
        modo = _texto(cuerpo, "modo", 20).lower() or "configurar"
        if modo not in ("nueva", "configurar", "eliminar"):
            raise ValueError(f"modo de campaña desconocido: {modo!r} (valen: nueva, configurar, eliminar)")
        if modo == "eliminar":
            return self._eliminar_campana(self._slug(consulta), _texto(cuerpo, "confirmar", 64))
        titulo = _texto(cuerpo, "titulo", 100)
        if modo == "nueva":
            if not titulo:
                raise ValueError("falta el título de la campaña")
            if not self._es_anfitrion():  # la sala también crea campañas, con un tope para que nadie llene el disco
                with self.server.presencia_lock:
                    if self.server.campanas_sala >= MAX_CAMPANAS_SALA:
                        raise ValueError(f"la sala ya creó {MAX_CAMPANAS_SALA} campañas en esta sesión: la siguiente la crea el anfitrión")
                    self.server.campanas_sala += 1
            slug = self._crear_partida(_texto(cuerpo, "slug", 100) or titulo, titulo)
        else:
            slug = self._slug(consulta)

        epoca = _texto(cuerpo, "epoca", 200)
        lugar = _texto(cuerpo, "lugar", 200)
        estilo_visual = _texto(cuerpo, "estilo_visual", 300)
        tono_raw = cuerpo.get("tono")
        if isinstance(tono_raw, list):
            tonos = [str(x).strip()[:40] for x in tono_raw if str(x).strip()][:10]
        else:
            tonos = [x.strip()[:40] for x in re.split(r"[,;]+", _texto(cuerpo, "tono", 400)) if x.strip()][:10]
        idea = _texto(cuerpo, "idea", 1500)
        pjs_txt = _texto(cuerpo, "personajes", 500)
        avisos: list[str] = []

        with bloqueo.candado(estado.ruta_candado(slug)):
            datos = estado.cargar(slug)
            if titulo:
                datos["titulo"] = titulo
            if modo == "nueva" and not self._es_anfitrion():
                datos["creada_por"] = "sala"  # la sala puede eliminar lo que ella creó
            amb = datos.setdefault("ambientacion", {})
            if epoca or modo == "nueva":
                amb["epoca"] = epoca
            if lugar or modo == "nueva":
                amb["lugar"] = lugar
            if estilo_visual or modo == "nueva":
                amb["estilo_visual"] = estilo_visual
            if tonos or modo == "nueva":
                amb["tono"] = tonos
            # Las monedas siguen a la ambientación en el acto (oro y cobre solo en fantasía) y las fichas con ellas.
            nuevas = reglas_2024.monedas_de({k: v for k, v in amb.items() if k != "monedas"})
            if amb.get("monedas") != nuevas and esquemas.version_de(datos) == esquemas.VERSION_2024:
                amb["monedas"] = nuevas
                for p in datos.get("personajes") or []:
                    previas = p.get("monedas") if isinstance(p.get("monedas"), dict) else {}
                    p["monedas"] = {m: int(previas.get(m, 0) or 0) for m in nuevas}
            if pjs_txt:
                avisos += self._sumar_personajes(datos, pjs_txt, reemplazar=modo == "nueva")

            biblia_ruta = estado.dir_partida(slug) / "biblia.md"
            rehacer_biblia = self._biblia_rehacible(biblia_ruta)
            lineas_biblia = [
                f"# Biblia — {datos.get('titulo', slug)}",
                "",
                "## 1. Estilo y tono",
                f"- **Reglamento:** `{datos.get('reglamento', 'dnd-2024')}`",
                f"- **Tono:** {', '.join(amb.get('tono') or []) or 'Aventura'}",
                f"- **Estilo visual:** {amb.get('estilo_visual') or 'Por definir en mesa'}",
                "",
                "## 2. Mundo y ambientación",
                f"- **Época:** {amb.get('epoca') or 'Por definir'}",
                f"- **Lugar inicial:** {amb.get('lugar') or 'Por definir'}",
            ]
            if idea:
                lineas_biblia += ["", "## 3. Propuesta de campaña de los jugadores", idea]
            lineas_biblia += [
                "",
                "## 4. Personajes jugadores",
                *[f"- **{p['nombre']}** ({p.get('rol') or 'Nivel 1'})" for p in datos.get("personajes", [])],
                "",
            ]
            origen = consulta.get("p", [""])[0] or ""
            autor = self._autor(cuerpo.get("autor")) if self._es_anfitrion() else (
                (self._pj_reclamado(origen) if slug_valido(origen) else None) or "invitado de la sala"
            )
            (evento,) = estado.escribir(
                slug,
                datos=datos,
                eventos=[{"tipo": "ambientacion", "titulo": datos.get("titulo", slug), "idea": idea, "autor": autor, "via": "visor"}],
            )
            # Después del commit: si la partida no se guardó, la biblia tampoco cambia.
            if rehacer_biblia:
                cuerpo_biblia = "\n".join(lineas_biblia)
                estado._escribir_texto(biblia_ruta, f"<!-- generada por el visor · {_huella(cuerpo_biblia)} -->\n{cuerpo_biblia}")
            else:
                avisos.append("biblia.md ya estaba escrita a mano: no se tocó; la ambientación queda en la partida")

        iniciado = False
        if cuerpo.get("iniciar_chat") and getattr(self.server, "narrador", None) is not None:
            partes_prompt = [f"Queremos arrancar la campaña «{datos.get('titulo', slug)}»."]
            if amb.get("epoca") or amb.get("lugar"):
                partes_prompt.append(f"Ambientación: {', '.join(x for x in (amb.get('epoca'), amb.get('lugar')) if x)}.")
            if amb.get("tono"):
                partes_prompt.append(f"Tono: {', '.join(amb['tono'])}.")
            if amb.get("estilo_visual"):
                partes_prompt.append(f"Estilo visual: {amb['estilo_visual']}.")
            if pjs_txt:
                partes_prompt.append(f"Personajes iniciales: {pjs_txt}.")
            if idea:
                partes_prompt.append(f"Lo que queremos jugar: {idea}")
            partes_prompt.append(
                "Por favor configura la Escena 1 (con su mapa táctico y posiciones de nuestros personajes), "
                "ajusta nuestras fichas D&D 2024 si hace falta y ábrenos la primera escena."
            )
            try:
                self._narrador().enviar(slug, " ".join(partes_prompt), "Mesa")
                iniciado = True
            except chat.Ocupado:
                iniciado = False

        return {"ok": True, "slug": slug, "titulo": datos.get("titulo", slug), "evento": evento, "iniciado": iniciado, "avisos": avisos}

    def _ficha_del_jugador(self, slug: str, datos: dict, quien) -> dict:
        """El PJ que actúa desde el visor: el anfitrión elige; un invitado, solo el suyo. Nunca un enemigo."""
        pjs = datos.get("personajes") or []
        if not pjs:
            raise ValueError("no hay personajes en la partida")
        if not self._es_anfitrion():
            propio = self._pj_reclamado(slug)
            if propio is None:
                raise Prohibido("elige tu personaje («Juego como») antes de tirar")
            if isinstance(quien, str) and quien.strip() and norm(quien) != norm(propio):
                raise Prohibido(f"en la sala actúas con {propio}: las fichas de los demás son suyas")
            quien = propio
        if not isinstance(quien, str) or not quien.strip():
            raise ValueError("falta «quien»: el personaje que actúa")
        clave = norm(quien)
        ficha = next((p for p in pjs if clave in {norm(p.get("nombre", "")), norm(p.get("id", ""))}), None)
        if ficha is None:
            raise ValueError(
                f"{quien.strip()[:40]!r} no es un PJ de esta partida (PJ: {', '.join(p['nombre'] for p in pjs)}); "
                "las fichas de los enemigos las lleva el narrador"
            )
        return ficha

    @staticmethod
    def _objeto(ficha: dict, nombre: str) -> dict:
        clave = norm(nombre or "")
        elegido = next((x for x in ficha.get("equipo") or [] if clave and norm(x.get("nombre", "")) == clave), None)
        if elegido is None:
            raise ValueError(f"no encuentro {nombre!r} en el inventario de {ficha['nombre']}")
        return elegido

    @staticmethod
    def _liberar_ranura(ficha: dict, elegido: dict) -> None:
        """Lo que ocupaba la misma ranura se guarda (y su bono de CA deja de contar)."""
        ranura = str(elegido.get("ranura") or "").strip()
        if not ranura:
            return
        for x in ficha.get("equipo") or []:
            if x is not elegido and x.get("equipado") and str(x.get("ranura") or "").strip() == ranura:
                x["equipado"] = False
                _ajustar_ca(ficha, -_bono_ca(x))

    @staticmethod
    def _aplicar_trasfondo(datos: dict, ficha: dict, cuerpo: dict, es_2024: bool) -> dict:
        """El jugador cuenta de dónde viene su PJ y qué le sube (SRD 5.2.1: +2/+1 o +1/+1/+1, tope 20)
        y, como regla de la casa opcional, qué le baja (−1). Rehacerlo deshace el trasfondo anterior."""
        if not es_2024:
            raise ValueError("el trasfondo con características es de D&D 2024; en d20-simple escríbelo en la biblia")
        def mapa(campo):
            valor = cuerpo.get(campo) or {}
            if not isinstance(valor, dict):
                raise ValueError(f"«{campo}» tiene que ser {{característica: número}}")
            return {reglas_2024.resolver_atributo(k)[0]: _numero(valor, k, minimo=-2, maximo=2) for k in valor}
        sube, baja = mapa("sube"), mapa("baja")
        if any(v < 0 for v in sube.values()) or sorted(sube.values()) not in ([], [1, 2], [1, 1, 1]):
            raise ValueError("el trasfondo sube +2 y +1, o +1 a tres características")
        if any(v not in (-1,) for v in baja.values()) or len(baja) > 1:
            raise ValueError("como regla de la casa, el trasfondo baja como mucho una característica en 1")
        habilidades = [str(h).strip()[:40] for h in (cuerpo.get("habilidades") or []) if str(h).strip()][:2]
        attrs = ficha.setdefault("atributos", {})
        previo = ficha.get("trasfondo") or {}
        for k, v in {**(previo.get("sube") or {}), **(previo.get("baja") or {})}.items():
            attrs[k] = int(attrs.get(k, 10)) - int(v)
        for k, v in list(sube.items()) + list(baja.items()):
            attrs[k] = int(attrs.get(k, 10)) + int(v)
            if not 1 <= attrs[k] <= 20:
                raise ValueError(f"{esquemas.NOMBRES_2024[k]} quedaría en {attrs[k]}: el tope es 20")
        comp = ficha.setdefault("competencias", {})
        comp["habilidades"] = [h for h in comp.get("habilidades") or [] if h not in (previo.get("habilidades") or [])] + [
            h for h in habilidades if h not in (comp.get("habilidades") or [])]
        nombre = _texto(cuerpo, "nombre", 60) or "Trasfondo"
        ficha["trasfondo"] = {"nombre": nombre, "historia": _texto(cuerpo, "historia", 1500), "sube": sube, "baja": baja, "habilidades": habilidades}
        cambios = ", ".join(f"{esquemas.NOMBRES_2024[k]} {con_signo(v)}" for k, v in {**sube, **baja}.items()) or "sin cambios de características"
        return {"tipo": "nota", "texto": f"{ficha['nombre']} · trasfondo «{nombre}»: {cambios}" + (f"; habilidades: {', '.join(habilidades)}" if habilidades else "")}

    @staticmethod
    def _texto_publico(pol: dict, evento: dict, texto: str) -> str:
        if evento.get("tipo") in ("prueba", "ataque"):
            return reglas.describir_prueba(vista.evento(pol, evento))
        return vista.texto(pol, texto)

    def _tirar_desde_visor(self, slug: str, cuerpo: dict) -> dict:
        accion = _texto(cuerpo, "accion", 30).lower() or "prueba"
        modo_req = _texto(cuerpo, "modo", 20).lower() or "normal"
        ventaja = "declarada" if modo_req == "ventaja" else False
        desventaja = "declarada" if modo_req == "desventaja" else False
        cd_raw = cuerpo.get("cd")
        if isinstance(cd_raw, str) and cd_raw.strip() and not cd_raw.strip().lstrip("-").isdigit():
            cd = cd_raw.strip()[:30]  # «exigente», «difícil»…: la resuelve el motor
        else:
            cd = _numero(cuerpo, "cd", minimo=1, maximo=40)
        etiqueta = _texto(cuerpo, "etiqueta", 80)

        with bloqueo.candado(estado.ruta_candado(slug)):
            datos = estado.cargar(slug)
            ficha = self._ficha_del_jugador(slug, datos, cuerpo.get("quien"))
            es_2024 = esquemas.version_de(datos) == esquemas.VERSION_2024

            if accion == "prueba":
                atributo = _texto(cuerpo, "atributo", 40) or "fuerza"
                salvacion = bool(cuerpo.get("salvacion")) and es_2024
                evento = reglas.prueba(
                    datos, ficha, atributo, cd=cd, ventaja=ventaja, desventaja=desventaja,
                    oficio=bool(cuerpo.get("oficio")), etiqueta=etiqueta, salvacion=salvacion,
                )
                texto = reglas.describir_prueba(evento)

            elif accion == "iniciativa":
                if es_2024:
                    # Se tira solo la de este PJ y se coloca en el orden que ya hubiera.
                    orden = reglas_2024.tirar_iniciativa(datos, quienes=[ficha], ventaja=ventaja, desventaja=desventaja, fusionar=True)
                    item = next(x for x in orden if x["quien"] == ficha["nombre"])
                    evento = {
                        "tipo": "prueba",
                        "reglamento": esquemas.REGLAMENTO_2024,
                        "quien": ficha["nombre"],
                        "atributo": "destreza",
                        "habilidad": "Iniciativa",
                        "etiqueta": etiqueta or "Iniciativa",
                        "partes": [{"fuente": "Destreza", "valor": item["modificador"]}],
                        "ventajas": item["ventajas"],
                        "desventajas": item["desventajas"],
                        "modo": item["modo"],
                        "caras": 20,
                        "valores": item["valores"],
                        "elegido": item["elegido"],
                        "modificador": item["modificador"],
                        "total": item["total"],
                        "cd": None,
                        "exito": None,
                        "resultado": "sin_cd",
                    }
                else:
                    evento = reglas.prueba(datos, ficha, "agilidad", ventaja=ventaja, desventaja=desventaja, etiqueta=etiqueta or "Iniciativa")
                texto = reglas.describir_prueba(evento)

            elif accion == "ataque":
                subtipo = _texto(cuerpo, "subtipo", 20).lower() or "arma"
                obj_req = _texto(cuerpo, "objetivo", 60)
                vivos = [e for e in datos.get("enemigos", []) if int(e.get("vida", 1) or 0) > 0]
                ca_practica = cd if isinstance(cd, int) else 12
                practica = {"nombre": "Objetivo", "defensa": ca_practica, "ca": ca_practica, "vida": 20, "vida_max": 20, "proteccion": 0}
                if obj_req:
                    # Por el nombre que ven los jugadores: el nombre real de un desconocido no se resuelve.
                    try:
                        objetivo = vista.resolver_objetivo(datos, obj_req)
                    except ValueError:
                        if vivos:
                            raise
                        objetivo = {**practica, "nombre": obj_req[:40]}
                elif vivos:
                    pol = vista.politica(datos)
                    raise ValueError("elige a quién atacas (Objetivo): " + ", ".join(vista.nombre_publico(pol, e["nombre"]) for e in vivos))
                else:
                    objetivo = practica
                if objetivo is ficha:
                    raise ValueError(f"{ficha['nombre']} no puede atacarse a sí mismo")

                armas = [a for a in (ficha.get("equipo") or []) if a.get("dano")]
                arma_nombre = _texto(cuerpo, "arma", 60) or None
                desarmado = {"nombre": "Golpe desarmado", "dano": "1", "tipo_dano": "contundente", "competente": True}
                attr_forzado = None
                arma_temporal = None
                if subtipo == "desarmado":
                    arma_temporal = desarmado
                elif subtipo == "distancia":
                    cand = next((a for a in armas if a.get("distancia")), None)
                    if cand is None:
                        raise ValueError(f"{ficha['nombre']} no lleva arma a distancia ni arrojadiza")
                    arma_nombre = cand["nombre"]
                elif subtipo == "cuerpo":
                    cand = next((a for a in armas if not a.get("distancia")), None)
                    if cand:
                        arma_nombre = cand["nombre"]
                    else:
                        arma_temporal = desarmado
                elif subtipo == "conjuro":
                    if es_2024:
                        attrs_f = ficha.get("atributos") or {}
                        mejor_mental = max(("inteligencia", "sabiduria", "carisma"), key=lambda k: int(attrs_f.get(k, 10)))
                        attr_forzado = str(ficha.get("atributo_conjuro") or mejor_mental)
                    else:
                        attr_forzado = "ingenio"
                    arma_temporal = {"nombre": "Conjuro de ataque", "dano": "1d8", "tipo_dano": "fuerza_magica", "distancia": True, "competente": True}
                    arma_nombre = "Conjuro de ataque"
                elif not armas and not arma_nombre:
                    arma_temporal = desarmado

                if arma_temporal is not None:
                    arma_nombre = arma_temporal["nombre"]
                    ficha.setdefault("equipo", []).append(arma_temporal)
                try:
                    evento = reglas.ataque(
                        datos, ficha, objetivo, arma=arma_nombre, ventaja=ventaja, desventaja=desventaja,
                        oficio=bool(cuerpo.get("oficio")), atributo=attr_forzado, etiqueta=etiqueta,
                    )
                finally:
                    if arma_temporal is not None and arma_temporal in ficha.get("equipo", []):
                        ficha["equipo"].remove(arma_temporal)
                texto = reglas.describir_prueba(evento)

            elif accion == "dano":
                critico = bool(cuerpo.get("critico"))
                expr = _texto(cuerpo, "expr", 60)
                arma_usada = None
                if expr:  # una expresión suelta se tira tal cual, sin modificador
                    r = reglas.dano(datos, expr, None, critico=critico)
                else:
                    arma_usada = reglas.buscar_arma(ficha, _texto(cuerpo, "arma", 60) or None)
                    if es_2024:  # SRD 5.2.1: el daño de un arma suma el modificador con el que se ataca
                        attr = reglas_2024.caracteristica_de_arma(ficha, arma_usada)
                        r = reglas_2024.dano(
                            datos, arma_usada["dano"], None, critico=critico, bonus_mod=reglas_2024.mod_caracteristica(ficha, attr),
                            fuente_mod=esquemas.NOMBRES_2024[attr], tipo_dano=arma_usada.get("tipo_dano"),
                        )
                    else:
                        r = reglas.dano(datos, arma_usada["dano"], None, critico=critico)
                evento = {"tipo": "dano", "quien": ficha["nombre"], "etiqueta": etiqueta or "Daño", **r["tirada"], "bruto": r["bruto"]}
                if arma_usada:
                    evento["arma"] = arma_usada["nombre"]
                if r.get("bonus_mod"):
                    evento.update(bonus_mod=r["bonus_mod"], fuente_mod=r.get("fuente_mod"))
                if r.get("tipo_dano"):
                    evento["tipo_dano"] = r["tipo_dano"]
                valores = " + ".join(str(v) for t in r["tirada"]["dados"] for v in t["valores"]) or str(r["tirada"]["total"])
                extra = f" {con_signo(r['bonus_mod'])} ({r.get('fuente_mod')})" if r.get("bonus_mod") else ""
                texto = f"Daño de {ficha['nombre']}: {r['tirada']['expr']} → {valores}{extra} = {r['bruto']}"

            elif accion == "dados_golpe":
                if not es_2024:
                    raise ValueError("d20-simple no usa Dados de Golpe: para curarse están el vendaje y los descansos")
                g = reglas_2024.gastar_dados_golpe(datos, ficha, 1)
                cv = g["vida"]
                expr_dg = f"1{g['dado']}{con_signo(g['mod_con']) if g['mod_con'] else ''}"
                evento = {
                    "tipo": "tirada",
                    "quien": ficha["nombre"],
                    "etiqueta": etiqueta or f"Dado de Golpe (quedan {g['restantes']}) · vida {cv['antes']} → {cv['despues']}/{cv['maximo']}",
                    "expr": expr_dg, "critico": False, "modificador": g["mod_con"], "total": g["curado"],
                    "dados": [{"dado": g["dado"], "signo": 1, "valores": g["valores"]}],
                }
                texto = f"{ficha['nombre']} · Dado de Golpe ({expr_dg}) = +{g['curado']} PG → vida {cv['antes']} → {cv['despues']}/{cv['maximo']}"

            elif accion == "salvacion_muerte":
                if not es_2024:
                    raise ValueError("d20-simple no tira salvaciones de muerte: a 0 de vida se queda Fuera de combate")
                if True:  # el motor rechaza a quien no está a 0 PG, está estable o ya murió
                    sm = reglas_2024.salvacion_muerte(datos, ficha)
                    evento = {
                        "tipo": "prueba",
                        "reglamento": esquemas.REGLAMENTO_2024,
                        "salvacion": True,
                        "quien": ficha["nombre"],
                        "atributo": "constitucion",
                        "habilidad": "Salvación de muerte",
                        "etiqueta": f"éxitos {sm['exitos']}/3 · fallos {sm['fallos']}/3",
                        "partes": [],
                        "ventajas": [],
                        "desventajas": [],
                        "modo": "normal",
                        "caras": 20,
                        "valores": [sm["valor"]],
                        "elegido": sm["valor"],
                        "modificador": 0,
                        "total": sm["valor"],
                        "cd": 10,
                        "exito": sm["valor"] >= 10,
                        "resultado": "critico" if sm["valor"] == 20 else ("uno_natural" if sm["valor"] == 1 else ("exito" if sm["valor"] >= 10 else "fallo")),
                    }
                    texto = f"{ficha['nombre']} · Salvación de muerte: 1d20 ({sm['valor']}) contra 10 → éxitos {sm['exitos']}/3, fallos {sm['fallos']}/3"

            elif accion == "descanso":
                clase = "largo" if _texto(cuerpo, "clase", 10).lower() == "largo" else "corto"
                if es_2024:
                    dg_gastar = 1 if (clase == "corto" and int(ficha.get("vida", 0)) < int(ficha.get("vida_max", 0))) else 0
                    lineas = reglas_2024.descanso(datos, clase, quienes=[ficha], dados_golpe=dg_gastar)
                else:
                    cambios = []
                    if clase == "largo":
                        v = reglas.aplicar_vida(ficha, int(ficha.get("vida_max", 0)))
                        if v["despues"] != v["antes"]:
                            cambios.append(f"vida {v['antes']} → {v['despues']}/{v['maximo']}")
                    if ficha.pop("vendaje_usado", None):
                        cambios.append("vendaje disponible")
                    recargas = {"descanso"} if clase == "corto" else {"descanso", "escena", "combate", "dia"}
                    for h in ficha.get("habilidades", []):
                        if h.get("recarga") in recargas and h.get("disponible") is False:
                            h["disponible"] = True
                            cambios.append(f"«{h['nombre']}» disponible")
                    lineas = [f"{ficha['nombre']}: {', '.join(cambios) or 'nada que recuperar'}"]
                evento = {"tipo": "descanso", "clase": clase, "quien": [ficha["nombre"]], "cambios": lineas}
                texto = f"Descanso {clase} · " + "; ".join(lineas)

            elif accion == "vida":
                delta = _numero(cuerpo, "delta", 0, minimo=-999, maximo=999)
                if cuerpo.get("temporal"):
                    cambio = reglas_2024.fijar_vida_temporal(ficha, max(0, delta))
                    evento = {"tipo": "vida_temporal", "quien": ficha["nombre"], "cantidad": max(0, delta), **cambio}
                    texto = f"{ficha['nombre']}: PG temporales {cambio['antes']} → {cambio['despues']}"
                else:
                    cambio = reglas.aplicar_vida(ficha, delta, partida=datos)
                    evento = {"tipo": "vida", "quien": ficha["nombre"], "delta": delta, "motivo": etiqueta or ("Curación" if delta >= 0 else "Daño"), **cambio}
                    texto = f"{ficha['nombre']}: vida {cambio['antes']} → {cambio['despues']}/{cambio['maximo']}"

            elif accion == "inspiracion":
                ficha["inspiracion"] = not bool(ficha.get("inspiracion"))
                estado_insp = "activada" if ficha["inspiracion"] else "gastada"
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']}: Inspiración heroica {estado_insp}"}
                texto = evento["texto"]

            elif accion == "equipar":
                elegido = self._objeto(ficha, _texto(cuerpo, "nombre", 60))
                nuevo_estado = not bool(elegido.get("equipado"))
                if nuevo_estado:
                    self._liberar_ranura(ficha, elegido)
                elegido["equipado"] = nuevo_estado
                # La CA guardada es la que usa el motor: el escudo o la armadura la mueven al equiparse.
                _ajustar_ca(ficha, _bono_ca(elegido) if nuevo_estado else -_bono_ca(elegido))
                evento = {
                    "tipo": "nota",
                    "texto": f"{ficha['nombre']} {'equipa' if nuevo_estado else 'guarda'} «{elegido['nombre']}»",
                }
                texto = evento["texto"]

            elif accion == "agregar_item":
                nombre_item = _texto(cuerpo, "nombre", 60)
                if not nombre_item:
                    raise ValueError("falta el nombre del objeto")
                if len(ficha.get("equipo") or []) >= 200:
                    raise ValueError(f"el inventario de {ficha['nombre']} ya tiene 200 objetos")
                categoria = _texto(cuerpo, "categoria", 20).lower() or "gear"
                ranura = _texto(cuerpo, "ranura", 20).lower()
                nuevo_obj: dict = {
                    "nombre": nombre_item,
                    "categoria": categoria if categoria in ("weapon", "armor", "gear") else "gear",
                    "peso": _numero(cuerpo, "peso", 0.0, minimo=0, maximo=10_000, entero=False),
                    "valor": _numero(cuerpo, "valor", 0, minimo=0, maximo=1_000_000_000),
                    "cantidad": _numero(cuerpo, "cantidad", 1, minimo=1, maximo=999),
                    "equipado": bool(cuerpo.get("equipado", False)),
                }
                if ranura:
                    nuevo_obj["ranura"] = ranura
                dano_txt = _texto(cuerpo, "dano", 20)
                if dano_txt:
                    dados.analizar(dano_txt)  # una expresión que el motor no sabe tirar no entra en la ficha
                    nuevo_obj.update(dano=dano_txt, competente=True, categoria="weapon")
                    nuevo_obj.setdefault("ranura", "main_hand")
                if _texto(cuerpo, "tipo_dano", 30):
                    nuevo_obj["tipo_dano"] = _texto(cuerpo, "tipo_dano", 30)
                bono = _numero(cuerpo, "bono_ca", 0, minimo=-10, maximo=10)
                if bono:
                    nuevo_obj.update(bono_ca=bono, categoria="armor")
                    nuevo_obj.setdefault("ranura", "armor")
                if _texto(cuerpo, "efecto", 120):
                    nuevo_obj.update(efecto=_texto(cuerpo, "efecto", 120), consumible=True)
                if _texto(cuerpo, "texto", 160):
                    nuevo_obj["texto"] = _texto(cuerpo, "texto", 160)
                if nuevo_obj["equipado"]:
                    self._liberar_ranura(ficha, nuevo_obj)
                    _ajustar_ca(ficha, _bono_ca(nuevo_obj))
                ficha.setdefault("equipo", []).append(nuevo_obj)
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']} añade «{nombre_item}» al inventario"}
                texto = evento["texto"]

            elif accion == "quitar_item":
                elegido = self._objeto(ficha, _texto(cuerpo, "nombre", 60))
                ficha["equipo"].remove(elegido)
                if elegido.get("equipado"):
                    _ajustar_ca(ficha, -_bono_ca(elegido))
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']} descarta «{elegido['nombre']}»"}
                texto = evento["texto"]

            elif accion == "usar_item":
                res_uso = reglas_2024.usar_consumible(datos, ficha, _texto(cuerpo, "nombre", 60))
                cura_txt = f" (+{res_uso['curacion']['total']} PG)" if res_uso.get("curacion") else ""
                evento = {
                    "tipo": "nota",
                    "texto": f"{ficha['nombre']} usa «{res_uso['objeto']}»{cura_txt} (quedan {res_uso['restantes']})",
                }
                texto = evento["texto"]

            elif accion == "monedas":
                tipos = reglas_2024.monedas_de(datos.get("ambientacion") or {})  # las de la campaña, no oro por defecto
                previas = ficha.get("monedas") if isinstance(ficha.get("monedas"), dict) else {}
                mon = ficha["monedas"] = {k: int(previas.get(k, 0) or 0) for k in tipos}
                for k in tipos:
                    valor = _numero(cuerpo, k, minimo=0, maximo=1_000_000_000)
                    if valor is not None:
                        mon[k] = valor
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']} actualiza su dinero: " + ", ".join(f"{v} {k}" for k, v in mon.items())}
                texto = evento["texto"]

            elif accion == "trasfondo":
                evento = self._aplicar_trasfondo(datos, ficha, cuerpo, es_2024)
                texto = evento["texto"]

            elif accion == "borrar_pj":
                # Un invitado solo borra el suyo (`_ficha_del_jugador`); el anfitrión, cualquiera.
                datos["personajes"].remove(ficha)
                escena = datos.get("escena") or {}
                escena["posiciones"] = [x for x in escena.get("posiciones") or [] if norm(str(x.get("quien", ""))) != norm(ficha["nombre"])]
                evento = {"tipo": "nota", "texto": f"{ficha['nombre']} deja la partida (ficha borrada)"}
                texto = evento["texto"]

            else:
                raise ValueError(f"acción de tirada desconocida: {accion!r}")

            (evento_guardado,) = estado.escribir(slug, datos=datos, eventos=[{**evento, "via": "visor"}])

        pol = vista.politica(datos)
        publico = self._texto_publico(pol, evento_guardado, texto)
        narrado = False
        if cuerpo.get("narrar") and getattr(self.server, "narrador", None) is not None:
            # Lo firma la mesa, no el PJ: es un aviso al narrador, no palabras del jugador. El chat
            # (público) guarda la versión que ven los jugadores; el narrador recibe la completa.
            try:
                self._narrador().enviar(
                    slug, f"[Tirada en la mesa · {publico}]", "Mesa",
                    texto_agente=f"[Tirada en la mesa · {texto}]" + (f" {etiqueta}" if etiqueta else ""),
                )
                narrado = True
            except chat.Ocupado:
                narrado = False

        return {"ok": True, "texto": publico, "evento": vista.evento(pol, evento_guardado), "narrado": narrado}

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

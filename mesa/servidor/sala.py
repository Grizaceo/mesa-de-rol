"""Auth de la mesa: anfitrión, clave de sala, reclamo de PJ y presencia."""

from __future__ import annotations

import json
import secrets
import time
from urllib.parse import unquote, urlparse

from .. import chat, estado, vista
from ..texto import norm, slug_valido
from .http import (
    HOSTS_LOCALES, MAX_CUERPO, MAX_PRESENCIA, Prohibido, TTL_PRESENCIA, TTL_RECLAMO,
    _es_loopback, _float_finito, _rechazar_constante,
)

class SalaMixin:
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

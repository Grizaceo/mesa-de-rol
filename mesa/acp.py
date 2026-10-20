"""Cliente ACP (Agent Client Protocol) mínimo, sin dependencias.

Con él el visor habla con el narrador (Hermes, Devin, Gemini CLI... cualquier agente que
sirva ACP por stdio) igual que un editor: lanza el proceso, abre o retoma una sesión y le
pasa los mensajes del jugador; el agente responde con notificaciones `session/update`
(trozos de texto, herramientas) y, si necesita permiso para algo, con
`session/request_permission`.

JSON-RPC 2.0, un mensaje por línea. El hilo lector despacha respuestas, notificaciones y
peticiones del agente; los permisos se resuelven en otro hilo para no bloquear la lectura.
No se ofrecen al agente ni el sistema de archivos ni la terminal del cliente: usa sus propias
herramientas, con los permisos que le dé su configuración.
"""

from __future__ import annotations

import json
import subprocess
import threading
from collections import deque
from typing import Callable

VERSION_PROTOCOLO = 1


class ErrorACP(RuntimeError):
    """El agente no arrancó, se cayó o respondió con un error."""


class ClienteACP:
    def __init__(self, comando: list[str], cwd: str, env: dict | None = None,
                 al_actualizar: Callable[[str, dict], None] | None = None,
                 al_pedir_permiso: Callable[[dict], str | None] | None = None):
        self.comando, self.cwd, self.env = comando, cwd, env
        self.al_actualizar = al_actualizar or (lambda sesion, update: None)
        self.al_pedir_permiso = al_pedir_permiso or (lambda params: None)
        self.capacidades: dict = {}
        self.info: dict = {}
        self._proceso: subprocess.Popen | None = None
        self._siguiente = 0
        self._pendientes: dict[int, dict] = {}
        self._cerrojo = threading.Lock()
        self._escritura = threading.Lock()
        self.stderr: deque[str] = deque(maxlen=60)

    # ---------- proceso ----------

    @property
    def vivo(self) -> bool:
        return self._proceso is not None and self._proceso.poll() is None

    def iniciar(self, espera: float = 120) -> dict:
        try:
            self._proceso = subprocess.Popen(
                self.comando, cwd=self.cwd, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
            )
        except OSError as e:
            raise ErrorACP(f"no se pudo lanzar el narrador ({' '.join(self.comando)}): {e}") from e
        threading.Thread(target=self._leer, daemon=True).start()
        threading.Thread(target=self._leer_errores, daemon=True).start()
        r = self.pedir("initialize", {
            "protocolVersion": VERSION_PROTOCOLO,
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
            "clientInfo": {"name": "mesa-de-rol", "version": "0.1"},
        }, espera)
        self.capacidades = r.get("agentCapabilities") or {}
        self.info = r.get("agentInfo") or {}
        return r

    def cerrar(self) -> None:
        proceso, self._proceso = self._proceso, None
        if proceso is None:
            return
        try:
            proceso.stdin.close()
        except OSError:
            pass
        try:
            proceso.terminate()
            proceso.wait(5)
        except (OSError, subprocess.TimeoutExpired):
            proceso.kill()
            proceso.wait(5)
        for tubo in (proceso.stdout, proceso.stderr):
            try:
                tubo.close()
            except (OSError, ValueError):
                pass
        self._fallar_pendientes("el narrador se cerró")

    # ---------- JSON-RPC ----------

    def _enviar(self, mensaje: dict) -> None:
        if not self.vivo:
            raise ErrorACP("el narrador no está en marcha")
        with self._escritura:
            self._proceso.stdin.write(json.dumps(mensaje, ensure_ascii=False) + "\n")
            self._proceso.stdin.flush()

    def pedir(self, metodo: str, params: dict, espera: float | None = None) -> dict:
        with self._cerrojo:
            self._siguiente += 1
            ident = self._siguiente
            espera_ = {"evento": threading.Event(), "respuesta": None}
            self._pendientes[ident] = espera_
        try:
            self._enviar({"jsonrpc": "2.0", "id": ident, "method": metodo, "params": params})
            if not espera_["evento"].wait(espera):
                raise ErrorACP(f"el narrador no respondió a {metodo} en {espera:.0f} s")
        finally:
            with self._cerrojo:
                self._pendientes.pop(ident, None)
        respuesta = espera_["respuesta"] or {}
        if "error" in respuesta:
            error = respuesta["error"] or {}
            detalle = f" ({error['data']})" if error.get("data") else ""
            raise ErrorACP(f"{metodo}: {error.get('message', 'error')}{detalle}")
        return respuesta.get("result") or {}

    def notificar(self, metodo: str, params: dict) -> None:
        self._enviar({"jsonrpc": "2.0", "method": metodo, "params": params})

    def _responder(self, ident, resultado=None, error: dict | None = None) -> None:
        mensaje = {"jsonrpc": "2.0", "id": ident}
        mensaje.update({"error": error} if error else {"result": resultado if resultado is not None else {}})
        try:
            self._enviar(mensaje)
        except ErrorACP:
            pass

    def _leer(self) -> None:
        proceso = self._proceso
        for linea in proceso.stdout:
            try:
                mensaje = json.loads(linea)
            except json.JSONDecodeError:
                self.stderr.append(f"(stdout no JSON) {linea.rstrip()[:300]}")
                continue
            if not isinstance(mensaje, dict):
                continue
            metodo = mensaje.get("method")
            if metodo is None:  # respuesta a una petición nuestra
                with self._cerrojo:
                    espera = self._pendientes.get(mensaje.get("id"))
                if espera is not None:
                    espera["respuesta"] = mensaje
                    espera["evento"].set()
            elif "id" in mensaje:  # el agente nos pide algo
                threading.Thread(target=self._atender, args=(mensaje,), daemon=True).start()
            elif metodo == "session/update":
                params = mensaje.get("params") or {}
                try:
                    self.al_actualizar(params.get("sessionId", ""), params.get("update") or {})
                except Exception as e:  # una tarjeta rota no puede matar la lectura
                    self.stderr.append(f"(al_actualizar) {type(e).__name__}: {e}")
        self._fallar_pendientes("el narrador terminó: " + (" | ".join(list(self.stderr)[-3:]) or "sin detalle"))

    def _leer_errores(self) -> None:
        for linea in self._proceso.stderr:
            self.stderr.append(linea.rstrip()[:500])

    def _atender(self, mensaje: dict) -> None:
        metodo, params = mensaje.get("method"), mensaje.get("params") or {}
        if metodo != "session/request_permission":
            self._responder(mensaje["id"], error={"code": -32601, "message": f"{metodo}: el cliente no lo ofrece"})
            return
        try:
            opcion = self.al_pedir_permiso(params)
        except Exception as e:
            self.stderr.append(f"(permiso) {type(e).__name__}: {e}")
            opcion = None
        resultado = {"outcome": {"outcome": "selected", "optionId": opcion}} if opcion else {"outcome": {"outcome": "cancelled"}}
        self._responder(mensaje["id"], resultado)

    def _fallar_pendientes(self, motivo: str) -> None:
        with self._cerrojo:
            pendientes = list(self._pendientes.values())
        for espera in pendientes:
            espera["respuesta"] = {"error": {"message": motivo}}
            espera["evento"].set()

    # ---------- sesiones ----------

    def nueva_sesion(self, mcp: list[dict], espera: float = 120) -> dict:
        return self.pedir("session/new", {"cwd": self.cwd, "mcpServers": mcp}, espera)

    def cargar_sesion(self, sesion: str, mcp: list[dict], espera: float = 120) -> bool:
        if not self.capacidades.get("loadSession"):
            return False
        try:
            self.pedir("session/load", {"sessionId": sesion, "cwd": self.cwd, "mcpServers": mcp}, espera)
            return True
        except ErrorACP:
            return False

    def preguntar(self, sesion: str, texto: str) -> str:
        """Un turno: manda el mensaje y espera la respuesta final; devuelve el motivo de parada."""
        r = self.pedir("session/prompt", {"sessionId": sesion, "prompt": [{"type": "text", "text": texto}]})
        return r.get("stopReason", "end_turn")

    def cancelar(self, sesion: str) -> None:
        try:
            self.notificar("session/cancel", {"sessionId": sesion})
        except ErrorACP:
            pass


def elegir_opcion(opciones: list[dict], permitir: bool) -> str | None:
    """De las opciones de un permiso, la de permitir (o rechazar) una vez; si no hay, la siempre."""
    prioridad = ("allow_once", "allow_always") if permitir else ("reject_once", "reject_always")
    for tipo in prioridad:
        for o in opciones or []:
            if o.get("kind") == tipo:
                return o.get("optionId")
    return None

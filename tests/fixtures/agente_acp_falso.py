"""Agente ACP de mentira para los tests del chat: habla el protocolo sin ningún modelo.

Según lo que diga el mensaje del jugador:
- siempre: piensa (no debe verse), lee «director.md» con contenido secreto (no debe verse) y responde;
- «tira»: registra una tirada de verdad con el MCP de la partida (`python -m mesa tirar`) a mitad del texto;
- «permiso»: pide permiso para un comando y cuenta qué le contestaron;
- «lento»: tarda hasta que lo cancelan.
Dice «nueva» si el mensaje traía el preámbulo de sesión nueva y «seguida» si no.
"""

import json
import os
import subprocess
import sys
import threading
import time

escritura = threading.Lock()
sesiones = {}
pendientes = {}
cancelado = threading.Event()
siguiente = [1000]


def enviar(mensaje):
    with escritura:
        sys.stdout.write(json.dumps(mensaje, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def actualizar(sesion, update):
    enviar({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sesion, "update": update}})


def texto(sesion, trozo):
    actualizar(sesion, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": trozo}})


def pedir_al_cliente(metodo, params):
    siguiente[0] += 1
    ident = siguiente[0]
    listo = threading.Event()
    pendientes[ident] = {"listo": listo}
    enviar({"jsonrpc": "2.0", "id": ident, "method": metodo, "params": params})
    listo.wait(30)
    return pendientes.pop(ident).get("respuesta", {})


def turno(ident, params):
    sesion = params["sessionId"]
    dicho = params["prompt"][0]["text"]
    cancelado.clear()
    actualizar(sesion, {"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "PENSAMIENTO SECRETO"}})
    actualizar(sesion, {"sessionUpdate": "tool_call", "toolCallId": "t1", "title": "read_file", "kind": "read", "status": "in_progress",
                        "content": [{"type": "content", "content": {"type": "text", "text": "SECRETO DEL DIRECTOR"}}]})
    actualizar(sesion, {"sessionUpdate": "tool_call_update", "toolCallId": "t1", "status": "completed"})
    texto(sesion, "nueva. " if "[Mesa de rol" in dicho else "seguida. ")
    if "tira" in dicho:
        texto(sesion, "Tiras el dado")
        actualizar(sesion, {"sessionUpdate": "tool_call", "toolCallId": "t2", "title": "mcp_mesa_tirar", "kind": "other", "status": "in_progress"})
        env = {**os.environ, **sesiones[sesion]["env"]}
        subprocess.run([sys.executable, "-m", "mesa", "tirar", "1d20", "--etiqueta", "falso"], env=env, capture_output=True, check=True)
        time.sleep(0.6)  # que el vigía de la bitácora lo vea antes del texto que sigue
        actualizar(sesion, {"sessionUpdate": "tool_call_update", "toolCallId": "t2", "status": "completed"})
        texto(sesion, " y sale lo que sale.")
    if "permiso" in dicho:
        r = pedir_al_cliente("session/request_permission", {
            "sessionId": sesion,
            "toolCall": {"toolCallId": "t3", "title": "rm -rf /tmp/algo", "kind": "execute"},
            "options": [{"optionId": "si", "name": "Permitir", "kind": "allow_once"}, {"optionId": "no", "name": "Rechazar", "kind": "reject_once"}],
        })
        salida = (r.get("result") or {}).get("outcome") or {}
        texto(sesion, f"permiso={salida.get('optionId') or salida.get('outcome')}")
    if "lento" in dicho:
        for _ in range(100):
            if cancelado.wait(0.1):
                enviar({"jsonrpc": "2.0", "id": ident, "result": {"stopReason": "cancelled"}})
                return
    enviar({"jsonrpc": "2.0", "id": ident, "result": {"stopReason": "end_turn"}})


def main():
    for linea in sys.stdin:
        m = json.loads(linea)
        metodo, ident, params = m.get("method"), m.get("id"), m.get("params") or {}
        if metodo is None:
            if ident in pendientes:
                pendientes[ident]["respuesta"] = m
                pendientes[ident]["listo"].set()
        elif metodo == "initialize":
            enviar({"jsonrpc": "2.0", "id": ident, "result": {"protocolVersion": 1, "agentCapabilities": {"loadSession": True}, "agentInfo": {"name": "falso"}}})
        elif metodo == "session/new":
            sesion = f"s-{len(sesiones) + 1}-{os.getpid()}"
            env = {e["name"]: e["value"] for e in params["mcpServers"][0]["env"]}
            sesiones[sesion] = {"env": env}
            enviar({"jsonrpc": "2.0", "id": ident, "result": {"sessionId": sesion, "models": {"currentModelId": "falso:modelo-de-prueba"}}})
        elif metodo == "session/load":
            sesion = params["sessionId"]
            if not sesion.startswith("s-"):
                enviar({"jsonrpc": "2.0", "id": ident, "error": {"code": -32002, "message": "no existe"}})
                continue
            sesiones[sesion] = {"env": {e["name"]: e["value"] for e in params["mcpServers"][0]["env"]}}
            actualizar(sesion, {"sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": "HISTORIA REPETIDA"}})
            texto(sesion, "HISTORIA REPETIDA")
            enviar({"jsonrpc": "2.0", "id": ident, "result": {}})
        elif metodo == "session/prompt":
            threading.Thread(target=turno, args=(ident, params), daemon=True).start()
        elif metodo == "session/cancel":
            cancelado.set()
        elif ident is not None:
            enviar({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "no"}})


if __name__ == "__main__":
    main()

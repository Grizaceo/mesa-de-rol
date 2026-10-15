"""Servidor MCP (Model Context Protocol) por stdio, sin dependencias.

Expone las mismas operaciones que la CLI para harnesses que prefieren herramientas
estructuradas (Claude Code, Codex, OpenCode, Gemini CLI, Cursor, Hermes...). Cada
herramienta se traduce a argumentos de `mesa` y se ejecuta con el mismo motor, así que
CLI y MCP nunca divergen.

Protocolo: JSON-RPC 2.0, un mensaje JSON por línea en stdin/stdout. stdout es el canal
del protocolo; los registros van a stderr.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout

from . import __version__, cli

VERSIONES = ("2025-06-18", "2025-03-26", "2024-11-05")
PROHIBIDOS = {"servir"}  # bloquearía el servidor

INSTRUCCIONES = (
    "Herramientas de la mesa de rol. Eres el director de juego: sigue AGENTS.md del repo. "
    "Empieza con `retomar` (indica tu harness/modelo como narrador), tira siempre con estas "
    "herramientas, registra cada turno con `turno` y al parar usa `pausar` con lo que queda pendiente."
)

_PARTIDA = {"type": "string", "description": "Slug de la partida; por defecto, la activa."}
_MOTIVO = {
    "type": ["string", "boolean"],
    "description": "true o el motivo (p. ej. 'Jualjin distrae'). Ventaja y desventaja se anulan entre sí.",
}
_BONOS = {"type": "array", "items": {"type": "string"}, "description": "Bonos extra como 'N:fuente', p. ej. '2:palanca'."}

HERRAMIENTAS = [
    {
        "name": "retomar",
        "title": "Retomar la partida",
        "description": "Empieza o retoma la sesión: registra quién narra y devuelve dónde quedó la historia, lecciones, reglas de la casa y estado. Llamar primero.",
        "inputSchema": {"type": "object", "properties": {
            "narrador": {"type": "string", "description": "harness/modelo, p. ej. 'codex/gpt-5.5' o 'hermes/kimi-k3'."},
            "partida": _PARTIDA}},
    },
    {
        "name": "contexto",
        "title": "Contexto del director",
        "description": "Lecciones aplicables, reglas de la casa, estado y últimos eventos. Con completo=true incluye biblia, notas secretas del director y reglamento.",
        "inputSchema": {"type": "object", "properties": {
            "completo": {"type": "boolean"}, "eventos": {"type": "integer", "minimum": 1}, "partida": _PARTIDA}},
    },
    {
        "name": "estado",
        "title": "Estado de la partida",
        "description": "Resumen legible del estado: escena, posiciones, fichas, recursos, PNJ, pistas y tramas.",
        "inputSchema": {"type": "object", "properties": {"partida": _PARTIDA}},
    },
    {
        "name": "prueba",
        "title": "Prueba d20",
        "description": "Prueba de atributo o habilidad (fuerza, agilidad, ingenio, corazón, o percepción, sigilo, engaño...) contra una dificultad. Aplica condiciones, ventaja/desventaja y 20/1 naturales. Anuncia la apuesta a los jugadores antes si hay riesgo.",
        "inputSchema": {"type": "object", "required": ["quien", "atributo"], "properties": {
            "quien": {"type": "string"},
            "atributo": {"type": "string"},
            "cd": {"type": ["string", "integer"], "description": "Número o: muy-facil, facil, media, dificil, muy-dificil, casi-imposible."},
            "ventaja": _MOTIVO, "desventaja": _MOTIVO,
            "oficio": {"type": "boolean", "description": "Suma el bono de oficio si la acción cae en el oficio del personaje."},
            "usar": {"type": "string", "description": "Habilidad de la ficha que se gasta y suma su bono."},
            "bonos": _BONOS,
            "etiqueta": {"type": "string", "description": "Qué intenta, en pocas palabras."},
            "partida": _PARTIDA}},
    },
    {
        "name": "ataque",
        "title": "Ataque",
        "description": "Ataque contra la Defensa del objetivo; si acierta, tira el daño del arma, resta protección y lo aplica.",
        "inputSchema": {"type": "object", "required": ["quien", "objetivo"], "properties": {
            "quien": {"type": "string"}, "objetivo": {"type": "string"},
            "arma": {"type": "string"}, "atributo": {"type": "string"},
            "cobertura": {"type": "string", "enum": ["media", "tres-cuartos"]},
            "ventaja": _MOTIVO, "desventaja": _MOTIVO, "oficio": {"type": "boolean"}, "bonos": _BONOS,
            "etiqueta": {"type": "string"}, "partida": _PARTIDA}},
    },
    {
        "name": "tirar",
        "title": "Tirada libre",
        "description": "Tira una expresión de dados: 1d20+3, 2d6, 1d8+1d4, d100.",
        "inputSchema": {"type": "object", "required": ["expr"], "properties": {
            "expr": {"type": "string"}, "quien": {"type": "string"}, "etiqueta": {"type": "string"},
            "critico": {"type": "boolean"}, "partida": _PARTIDA}},
    },
    {
        "name": "suerte",
        "title": "Suerte (d100)",
        "description": "d100 contra un porcentaje para lo que no depende de nadie (¿hay alguien en esa calle?).",
        "inputSchema": {"type": "object", "required": ["probabilidad", "etiqueta"], "properties": {
            "probabilidad": {"type": "integer", "minimum": 0, "maximum": 100}, "etiqueta": {"type": "string"},
            "partida": _PARTIDA}},
    },
    {
        "name": "turno",
        "title": "Registrar turno",
        "description": "Registra lo que declaró cada jugador (con sus palabras) y lo que pasó. Hazlo en cada turno.",
        "inputSchema": {"type": "object", "required": ["resumen"], "properties": {
            "acciones": {"type": "object", "additionalProperties": {"type": "string"}, "description": "{nombre del personaje: lo que declaró}"},
            "resumen": {"type": "string"}, "partida": _PARTIDA}},
    },
    {
        "name": "pausar",
        "title": "Pausar la partida",
        "description": "Deja el traspaso para el próximo narrador (sea cual sea su harness): qué está pendiente y a quién se espera. Con commit=true guarda la partida en git.",
        "inputSchema": {"type": "object", "required": ["pendiente"], "properties": {
            "pendiente": {"type": "string"}, "commit": {"type": "boolean"}, "partida": _PARTIDA}},
    },
    {
        "name": "comando",
        "title": "Otro comando de la mesa",
        "description": (
            "Cualquier otro comando de la CLI `mesa`, como lista de argumentos. Comandos: vida, condicion, habilidad, "
            "enemigo, nivel, escena, pnj, pista, trama, misterio, recurso, reloj, regla, nota, imagen, guardar, retro, "
            "leccion, partidas, usar, nueva. Ejemplos: [\"vida\", \"Jualjin\", \"-3\"], "
            "[\"escena\", \"posicion\", \"Crisljin\", \"en la popa, a 4 m\"], [\"pnj\", \"Anya\", \"--nota\", \"...\"]."
        ),
        "inputSchema": {"type": "object", "required": ["args"], "properties": {
            "args": {"type": "array", "items": {"type": "string"}, "minItems": 1}, "partida": _PARTIDA}},
    },
]


def _motivo(args: list[str], bandera: str, valor) -> None:
    if valor is True:
        args.append(bandera)
    elif isinstance(valor, str) and valor.strip():
        args += [bandera, valor]


def construir_argumentos(nombre: str, a: dict) -> list[str]:
    """Traduce una llamada MCP a argumentos de la CLI."""
    previos = ["-p", a["partida"]] if a.get("partida") else []
    if nombre == "retomar":
        args = ["retomar"] + (["--narrador", a["narrador"]] if a.get("narrador") else [])
    elif nombre == "contexto":
        args = ["contexto"] + (["--completo"] if a.get("completo") else []) + (["--eventos", str(a["eventos"])] if a.get("eventos") else [])
    elif nombre == "estado":
        args = ["estado"]
    elif nombre in ("prueba", "ataque"):
        args = [nombre, a["quien"], a["atributo"] if nombre == "prueba" else a["objetivo"]]
        for campo in ("cd", "usar", "arma", "atributo", "cobertura", "etiqueta"):
            if nombre == "prueba" and campo == "atributo":
                continue
            if a.get(campo) not in (None, ""):
                args += [f"--{campo}", str(a[campo])]
        _motivo(args, "--ventaja", a.get("ventaja"))
        _motivo(args, "--desventaja", a.get("desventaja"))
        if a.get("oficio"):
            args.append("--oficio")
        for bono in a.get("bonos") or []:
            args += ["--bono", bono]
    elif nombre == "tirar":
        args = ["tirar", a["expr"]] + sum(([f"--{c}", a[c]] for c in ("quien", "etiqueta") if a.get(c)), [])
        if a.get("critico"):
            args.append("--critico")
    elif nombre == "suerte":
        args = ["suerte", str(a["probabilidad"]), "--etiqueta", a["etiqueta"]]
    elif nombre == "turno":
        args = ["turno", "--resumen", a["resumen"]]
        for quien, que in (a.get("acciones") or {}).items():
            args += ["--accion", f"{quien}={que}"]
    elif nombre == "pausar":
        args = ["pausar", "--pendiente", a["pendiente"]] + (["--commit"] if a.get("commit") else [])
    elif nombre == "comando":
        args = [str(x) for x in a["args"]]
        if args and args[0] in PROHIBIDOS:
            raise ValueError(f"`{args[0]}` no se puede usar desde MCP")
    else:
        raise KeyError(nombre)
    return previos + args


def ejecutar(args: list[str]) -> tuple[bool, str]:
    salida, errores = io.StringIO(), io.StringIO()
    with redirect_stdout(salida), redirect_stderr(errores):
        try:
            codigo = cli.main(args)
        except SystemExit as e:  # argparse: argumentos inválidos
            codigo = e.code if isinstance(e.code, int) else 1
    texto = "\n".join(t for t in (salida.getvalue().strip(), errores.getvalue().strip()) if t)
    return codigo == 0, texto or "(sin salida)"


def _resultado(id_, resultado) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": resultado}


def _error(id_, codigo: int, mensaje: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": mensaje}}


def atender(mensaje: dict) -> dict | None:
    """Responde un mensaje JSON-RPC; las notificaciones (sin id) no tienen respuesta."""
    if not isinstance(mensaje, dict) or mensaje.get("jsonrpc") != "2.0" or "method" not in mensaje:
        return _error(mensaje.get("id") if isinstance(mensaje, dict) else None, -32600, "petición inválida")
    metodo, id_ = mensaje["method"], mensaje.get("id")
    if id_ is None:
        return None
    params = mensaje.get("params") or {}
    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        return _resultado(id_, {
            "protocolVersion": pedida if pedida in VERSIONES else VERSIONES[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "mesa-de-rol", "version": __version__},
            "instructions": INSTRUCCIONES,
        })
    if metodo == "ping":
        return _resultado(id_, {})
    if metodo == "tools/list":
        return _resultado(id_, {"tools": HERRAMIENTAS})
    if metodo == "tools/call":
        nombre, argumentos = params.get("name"), params.get("arguments") or {}
        if nombre not in {h["name"] for h in HERRAMIENTAS}:
            return _error(id_, -32602, f"herramienta desconocida: {nombre}")
        try:
            ok, texto = ejecutar(construir_argumentos(nombre, argumentos))
        except (KeyError, ValueError, TypeError) as e:
            ok, texto = False, f"argumentos inválidos: {e}"
        return _resultado(id_, {"content": [{"type": "text", "text": texto}], "isError": not ok})
    return _error(id_, -32601, f"método no soportado: {metodo}")


def servir(entrada=None, salida=None) -> None:
    entrada = entrada or sys.stdin
    salida = salida or sys.stdout
    for linea in entrada:
        if not linea.strip():
            continue
        try:
            mensaje = json.loads(linea)
        except json.JSONDecodeError:
            respuestas = [_error(None, -32700, "JSON inválido")]
        else:
            lote = mensaje if isinstance(mensaje, list) else [mensaje]
            respuestas = [r for r in (atender(m) for m in lote) if r is not None]
            if isinstance(mensaje, list) and respuestas:
                salida.write(json.dumps(respuestas, ensure_ascii=False) + "\n")
                salida.flush()
                continue
        for r in respuestas:
            salida.write(json.dumps(r, ensure_ascii=False) + "\n")
        salida.flush()


if __name__ == "__main__":
    servir()

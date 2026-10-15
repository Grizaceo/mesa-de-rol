"""Adaptadores por harness: un solo origen y archivos generados.

Origen único:
  AGENTS.md               contrato del director (estándar abierto que leen la mayoría de harnesses)
  adaptadores/comandos/   comandos /retomar, /pausar, /nueva-historia
  adaptadores/hermes/     skill opcional para Hermes

Todo lo demás (CLAUDE.md, GEMINI.md, configuraciones MCP y comandos por harness) se genera
con `mesa harness sync` y se comprueba con `mesa harness verificar`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import estado

MCP = "bin/mesa-mcp"
CABECERA_MD = "<!-- Generado por `bin/mesa harness sync`. No editar: cambia AGENTS.md o adaptadores/. -->"
CABECERA_HASH = "# Generado por `bin/mesa harness sync`. No editar: cambia adaptadores/ o mesa/harness.py."

HARNESSES = [
    {"id": "claude-code", "nombre": "Claude Code", "instrucciones": "CLAUDE.md → importa AGENTS.md",
     "mcp": ".mcp.json (aprobar la primera vez)", "comandos": ".claude/commands/", "archivos": ["CLAUDE.md", ".mcp.json"]},
    {"id": "codex", "nombre": "Codex CLI", "instrucciones": "AGENTS.md (nativo)",
     "mcp": ".codex/config.toml (solo en proyectos de confianza)", "comandos": "—", "archivos": [".codex/config.toml"]},
    {"id": "hermes", "nombre": "Hermes (DAVI)", "instrucciones": "AGENTS.md (nativo; prioridad .hermes.md > AGENTS.md > CLAUDE.md)",
     "mcp": "mcp_servers en ~/.hermes/config.yaml (opcional)", "comandos": "skill opcional", "archivos": []},
    {"id": "opencode", "nombre": "OpenCode", "instrucciones": "AGENTS.md (nativo)",
     "mcp": ".opencode/opencode.json (formato v2)", "comandos": ".opencode/commands/", "archivos": [".opencode/opencode.json"]},
    {"id": "devin", "nombre": "Devin", "instrucciones": "AGENTS.md (nativo, CLI local y nube)",
     "mcp": ".mcp.json (CLI local); en la nube, la CLI en su VM", "comandos": "—", "archivos": [".mcp.json"]},
    {"id": "gemini-cli", "nombre": "Gemini CLI", "instrucciones": "GEMINI.md → importa AGENTS.md",
     "mcp": ".gemini/settings.json", "comandos": ".gemini/commands/", "archivos": ["GEMINI.md", ".gemini/settings.json"]},
    {"id": "cursor", "nombre": "Cursor", "instrucciones": "AGENTS.md (nativo)",
     "mcp": ".cursor/mcp.json", "comandos": "—", "archivos": [".cursor/mcp.json"]},
    {"id": "aider", "nombre": "Aider", "instrucciones": ".aider.conf.yml → lee AGENTS.md",
     "mcp": "no tiene: /run bin/mesa ...", "comandos": "—", "archivos": [".aider.conf.yml"]},
    {"id": "otro", "nombre": "Cualquier otro", "instrucciones": "«lee AGENTS.md y retoma la partida»",
     "mcp": "bin/mesa-mcp si soporta MCP por stdio", "comandos": "—", "archivos": []},
]


def _raiz() -> Path:
    return estado.RAIZ


def comandos() -> list[tuple[str, str, str]]:
    """(nombre, descripción, cuerpo) de cada comando canónico."""
    salida = []
    for ruta in sorted((_raiz() / "adaptadores" / "comandos").glob("*.md")):
        texto = ruta.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n(.*)", texto, re.S)
        if not m:
            raise ValueError(f"{ruta} necesita frontmatter con description")
        descripcion = re.search(r"^description:\s*(.+)$", m.group(1), re.M)
        salida.append((ruta.stem, descripcion.group(1).strip() if descripcion else ruta.stem, m.group(2).lstrip("\n")))
    return salida


def _json(datos: dict) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"


def archivos() -> dict[str, str]:
    """Ruta relativa → contenido de cada archivo generado."""
    puntero = (
        "Este repo es una mesa de rol dirigida por IA. Si te piden jugar, retomar o crear una partida,\n"
        "eres el director de juego: sigue el contrato de AGENTS.md (importado abajo).\n"
    )
    a = {
        "CLAUDE.md": f"{CABECERA_MD}\n# CLAUDE.md\n\n{puntero}\n@AGENTS.md\n",
        "GEMINI.md": f"{CABECERA_MD}\n# GEMINI.md\n\n{puntero}\n@./AGENTS.md\n",
        ".mcp.json": _json({"mcpServers": {"mesa": {"type": "stdio", "command": MCP, "args": []}}}),
        ".cursor/mcp.json": _json({"mcpServers": {"mesa": {"command": MCP, "args": []}}}),
        ".gemini/settings.json": _json({"mcpServers": {"mesa": {"command": MCP, "args": []}}}),
        # OpenCode v2 (mcp.servers.<nombre>). Va en .opencode/ y no en la raíz porque la CLI de Devin
        # lee opencode.json de la raíz con el formato v1 (mcp.<nombre>) y crearía un servidor «servers».
        ".opencode/opencode.json": _json({"$schema": "https://opencode.ai/config.json", "mcp": {"servers": {"mesa": {"type": "local", "command": [MCP]}}}}),
        ".codex/config.toml": (
            f"{CABECERA_HASH}\n# Codex solo lee este archivo si el proyecto está marcado como de confianza.\n"
            f"[mcp_servers.mesa]\ncommand = \"{MCP}\"\nargs = []\n"
        ),
        ".aider.conf.yml": f"{CABECERA_HASH}\nread:\n  - AGENTS.md\n",
    }
    for nombre, descripcion, cuerpo in comandos():
        markdown = f"---\ndescription: {descripcion}\n---\n{cuerpo}"
        a[f".claude/commands/{nombre}.md"] = markdown
        a[f".opencode/commands/{nombre}.md"] = markdown
        prompt = cuerpo.replace("$ARGUMENTS", "{{args}}")
        a[f".gemini/commands/{nombre}.toml"] = (
            f"{CABECERA_HASH}\ndescription = {json.dumps(descripcion, ensure_ascii=False)}\nprompt = '''\n{prompt}'''\n"
        )
    return a


def diferencias() -> list[str]:
    return [ruta for ruta, contenido in archivos().items()
            if not (_raiz() / ruta).exists() or (_raiz() / ruta).read_text(encoding="utf-8") != contenido]


def sync() -> list[str]:
    cambiados = diferencias()
    generados = archivos()
    for ruta in cambiados:
        destino = _raiz() / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(generados[ruta], encoding="utf-8")
    return cambiados


def probar_mcp() -> tuple[bool, str]:
    """Arranca el servidor MCP como lo haría un harness y comprueba initialize + tools/list."""
    peticiones = "\n".join(json.dumps(m) for m in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "verificar", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )) + "\n"
    entorno = dict(os.environ, PYTHONPATH=str(_raiz()), MESA_RAIZ=str(_raiz()))
    try:
        r = subprocess.run([sys.executable, "-m", "mesa.mcp"], input=peticiones, capture_output=True,
                           text=True, timeout=20, cwd=_raiz(), env=entorno)
        respuestas = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
        herramientas = respuestas[1]["result"]["tools"]
        return True, f"responde: {len(herramientas)} herramientas ({', '.join(h['name'] for h in herramientas)})"
    except (subprocess.SubprocessError, json.JSONDecodeError, IndexError, KeyError) as e:
        return False, f"no responde bien: {e}"


def _python_hermes() -> tuple[Path, Path] | None:
    agente = Path(os.environ.get("HERMES_AGENT_DIR", Path.home() / ".hermes" / "hermes-agent"))
    candidatos = [Path(os.environ["HERMES_PYTHON"])] if os.environ.get("HERMES_PYTHON") else sorted(
        (Path.home() / ".hermes" / "tools").glob("python-*/bin/python3"))
    python = next((p for p in reversed(candidatos) if p.exists()), None)
    if python and (agente / "tools" / "threat_patterns.py").exists():
        return python, agente
    return None


def escanear_hermes() -> tuple[str, str]:
    """Hermes bloquea los AGENTS.md que parecen inyección de prompts: comprueba que el nuestro pasa."""
    encontrado = _python_hermes()
    if not encontrado:
        return "omitido", "Hermes no está instalado aquí (o define HERMES_AGENT_DIR y HERMES_PYTHON)"
    python, agente = encontrado
    codigo = (
        "import sys, json; sys.path.insert(0, sys.argv[1]);"
        "from tools.threat_patterns import scan_for_threats;"
        "print(json.dumps({p: scan_for_threats(open(p, encoding='utf-8').read(), scope='context') for p in sys.argv[2:]}, default=str))"
    )
    rutas = [str(_raiz() / n) for n in ("AGENTS.md", "CLAUDE.md") if (_raiz() / n).exists()]
    r = subprocess.run([str(python), "-I", "-c", codigo, str(agente), *rutas], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return "fallo", f"no se pudo ejecutar el escáner de Hermes: {r.stderr.strip()[-200:]}"
    hallazgos = {Path(k).name: v for k, v in json.loads(r.stdout).items() if v}
    return ("fallo", f"Hermes bloquearía: {hallazgos}") if hallazgos else ("ok", "AGENTS.md y CLAUDE.md pasan el escáner de inyección de Hermes")


def verificar() -> list[tuple[str, str, str]]:
    resultados = []
    resultados.append(("AGENTS.md", "ok" if (_raiz() / "AGENTS.md").exists() else "fallo", "contrato del director"))
    pendientes = diferencias()
    resultados.append(("adaptadores", "fallo" if pendientes else "ok",
                       f"desincronizados: {', '.join(pendientes)} (corre `bin/mesa harness sync`)" if pendientes else "en sincronía con AGENTS.md y adaptadores/"))
    lanzador = _raiz() / MCP
    resultados.append(("bin/mesa-mcp", "ok" if lanzador.exists() and os.access(lanzador, os.X_OK) else "fallo", "lanzador del servidor MCP"))
    ok, detalle = probar_mcp()
    resultados.append(("servidor MCP", "ok" if ok else "fallo", detalle))
    resultados.append(("escáner de Hermes", *escanear_hermes()))
    return resultados


def instrucciones(id_: str) -> str:
    r = _raiz()
    textos = {
        "claude-code": f"cd {r} && claude\n→ /retomar (o «retomemos la partida»). Aprueba el servidor MCP «mesa» de .mcp.json la primera vez.",
        "codex": (
            f"cd {r} && codex\n→ «retomemos la partida» (Codex lee AGENTS.md).\n"
            "MCP: marca el proyecto como de confianza para que lea .codex/config.toml, o regístralo global:\n"
            f"  codex mcp add mesa -- {r}/bin/mesa-mcp\n"
            "El sandbox por defecto (escritura en el workspace) basta; solo `imagen generar` necesita red."
        ),
        "hermes": (
            f"cd {r} && hermes\n→ «retomemos la partida» (Hermes carga AGENTS.md del repo).\n"
            "MCP opcional, en ~/.hermes/config.yaml:\n"
            f"  mcp_servers:\n    mesa:\n      command: {r}/bin/mesa-mcp\n      args: []\n"
            "Skill opcional para retomar desde cualquier directorio: bin/mesa harness instalar-hermes"
        ),
        "opencode": f"cd {r} && opencode\n→ /retomar (.opencode/opencode.json registra el MCP «mesa» con el formato v2; AGENTS.md es nativo).",
        "devin": (
            f"CLI local: cd {r} && devin\n→ «retomemos la partida» (lee AGENTS.md y el MCP «mesa» de .mcp.json).\n"
            "Devin Cloud trabaja en su propia VM con el repo clonado, así que el repo necesita un remoto:\n"
            "  git remote add origin <url> && git push -u origin main\n"
            "Conéctalo en Devin y pide «retomemos la partida» (lee AGENTS.md y usa la CLI en su shell).\n"
            "Al cambiar de harness: bin/mesa pausar --pendiente \"...\" --commit && git push. Al volver: git pull."
        ),
        "gemini-cli": f"cd {r} && gemini\n→ /retomar (GEMINI.md importa AGENTS.md; .gemini/settings.json registra el MCP).",
        "cursor": f"Abre {r} en Cursor: lee AGENTS.md y .cursor/mcp.json registra el MCP (actívalo en los ajustes de MCP).",
        "aider": f"cd {r} && aider\n→ .aider.conf.yml le hace leer AGENTS.md. Sin MCP: ejecuta las tiradas con /run bin/mesa ... (modo limitado).",
        "otro": (
            f"Cualquier agente con shell: ábrelo en {r} y dile «lee AGENTS.md y retoma la partida».\n"
            f"Si soporta MCP por stdio: comando {r}/bin/mesa-mcp.\n"
            "Sin shell ni MCP: los jugadores ejecutan bin/mesa y pegan la salida en el chat."
        ),
    }
    if id_ not in textos:
        raise ValueError(f"harness desconocido: {id_} (usa: {', '.join(textos)})")
    return textos[id_]


def instalar_skill_hermes(forzar: bool = False) -> Path:
    origen = _raiz() / "adaptadores" / "hermes" / "mesa-de-rol" / "SKILL.md"
    destino = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "skills" / "mesa-de-rol" / "SKILL.md"
    if destino.exists() and not forzar:
        raise FileExistsError(f"ya existe {destino} (usa --forzar para reemplazarla)")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(origen.read_text(encoding="utf-8").replace("{RAIZ}", str(_raiz())), encoding="utf-8")
    return destino

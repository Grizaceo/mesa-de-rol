# Harnesses: la misma mesa desde cualquier agente

El narrador es un modelo de IA, y el **harness** es el programa que lo hospeda y le da
herramientas: Claude Code, Codex, Hermes, OpenCode, Devin, Gemini CLI, Cursor… El repo está
hecho para que dé igual cuál se use, e incluso para cambiar de harness entre una sesión y otra.

## Cómo se consigue

| Pieza | Qué la hace portable |
|---|---|
| **Instrucciones** | `AGENTS.md` es el estándar abierto que la mayoría lee de forma nativa. Para los que no, se generan punteros que lo importan (`CLAUDE.md`, `GEMINI.md`, `.aider.conf.yml`). |
| **Herramientas** | Dos vías con el mismo motor: la CLI `bin/mesa`, para cualquier harness con shell, y el servidor MCP `bin/mesa-mcp` (stdio, sin dependencias), para los que hablan MCP. |
| **Estado** | Todo en archivos del repo: nada vive en la memoria del harness. |
| **Traspaso** | `mesa pausar --pendiente "..."` deja escrito dónde quedó todo. `mesa retomar --narrador "<harness>/<modelo>"` lo recoge en cualquier otro. |
| **Procedencia** | Cada evento de la bitácora registra qué `harness/modelo` narraba. |
| **Comandos** | `/retomar`, `/pausar` y `/nueva-historia` salen de un único origen (`adaptadores/comandos/`) y se traducen al formato de cada harness. |

Para regenerar los adaptadores tras cambiar `AGENTS.md` o `adaptadores/`, y para comprobar que todo está en orden:

```bash
bin/mesa harness sync          # regenera los adaptadores
bin/mesa harness verificar     # sincronía, servidor MCP y escáner de inyección de Hermes
bin/mesa harness lista         # qué lee cada harness
bin/mesa harness instrucciones codex   # cómo arrancar en uno concreto
```

## Matriz

Cada harness se probó en esta máquina el 2026-10-15 con su propio comando de listado de MCP, sin abrir sesiones de modelo.

| Harness (versión probada) | Instrucciones | MCP `mesa` | Comandos | Resultado de la prueba |
|---|---|---|---|---|
| **Claude Code** 2.1.300 | `CLAUDE.md` → `@AGENTS.md` | `.mcp.json` | `.claude/commands/` | `claude mcp list`: *mesa — pendiente de aprobación* ✓ |
| **Codex CLI** 0.162.1 | `AGENTS.md` nativo | `.codex/config.toml` (proyecto de confianza) | — | `codex mcp list` con el proyecto como de confianza: *mesa enabled* ✓ |
| **Hermes** | `AGENTS.md` nativo (prioridad: `.hermes.md` > `AGENTS.md` > `CLAUDE.md`) | opcional en `~/.hermes/config.yaml` | skill opcional | El escáner de inyección de Hermes aprueba `AGENTS.md` y `CLAUDE.md` ✓ |
| **OpenCode** v2.0.29 | `AGENTS.md` nativo | `.opencode/opencode.json` (formato v2) | `.opencode/commands/` | `opencode mcp list`: *mesa connected* ✓ |
| **Devin** CLI 3000.11 | `AGENTS.md` nativo | `.mcp.json` | — | `devin mcp list`: *mesa (.mcp.json)* ✓; `devin rules list`: carga AGENTS |
| **Gemini CLI** 0.64.0 | `GEMINI.md` → `@./AGENTS.md` | `.gemini/settings.json` | `.gemini/commands/*.toml` | `gemini mcp list`: *mesa Connected* ✓ |
| **Cursor** (cursor-agent 2026.10.14) | `AGENTS.md` nativo | `.cursor/mcp.json` | — | `cursor-agent mcp list`: *mesa needs approval* ✓ |
| **Aider** | `.aider.conf.yml` → lee `AGENTS.md` | no tiene MCP | — | No instalado aquí; modo limitado con `/run bin/mesa ...` |
| **Cualquier otro** | «lee AGENTS.md y retoma la partida» | `bin/mesa-mcp` si soporta stdio | — | — |

### Particularidades descubiertas al probar

- **OpenCode v2 cambió el formato** de `mcp.<nombre>` a `mcp.servers.<nombre>`. La configuración va en `.opencode/opencode.json` y no en la raíz, porque la CLI de Devin lee `opencode.json` de la raíz con el formato v1 y crearía un servidor fantasma llamado «servers».
- **Codex solo lee `.codex/config.toml` si el proyecto es de confianza.** Codex lo pregunta la primera vez que se abre en el repo; también se puede registrar el servidor de forma global con `codex mcp add mesa -- <ruta>/bin/mesa-mcp`.
- **Claude Code y Cursor piden aprobar** los servidores MCP de proyecto la primera vez.
- **Hermes carga un solo tipo de archivo de contexto** y escanea los del proyecto en busca de inyección de prompts. Si un archivo coincide, lo **bloquea**. Por eso `harness verificar` pasa `AGENTS.md` por el escáner real de Hermes cuando está instalado. Al editar `AGENTS.md`, verifica.
- **Las rutas de MCP son relativas** (`bin/mesa-mcp`): abre el harness desde la raíz del repo. Si uno no lo encuentra, `bin/mesa harness instrucciones <id>` da la ruta absoluta.

## Cambiar de harness a mitad de una historia

```bash
# En el harness A, al parar:
bin/mesa pausar --pendiente "Stepán acaba de decir «Pregunten…»; esperan las preguntas de Jualjin y Crisljin" --commit

# En el harness B (misma máquina), al seguir:
bin/mesa retomar --narrador "opencode/kimi-k3"
```

En otra máquina o en un harness en la nube (Devin Cloud, Codex cloud, Claude Code web), el repo necesita un remoto git:

1. Tras pausar con `--commit`, haz `git push`.
2. El harness remoto clona o hace `git pull` y ejecuta `retomar`.
3. Al terminar, `pausar --commit` y `git push` otra vez.

## Lo que no es portable (y está bien)

- **La aprobación de herramientas**, sea de MCP o de comandos de shell: cada harness pregunta a su manera.
- **La skill de Hermes** (`bin/mesa harness instalar-hermes`): vive fuera del repo, en `~/.hermes/skills`, y es opcional. Sirve para retomar desde cualquier directorio.
- **Los prompts personalizados globales de Codex**: no son de proyecto; basta con decir «retomemos la partida».

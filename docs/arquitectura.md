# Arquitectura

## Estructura

```
AGENTS.md          contrato del director IA: la fuente para todos los harnesses
adaptadores/       origen de los comandos (/retomar, /pausar, /nueva-historia) y de la skill de Hermes
CLAUDE.md GEMINI.md .mcp.json   punteros y configuración MCP que viajan en el repo
bin/mesa           CLI · bin/mesa-mcp: servidor MCP por stdio
reglas/            el reglamento d20-simple (manda)
guias/             jugadores, director, sesión cero, habilidades, combate, condiciones, entorno, imágenes, lecciones, fuente SRD
mesa/              motor en Python: dados, reglas, estado, imágenes, informes, servidor, CLI
visor/             visor web (HTML, CSS y JS sin dependencias)
partidas/<slug>/   partida.json (público), eventos.jsonl, biblia.md, director.md (secreto), retro.md, guardados/, imagenes/
partidas/_plantilla/  esqueleto de las historias nuevas
lecciones/         lecciones.jsonl: lo aprendido entre historias
biblioteca/        imágenes reutilizables con etiquetas y licencia
tests/             python3 -m unittest
docs/              la CLI, esta arquitectura y la atribución del SRD
```

`.claude/`, `.codex/`, `.cursor/`, `.gemini/`, `.opencode/` y `.aider.conf.yml` no viajan: son
configuración de cada máquina y se generan con `bin/mesa harness sync`.

## Jugar, con el harness que quieras

El narrador puede vivir en Claude Code, Codex, Hermes, OpenCode, Devin, Gemini CLI, Cursor o
cualquier agente que lea `AGENTS.md`. El agente ejecuta `bin/mesa retomar --narrador "<harness>/<modelo>"`,
lee el traspaso pendiente y dirige con las herramientas del repo:

- **Cualquier harness con shell:** la CLI `bin/mesa`.
- **Harnesses con MCP:** el servidor `mesa` (`bin/mesa-mcp`), ya configurado para cada uno.

Se puede cambiar de harness entre sesiones: `mesa pausar` en uno y `mesa retomar` en otro.

Para ver la mesa en vivo:

```bash
bin/mesa servir                # http://127.0.0.1:8765
```

**Jugar desde el navegador, con el chat al centro** (como Friends & Fables): el visor habla con el
narrador por ACP (Agent Client Protocol), el mismo protocolo que usan los editores, y la
conversación ocurre en la página, con las tiradas y los cambios como tarjetas dentro del chat y la
ficha, la memoria y los mapas a los lados.

```bash
bin/mesa servir --agente hermes              # Hermes, perfil `narrador`
bin/mesa servir --agente devin               # o Devin (`devin acp`), gemini...
bin/mesa servir --agente-cmd 'hermes -p otro acp'
bin/mesa servir --agente hermes --tailscale  # además, escribir desde tu otro equipo vía `tailscale serve`
```

El agente sigue siendo el mismo, con este `AGENTS.md` y el MCP `mesa` de la partida; lo que piensa y
lo que leen sus herramientas no se muestra. Con `--sin-agente`, el centro muestra la bitácora como
conversación y se narra desde la terminal, como siempre. Ver
[`../guias/seguridad.md`](../guias/seguridad.md).

## Dónde viven los datos

Corriendo desde el repositorio, en `partidas/`, `lecciones/` y `biblioteca/` del propio repo. Con
el paquete instalado (wheel), en `$MESA_RAIZ` si está definida, o en `$XDG_DATA_HOME/mesa-de-rol`
(por defecto `~/.local/share/mesa-de-rol`). El visor, la plantilla y los adaptadores viajan dentro
del paquete (`mesa/recursos/`): `bin/mesa recursos sync` regenera esa copia desde el repositorio y
`mesa harness verificar` avisa si se desincronizó. El paquete nunca lleva partidas, lecciones ni
bibliotecas personales.

## Ideas que lo sostienen

- **Agnóstico del harness.** El estado vive en el repo, el contrato en `AGENTS.md` y las
  herramientas son CLI y MCP con el mismo motor. Narrar desde otro agente es pausar y retomar.
- **El director no inventa datos.** Usa `bin/mesa`, y la tirada queda en la bitácora y en el visor.
- **Público y secreto están separados.** `partida.json` es lo que ven los jugadores; `director.md`
  no lo sirve el visor ni lo imprime la CLI, y el narrador lo lee con su herramienta de lectura de
  archivos, porque los jugadores miran la misma terminal.
- **El contexto no crece con la historia.** El narrador retoma con la memoria (hechos clave dentro
  de un presupuesto, «Hasta ahora» y la crónica), el estado y los últimos eventos, no con toda la
  conversación; se puede abrir una sesión nueva del harness en cualquier escena. El visor solo
  escribe esa memoria, y solo desde este equipo.
- **Afinar sin reentrenar.** Las lecciones son instrucciones con evidencia y alcance (`global`,
  `jugadores`, `reglas:…`, `ambientacion:…`) que se inyectan al director.
- **Imágenes opcionales y baratas por defecto.** Generar solo si se pide, porque gasta crédito y sale
  a la red.

## Desarrollo

```bash
python3 -m unittest discover -s tests -v
```

## Pendiente / ideas

- Modo autónomo: un runner que llame a un modelo por API, para jugar desde Telegram o la web sin un
  agente de terminal (se puede apoyar en el mismo servidor MCP).
- Narración por voz (TTS) de los bloques ESCENA.
- Exportar la bitácora a un dataset de turnos, por si algún día se quiere reentrenar de verdad.

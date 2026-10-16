# Mesa de rol

Partidas de rol por chat donde **una IA dirige la historia** a medida que los jugadores
responden. El repo pone alrededor del director todo lo que una buena mesa necesita:

- **Reglas d20 simples**, compatibles con D&D quinta edición (SRD 5.2.1) y pensadas para principiantes.
- **Dados reales y registrados**: nada de tiradas inventadas.
- **Estado persistente** de la partida: fichas, escena, PNJ, pistas, tramas, recursos y relojes.
- **Un visor web** con los dados animados, las fichas, la escena con su imagen, el mundo y los documentos que encuentran los personajes.
- **Imágenes de ambiente opcionales**: tarjeta local, una imagen existente o una generada.
- **Lecciones entre historias**: cada historia nueva arranca con lo aprendido en las anteriores.

La primera partida, *Los Hermanos del Neva* (Rusia, 1917), está guardada en pausa justo donde quedó.

**Esquemas.** Cada partida declara el suyo en `partida.json`. Las de antes de los esquemas (como
*Los Hermanos del Neva*) son legacy (`d20-simple`, cuatro atributos-bono) y se abren tal como
quedaron. Las nuevas nacen en el esquema 2 (`dnd-2024`, seis características con puntuación,
valores derivados en `mesa/esquemas.py`); su motor de reglas llega con el corte vertical 2024
(P2) y hasta entonces `prueba`, `ataque` y `nivel` se niegan a calcular sobre ellas en vez de
hacerlo mal.

## Jugar, con el harness que quieras

El narrador puede vivir en Claude Code, Codex, Hermes, OpenCode, Devin, Gemini CLI, Cursor o cualquier agente que lea `AGENTS.md`:

```bash
cd ~/.hermes/workspace/ACTIVE/mesa-de-rol
claude      # o: codex · hermes · opencode · devin · gemini · cursor-agent
# luego: «retomemos la partida» (o /retomar donde haya comandos)
```

El agente ejecuta `bin/mesa retomar --narrador "<harness>/<modelo>"`, lee el traspaso pendiente y dirige con las herramientas del repo:

- **Cualquier harness con shell:** la CLI `bin/mesa`.
- **Harnesses con MCP:** el servidor `mesa` (`bin/mesa-mcp`), ya configurado para cada uno.

Se puede cambiar de harness entre sesiones: `mesa pausar` en uno y `mesa retomar` en otro. La matriz, lo verificado y las particularidades de cada harness están en [`guias/harnesses.md`](guias/harnesses.md).

Para ver la mesa en vivo:

```bash
bin/mesa servir                # http://127.0.0.1:8765
```

No hay que instalar nada: Python ≥ 3.10, sin dependencias. `bin/mesa` es la CLI. Si se prefiere
instalarla, `uv tool install .` o `pip install -e .` dejan disponible el comando `mesa`.

**Dónde viven los datos.** Corriendo desde el repositorio, en `partidas/`, `lecciones/` y
`biblioteca/` del propio repo. Con el paquete instalado (wheel), en `$MESA_RAIZ` si está definida,
o en `$XDG_DATA_HOME/mesa-de-rol` (por defecto `~/.local/share/mesa-de-rol`). El visor, la
plantilla y los adaptadores viajan dentro del paquete (`mesa/recursos/`): `bin/mesa recursos
sync` regenera esa copia desde el repositorio y `mesa harness verificar` avisa si se
desincronizó. El paquete nunca lleva partidas, lecciones ni bibliotecas personales.

## La CLI

| Comando | Para qué |
|---|---|
| `mesa partidas` / `usar <slug>` / `nueva <slug> --titulo` | Elegir o crear partida |
| `mesa retomar --narrador "<harness>/<modelo>"` | Empezar o retomar: traspaso pendiente, lecciones, reglas de la casa y estado |
| `mesa pausar --pendiente "..." [--commit]` | Dejar el traspaso para el próximo narrador, en cualquier harness |
| `mesa contexto [--completo]` | Lo que lee el director: lecciones, reglas de la casa, estado y últimos eventos |
| `mesa estado` | Resumen del estado (`--breve`: una línea por personaje con lo que tiene a mano; `--json`: completo) |
| `mesa prueba <quien> <atributo\|habilidad> --cd exigente [--ventaja M] [--desventaja M] [--oficio] [--usar H]` | Prueba d20 |
| `mesa ataque <quien> <objetivo> [--arma] [--cobertura]` | Ataque contra Defensa y daño aplicado |
| `mesa dano` / `tirar 2d6+1` / `suerte 30 --etiqueta` | Daño, tirada libre, d100 de suerte |
| `mesa vida` / `condicion` / `habilidad` / `nivel` | Fichas |
| `mesa vendaje <quien>` / `descanso corto\|largo` | Curarse y recargar habilidades |
| `mesa enemigo agregar <nombre> --plantilla maton` | Amenazas en escena |
| `mesa escena nueva\|editar\|posicion` | Escena actual y posiciones en metros |
| `mesa pnj` / `pista` / `trama` / `misterio` / `recurso` / `reloj` | El mundo |
| `mesa documento agregar\|ver` | Documentos del mundo (cartas, telegramas, periódicos): bloque para el chat y pestaña en el visor |
| `mesa turno --accion "Nombre=..." --resumen "..." [--cambio '...']` | El turno y sus cambios de estado en un solo paso (todos o ninguno), con avisos |
| `mesa revisar` / `regla` / `nota` | Avisos de consistencia, reglas de la casa y notas |
| `mesa imagen ninguna\|elegir\|buscar\|generar\|biblioteca-agregar` | Imagen de la escena |
| `mesa guardar` | «Guardar partida»: resumen copiable más un archivo |
| `mesa retro` / `leccion agregar\|listar\|retirar\|incorporar\|fase` | Retrospectiva y lecciones |
| `mesa servir` | El visor |
| `mesa harness lista\|sync\|verificar\|instrucciones <id>` | Adaptadores por harness y su comprobación |
| `mesa recursos sync\|verificar` | Copia de los recursos que viaja en el paquete instalable |

Todos los comandos que tiran dados o cambian algo dejan un evento en
`partidas/<slug>/eventos.jsonl`, y el visor lo recoge en menos de un segundo.

**Un escritor a la vez.** Los comandos que escriben toman un candado por partida
(`partidas/<slug>/.candado`): si otro proceso está a mitad de escritura, esperan unos segundos
y, si sigue ocupado, avisan con un error legible en vez de pisar el cambio; las lecturas no
esperan. El estado (`partida.json`) y la bitácora (`eventos.jsonl`) se guardan en una sola
transacción con diario, así que un corte a mitad se rehace entero en la siguiente lectura o
escritura, sin medio turno ni eventos duplicados.

## Estructura

```
AGENTS.md          contrato del director IA: la fuente para todos los harnesses
adaptadores/       origen de los comandos (/retomar, /pausar, /nueva-historia) y de la skill de Hermes
CLAUDE.md GEMINI.md .mcp.json .codex/ .opencode/ .gemini/ .cursor/ .claude/ .aider.conf.yml
                   generados por `bin/mesa harness sync` (no editar a mano)
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
```

## Ideas que lo sostienen

- **Agnóstico del harness.** El estado vive en el repo, el contrato en `AGENTS.md` y las herramientas son CLI y MCP con el mismo motor. Narrar desde otro agente es pausar y retomar.
- **El director no inventa dados.** Usa `bin/mesa`, y la tirada queda en la bitácora y en el visor.
- **Público y secreto están separados.** `partida.json` es lo que ven los jugadores; `director.md` no lo sirve el visor ni lo imprime la CLI, y el narrador lo lee con su herramienta de lectura de archivos, porque los jugadores miran la misma terminal.
- **Afinar sin reentrenar.** Las lecciones son instrucciones con evidencia y alcance (`global`, `jugadores`, `reglas:…`, `ambientacion:…`) que se inyectan al director. Ver `guias/lecciones.md`.
- **Imágenes opcionales y baratas por defecto.** Generar solo si se pide, porque gasta crédito y sale a la red. Ver `guias/imagenes.md`.

## Desarrollo

```bash
python3 -m unittest discover -s tests -v
```

## Pendiente / ideas

- Modo autónomo: un runner que llame a un modelo por API, para jugar desde Telegram o la web sin un agente de terminal (se puede apoyar en el mismo servidor MCP).
- Narración por voz (TTS) de los bloques ESCENA.
- Mapa de posiciones dibujado a partir de `escena.posiciones`.
- Exportar la bitácora a un dataset de turnos, por si algún día se quiere reentrenar de verdad.

## Licencias

Las reglas adaptan el SRD 5.2.1 de Wizards of the Coast (CC-BY-4.0); ver [`LICENCIA-SRD.md`](LICENCIA-SRD.md).
Compatible con quinta edición, sin afiliación con Wizards of the Coast.

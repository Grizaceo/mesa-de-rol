# Mesa de rol

Partidas de rol por chat donde **una IA dirige la historia** a medida que los jugadores
responden. El repo pone alrededor del director todo lo que una buena mesa necesita:

- **Reglas d20 simples**, compatibles con D&D quinta edición (SRD 5.2.1) y pensadas para principiantes.
- **Dados reales y registrados**: nada de tiradas inventadas.
- **Estado persistente** de la partida: fichas, escena, PNJ, pistas, tramas, recursos y relojes.
- **Un visor web** con los dados animados, las fichas, la escena con su imagen y el mundo.
- **Imágenes de ambiente opcionales**: tarjeta local, una imagen existente o una generada.
- **Lecciones entre historias**: cada historia nueva arranca con lo aprendido en las anteriores.

La primera partida, *Los Hermanos del Neva* (Rusia, 1917), está guardada en pausa justo donde quedó.

## Jugar

Con Claude Code, o con cualquier agente que lea `AGENTS.md`:

```bash
cd ~/.hermes/workspace/ACTIVE/mesa-de-rol
claude                         # y luego: «retomemos la partida» o «nueva historia»
```

El agente lee `AGENTS.md`, corre `bin/mesa contexto` y dirige con las herramientas del repo.
Para ver la mesa en vivo:

```bash
bin/mesa servir                # http://127.0.0.1:8765
```

No hay que instalar nada: Python ≥ 3.10, sin dependencias. `bin/mesa` es la CLI. Si se prefiere
instalarla, `uv tool install .` o `pip install -e .` dejan disponible el comando `mesa`.

## La CLI

| Comando | Para qué |
|---|---|
| `mesa partidas` / `usar <slug>` / `nueva <slug> --titulo` | Elegir o crear partida |
| `mesa contexto [--completo]` | Lo que lee el director: lecciones, reglas de la casa, estado y últimos eventos |
| `mesa estado` | Resumen del estado (`--json` para el estado completo) |
| `mesa prueba <quien> <atributo\|habilidad> --cd media [--ventaja M] [--desventaja M] [--oficio] [--usar H]` | Prueba d20 |
| `mesa ataque <quien> <objetivo> [--arma] [--cobertura]` | Ataque contra Defensa y daño aplicado |
| `mesa dano` / `tirar 2d6+1` / `suerte 30 --etiqueta` | Daño, tirada libre, d100 de suerte |
| `mesa vida` / `condicion` / `habilidad` / `nivel` | Fichas |
| `mesa enemigo agregar <nombre> --plantilla maton` | Amenazas en escena |
| `mesa escena nueva\|editar\|posicion` | Escena actual y posiciones en metros |
| `mesa pnj` / `pista` / `trama` / `misterio` / `recurso` / `reloj` | El mundo |
| `mesa turno --accion "Nombre=..." --resumen` / `regla` / `nota` | Bitácora y reglas de la casa |
| `mesa imagen ninguna\|elegir\|buscar\|generar\|biblioteca-agregar` | Imagen de la escena |
| `mesa guardar` | «Guardar partida»: resumen copiable más un archivo |
| `mesa retro` / `leccion agregar\|listar\|retirar` | Retrospectiva y lecciones |
| `mesa servir` | El visor |

Todos los comandos que tiran dados o cambian algo dejan un evento en
`partidas/<slug>/eventos.jsonl`, y el visor lo recoge en menos de un segundo.

## Estructura

```
AGENTS.md          contrato del director IA (CLAUDE.md lo importa)
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

- **El director no inventa dados.** Usa `bin/mesa`, y la tirada queda en la bitácora y en el visor.
- **Público y secreto están separados.** `partida.json` es lo que ven los jugadores; `director.md` no lo sirve el visor.
- **Afinar sin reentrenar.** Las lecciones son instrucciones con evidencia y alcance (`global`, `jugadores`, `reglas:…`, `ambientacion:…`) que se inyectan al director. Ver `guias/lecciones.md`.
- **Imágenes opcionales y baratas por defecto.** Generar solo si se pide, porque gasta crédito y sale a la red. Ver `guias/imagenes.md`.

## Desarrollo

```bash
python3 -m unittest discover -s tests -v
```

## Pendiente / ideas

- Modo autónomo: un runner que llame a un modelo por API, para jugar desde Telegram o la web sin un agente de terminal.
- Narración por voz (TTS) de los bloques ESCENA.
- Mapa de posiciones dibujado a partir de `escena.posiciones`.
- Exportar la bitácora a un dataset de turnos, por si algún día se quiere reentrenar de verdad.

## Licencias

Las reglas adaptan el SRD 5.2.1 de Wizards of the Coast (CC-BY-4.0); ver [`LICENCIA-SRD.md`](LICENCIA-SRD.md).
Compatible con quinta edición, sin afiliación con Wizards of the Coast.

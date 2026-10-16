# Seguridad: qué puede hacer cada superficie

Desde P0-02, la CLI y el MCP no tienen las mismas capacidades. Comparten el motor y, para
las acciones de mesa, los mismos efectos; lo que cambia es la autoridad.

| Superficie | Puede |
|---|---|
| **MCP de juego** (`bin/mesa-mcp`) | Todo lo de jugar: `retomar`, `contexto`, `estado`, tiradas, ataques, vida, condiciones, escena, mundo, `turno`, `pausar`, `imagen ninguna`/`buscar`/`elegir` por id de biblioteca, `guardar`, `retro`, `leccion`. |
| **CLI deliberada** (`bin/mesa ...`, la que teclea una persona) | Lo anterior **y** la administración e importaciones: `harness` (instalar la skill, regenerar adaptadores, verificar), `servir`, `documento agregar --archivo`, `imagen generar`, `imagen biblioteca-agregar`, rutas o URLs en `imagen elegir`, y el catálogo externo (`fuentes buscar` y `fuentes actualizar` salen a la red). |

La política vive en `mesa/capacidades.py` y se aplica dos veces: al parsear el comando y,
con el mismo examen, a cada cambio anidado de `turno --cambio`. No basta bloquear el primer
token del texto: `documento agregar T --archivo /fuera/secreto.txt` se rechaza igual suelto
que dentro de un turno, y también a través de un symlink, porque lo que se prohíbe es leer
archivos de fuera de la partida, no una ruta concreta.

## Por qué

- La administración del repo y del harness escribe fuera de la partida (por ejemplo,
  `~/.hermes/skills/`): no es una acción de mesa y no debe dispararla el texto del narrador.
- `documento --archivo` publica en el visor cualquier archivo legible; desde el MCP solo
  entran documentos con el texto que ya está en el chat.
- `imagen generar` gasta crédito de un proveedor externo y envía el prompt afuera;
  `imagen elegir` con ruta o URL importa contenido nuevo. Ambas las decide una persona.
- Las imágenes se eligen por id o archivo de `biblioteca/imagenes/`: lo que está ahí lo puso
  una persona, con su fuente y licencia anotadas (ver [`imagenes.md`](imagenes.md)).
- `fuentes buscar` y `fuentes actualizar` salen a la red y copian datos de un servicio
  externo a `biblioteca/fuentes/`; el motor lee esa caché local y nunca consulta por su
  cuenta. Cada entrada guarda licencia, URL y fecha (ver [`fuente-srd.md`](fuente-srd.md)).

## Contrato AGENTS.md

Desde el 2026-10-16 (aplicado con aprobación del titular), `AGENTS.md` precisa que la
equivalencia CLI/MCP vale para las **acciones de juego**: la administración del harness
(`harness`), el visor (`servir`) y las importaciones externas (`documento --archivo`,
`imagen generar`, `imagen biblioteca-agregar`, rutas/URLs en `imagen elegir`) son **solo de la
CLI deliberada**. La política se aplicaba igual desde el cierre de P0-02; el contrato ahora
lo dice.

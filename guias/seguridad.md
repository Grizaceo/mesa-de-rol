# Seguridad: qué puede hacer cada superficie

Desde P0-02, la CLI y el MCP no tienen las mismas capacidades. Comparten el motor y, para
las acciones de mesa, los mismos efectos; lo que cambia es la autoridad.

| Superficie | Puede |
|---|---|
| **MCP de juego** (`bin/mesa-mcp`) | Todo lo de jugar: `retomar`, `contexto`, `estado`, tiradas, ataques, vida, condiciones, escena, mundo, `turno`, `pausar`, `imagen ninguna`/`buscar`/`elegir` por id de biblioteca, `guardar`, `retro`, `leccion`. |
| **CLI deliberada** (`bin/mesa ...`, la que teclea una persona) | Lo anterior **y** la administración e importaciones: `harness` (instalar la skill, regenerar adaptadores, verificar), `servir`, `documento agregar --archivo`, `imagen generar`, `imagen biblioteca-agregar` y rutas o URLs en `imagen elegir`. |

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

## Propuesta pendiente de aprobación: contrato AGENTS.md

`AGENTS.md` dice hoy que «hay dos vías equivalentes para las herramientas, con el mismo motor
y los mismos resultados». Sigue siendo válido para las acciones de juego, pero ya no para la
administración: el MCP no la expone. Si quieres precisarlo en el contrato, este es el diff
mínimo, **sin aplicar** (modificar `AGENTS.md` requiere aprobación explícita):

```diff
@@ Principios de portabilidad
   - **Hay dos vías equivalentes para las herramientas**, con el mismo motor y los mismos resultados:
     - **MCP:** el servidor `mesa` (`bin/mesa-mcp`), con las herramientas `retomar`, `contexto`,
       `estado`, `prueba`, `ataque`, `tirar`, `suerte`, `turno`, `pausar` y `comando`.
     - **CLI:** `bin/mesa <comando>` (o `python3 -m mesa <comando>`) desde la raíz del repo.
+    - La equivalencia vale para las **acciones de juego**. La administración del harness
+      (`harness`), el visor (`servir`) y las importaciones externas (`documento --archivo`,
+      `imagen generar`, `imagen biblioteca-agregar`, rutas/URLs en `imagen elegir`) son
+      **solo de la CLI deliberada**: el MCP de juego las rechaza. Ver `guias/seguridad.md`.

   Usa MCP si tu harness lo cargó; si no, la CLI.
```

Mientras no se apruebe, la política igual se aplica: es una restricción de seguridad, no un
cambio de reglamento, y la CLI conserva todas las operaciones.

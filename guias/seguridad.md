# Seguridad: qué puede hacer cada superficie

Desde P0-02, la CLI y el MCP no tienen las mismas capacidades. Comparten el motor y, para
las acciones de mesa, los mismos efectos; lo que cambia es la autoridad.

| Superficie | Puede |
|---|---|
| **MCP de juego** (`bin/mesa-mcp`) | Todo lo de jugar: `retomar`, `contexto`, `estado`, tiradas, ataques, vida, condiciones, escena, mundo, memoria (`hecho`, `memoria`), mapas (`mapa`, `mundo`), `turno`, `pausar`, `imagen ninguna`/`buscar`/`elegir` por id de biblioteca, `guardar`, `retro`, `leccion`. |
| **CLI deliberada** (`bin/mesa ...`, la que teclea una persona) | Lo anterior **y** la administración e importaciones: `harness` (instalar la skill, regenerar adaptadores, verificar), `servir`, `documento agregar --archivo`, `imagen generar`, `imagen biblioteca-agregar`, rutas o URLs en `imagen elegir`, y el catálogo externo (`fuentes buscar` y `fuentes actualizar` salen a la red). |
| **Visor** (el navegador, `bin/mesa servir`) | Leer la partida **filtrada por lo que saben los personajes** (`mesa/vista.py`), **escribir la memoria** (`POST /api/memoria`), **jugar con la ficha propia** (`POST /api/tirar`: pruebas, ataques, daño, descansos, vida, inventario) y, si se arrancó con `--agente`, **hablar con el narrador** (`POST /api/chat`). Crear o configurar campañas (`POST /api/campana`) también vale desde la sala; los permisos del agente y cambiar de agente o de sesión son solo del **anfitrión**. Enemigos, escena y mapas los cambia el narrador. |

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

## La escritura del visor

El jugador corrige la memoria desde el navegador, así que el servidor del visor dejó de ser
solo lectura en ese único punto. La petición se acepta solo si:

- viene de este equipo (dirección de loopback) y con `Host` local (`127.0.0.1`, `localhost`,
  `[::1]`), lo que corta el DNS rebinding; con `servir --host 0.0.0.0` los demás equipos leen,
  pero no escriben;
- trae el token de esa ejecución del servidor (`X-Mesa-Token`, que `GET /api/visor` entrega solo
  con `Host` local; no se guarda en disco ni en la bitácora) y, si el navegador manda `Origin`,
  es de este equipo (en cualquier puerto, porque un proxy local, como la vista previa de un
  harness, lo cambia);
- el cuerpo es JSON de menos de 16 KiB, lo que obliga a una consulta CORS previa que el servidor
  no responde: una página ajena no puede enviarla.

Cada cambio pasa por el candado de la partida y deja un evento con `autor: jugador` y `via: visor`.
Los textos se validan como en la CLI (vacío, duplicado, largo máximo) y el visor los escapa al
pintarlos.

**Por Tailscale** (`servir --tailscale`): también escribe quien llega por `tailscale serve` con
`Host` del propio nodo (`<equipo>.<tailnet>.ts.net`) y la cabecera `Tailscale-User-Login` de un
usuario autorizado (por defecto, el dueño del nodo; o los de `--tailscale-usuario`). Esa cabecera la
pone tailscaled, que atiende la conexión y la pasa desde 127.0.0.1; un cliente de fuera no puede
fabricarla. Los demás usuarios de la tailnet leen, pero no escriben.

## La sala online (`servir --sala`)

Una sala deja jugar desde fuera (por ejemplo, detrás de un túnel) con una **clave de sala**
(`X-Mesa-Sala`): `--sala` genera una de 128 bits y `--clave-sala` exige al menos 16 caracteres.
Con sala activa, **leer** la API también pide la clave; las imágenes de `/media/` siguen abiertas.

Hay dos papeles:

- **Anfitrión**: este equipo (loopback y `Host` local) o el dueño por Tailscale. Puede todo lo
  del visor, incluido lo que pone a trabajar herramientas del equipo: responder a los permisos
  del agente y cambiar de agente o de sesión.
- **Invitado** (la clave): primero reclama un PJ (`POST /api/reclamar`, un PJ por persona) y a
  partir de ahí escribe en el chat **firmando siempre como ese PJ** y tira o cambia **solo su
  ficha**. Nunca la de otro jugador ni la de un enemigo, y nunca permisos ni agente. Sí puede
  crear o configurar campañas: nunca se pisan PJ existentes ni una biblia escrita a mano, la
  partida activa del narrador no cambia y la sala crea como mucho 5 campañas por arranque.

Lo que sale de la API pasa por `vista.py`. Los PJ que juega una persona se ven enteros; de los
demás (enemigos, PNJ y PJ con `piloto: narrador`) solo lo que se ve. El nombre real de quien no
es conocido no viaja en el estado, la zona, la bitácora, los errores ni el texto del narrador,
y su vida, CA, ataque y modificadores tampoco, salvo `revelar_stats`. Un ataque se dirige por el
nombre público: el real no se resuelve, así que no sirve para adivinarlo.

Los números del cuerpo se validan (sin `NaN` ni infinitos, con rangos) y el estado se guarda
como JSON estricto. El visor envía una CSP que no permite scripts en línea ni nada de fuera.

## El chat con el narrador

Escribir en el chat pone a trabajar a un agente con acceso al equipo, así que:

- **El agente recibe solo el MCP `mesa` de esa partida**, por ACP, con `MESA_RAIZ` y `MESA_PARTIDA`;
  ese MCP se niega a actuar sobre otra partida o a cambiar de partida. El perfil `narrador` de Hermes
  no trae MCP propios: uno propio apuntaría a la raíz del repo y podría escribir en otra partida
  (pasó una vez en pruebas; de ahí la regla).
- **Permisos:** las herramientas de la mesa y la lectura pasan solas; editar archivos, solo dentro de
  la carpeta de la partida (por ejemplo `director.md`); cualquier otra cosa (un comando, una escritura
  fuera) espera en el chat a que el jugador la permita o la rechace (5 minutos, y si no, se rechaza).
- **Secretos:** del agente se muestra solo su respuesta y un aviso genérico de lo que hace («consulta
  sus notas»). Lo que piensa y lo que leen sus herramientas (por ejemplo `director.md`) no sale del
  servidor ni queda en `chat.jsonl`.
- La sesión del agente se guarda en `partidas/<slug>/.narrador.json`, que el visor no sirve.

## Contrato AGENTS.md

Desde el 2026-10-16 (aplicado con aprobación del titular), `AGENTS.md` precisa que la
equivalencia CLI/MCP vale para las **acciones de juego**: la administración del harness
(`harness`), el visor (`servir`) y las importaciones externas (`documento --archivo`,
`imagen generar`, `imagen biblioteca-agregar`, rutas/URLs en `imagen elegir`) son **solo de la
CLI deliberada**. La política se aplicaba igual desde el cierre de P0-02; el contrato ahora
lo dice.

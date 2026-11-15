# La CLI

El motor de la mesa se maneja con `bin/mesa` (o `python3 -m mesa`, o el comando `mesa` si instalas
el paquete). El servidor MCP `bin/mesa-mcp` expone el mismo motor por herramientas.

## Comandos

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
| `mesa escena nueva\|editar\|posicion [--celda C4] [--cierre "..."]` | Escena actual, posiciones en metros (y en casillas si hay mapa) y su línea de crónica al cerrarla |
| `mesa mapa zona --dibujo "..." [--leyenda c=significado]` / `mapa ver` | Mapa de la zona en cuadrícula, dibujado en texto: el visor lo pinta y `turno` lo imprime con las distancias |
| `mesa mundo lugar\|ruta\|aqui\|quitar\|ajustar\|ver` | Mapa del mundo: lugares conocidos con coordenadas, rutas y dónde están |
| `mesa hecho agregar\|editar\|fijar\|soltar\|archivar\|restaurar\|listar` | Hechos clave de la memoria de la historia |
| `mesa memoria hasta-ahora\|escena\|presupuesto\|ver` | «Hasta ahora», crónica de escenas y cuánto entra al contexto |
| `mesa pnj` / `pista` / `trama` / `misterio` / `recurso` / `reloj` | El mundo |
| `mesa documento agregar\|ver` | Documentos del mundo (cartas, telegramas, periódicos): bloque para el chat y pestaña en el visor |
| `mesa turno --accion "Nombre=..." --resumen "..." [--cambio '...']` | El turno y sus cambios de estado en un solo paso (todos o ninguno), con avisos |
| `mesa revisar` / `regla` / `nota` | Avisos de consistencia, reglas de la casa y notas |
| `mesa imagen ninguna\|elegir\|buscar\|generar\|biblioteca-agregar` | Imagen de la escena |
| `mesa guardar` | «Guardar partida»: resumen copiable más un archivo |
| `mesa retro` / `leccion agregar\|listar\|retirar\|incorporar\|fase` | Retrospectiva y lecciones |
| `mesa servir [--agente hermes\|devin\|gemini] [--agente-cmd '...'] [--tailscale]` | El visor; con agente, el chat con el narrador por ACP |
| `mesa harness lista\|sync\|verificar\|instrucciones <id>` | Adaptadores por harness y su comprobación |
| `mesa recursos sync\|verificar` | Copia de los recursos que viaja en el paquete instalable |
| `mesa fuentes listar\|buscar\|actualizar\|ver` | Catálogo externo con procedencia (Open5e, documento `srd-2024`): licencia, URL y fecha por entrada; la red solo en `buscar` y `actualizar` |
| `mesa migrar [diagnosticar\|copiar <destino>] [--fichas ...]` | Diagnóstico `dry-run` y migración en copia validada de `d20-simple` a `dnd-2024` (sin tocar la partida original) |

Todos los comandos que tiran dados o cambian algo dejan un evento en
`partidas/<slug>/eventos.jsonl`, y el visor lo recoge en menos de un segundo.

## Un escritor a la vez

Los comandos que escriben toman un candado por partida (`partidas/<slug>/.candado`): si otro
proceso está a mitad de escritura, esperan unos segundos y, si sigue ocupado, avisan con un error
legible en vez de pisar el cambio; las lecturas no esperan.

El estado (`partida.json`) y la bitácora (`eventos.jsonl`) se guardan en una sola transacción con
diario, así que un corte a mitad se rehace entero en la siguiente lectura o escritura, sin medio
turno ni eventos duplicados.

## La configuración de cada harness es local

`bin/mesa harness sync` genera en tu máquina la configuración que usa tu agente: la del servidor
MCP, los comandos de barra (`/retomar`, `/pausar`, `/nueva-historia`) y los punteros a
`AGENTS.md`. Son archivos generados, no editables a mano: la fuente es `AGENTS.md` y
`adaptadores/`.

`bin/mesa harness verificar` comprueba que lo que hay en tu máquina está al día y que el servidor
MCP responde. En un clon recién descargado, lo que falta no es «desincronizado»: está sin generar.

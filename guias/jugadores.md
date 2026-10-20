# Guía para jugadores

## Cómo jugar

Escribe qué hace tu personaje, en primera persona o como prefieras:

> **Jualjin:** «Sujeto la barca y le pregunto al marinero quién lo persigue.»
> **Crisljin:** «Reviso el paquete sin abrirlo y busco marcas.»

- Si son varios jugadores, pueden escribir juntos o por separado. El director no avanza hasta tener la acción de todos.
- Puedes preguntar cosas del mundo («¿cuántos metros hay hasta la calle?») o de las reglas («¿esto es Agilidad?») sin que pase el tiempo.

## Los dados

- **Pruebas:** 1d20 + tu atributo contra una dificultad de 10 (sencilla), 15 (exigente) o 20 (difícil).
- **Antes de algo arriesgado**, el director te dice qué atributo usas, la dificultad, qué ganas y qué arriesgas. Tú confirmas o cambias de plan.
- **Ventaja:** si tu compañero te ayuda o ambos persiguen lo mismo de distinta forma, tiras 2d20 y te quedas con el mayor. **Desventaja:** el menor.
- **20 natural:** éxito siempre, y además un crítico que te deja algo extra. **1 natural:** falla siempre.
- **Puedes pedir la tirada con nombres de D&D** («tirada de percepción»). El director la traduce con [`habilidades.md`](habilidades.md).
- **Los dados son reales** y se ven en el visor. Nadie los cambia.

## Tu ficha

| Atributo | Para qué sirve |
|---|---|
| **Fuerza** | Cargar, golpear, aguantar |
| **Agilidad** | Moverte, esconderte, apuntar |
| **Ingenio** | Notar, recordar, reparar, inventar |
| **Corazón** | Convencer, leer a la gente, tener valor |

Además de los atributos, la ficha tiene:

- **Oficio (+2):** lo que tu personaje hace desde siempre. Si la acción encaja, recuérdaselo al director.
- **Habilidades:** se gastan y se recargan (por escena, por combate). El visor muestra si están disponibles, y el director te recuerda en cada turno lo que tienes a mano.
- **Condiciones:** estados como *Empapado*. El visor marca el atributo afectado.

## Pedidos útiles

| Pedido | Qué hace |
|---|---|
| «Guardar partida» | Resumen copiable con fichas, inventario, PNJ, pistas y pendientes |
| «¿Qué sabemos de X?» | El director repasa pistas y PNJ |
| «Regla de la casa: …» | Cambiar una regla para el resto de la partida; queda escrita |
| «Congela la escena» | Pausa para hablar de reglas o de la historia |

## El visor

Abre `http://127.0.0.1:8765` mientras se juega. Al centro está la conversación; arriba, la escena,
el día y los plazos.

- **Si el visor tiene narrador** (`bin/mesa servir --agente hermes`), escribes tu acción abajo y el
  narrador responde ahí mismo. Las tiradas (con los dados rodando), los golpes, las pistas, los
  documentos y los hechos clave aparecen como tarjetas dentro de su respuesta; tócalas para verlas en
  su panel. Si pide permiso para algo que no es de la mesa, te lo pregunta en el chat. «Detener»
  corta su turno y «Sesión nueva del narrador» lo hace retomar desde la memoria de la historia.
- **Si se narra desde la terminal**, el centro muestra lo mismo como conversación, en vivo.

A los lados (en pantallas estrechas, con los botones de la barra) van estas pestañas:

- **Ficha:** tu personaje, su vida, atributos, habilidades, equipo y quién es; y las amenazas en escena.
- **Zona:** la escena y su mapa en cuadrícula (cada casilla, 1,5 m). Toca una ficha para medir
  desde ella y una casilla para ver a cuántos metros queda.
- **Mundo:** el mapa de los lugares que conocen, dónde están y las rutas. Arrastra para moverte,
  usa + y − (o la rueda) para el zoom y toca un lugar para ver a cuánto queda.
- **Hechos:** la memoria de la historia, lo que el narrador lee al retomar en vez de toda la
  conversación. **Puedes corregirla:** editar un hecho, fijarlo (entra siempre), archivarlo (deja de
  entrar), anotar uno nuevo y reescribir «Hasta ahora» o la crónica de una escena. Solo se edita
  desde este mismo equipo; lo que corriges queda en la bitácora como tuyo.
- **Ambientación:** época, lugar, tono, estilo, las reglas de la mesa y las reglas de la casa.
- **Registro:** PNJ, pistas, documentos, tramas, preguntas abiertas, recursos, tiradas y bitácora.

Un punto junto a una pestaña avisa que ahí hay algo nuevo.

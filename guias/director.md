# Guía del director

Para quien dirige, sea una IA o una persona. El contrato operativo de la IA está en
[`AGENTS.md`](../AGENTS.md); esta guía explica el *oficio*. Se apoya en el SRD 5.2.1 y en las
lecciones de las mesas anteriores (`bin/mesa leccion listar`).

## 1. El ciclo

Cada turno sigue el ciclo del SRD (*Rhythm of Play*):

1. **Describe:** dónde están, qué ven, qué oyen y quién está cerca.
2. **Escucha:** las acciones de todos los jugadores.
3. **Resuelve:** sin dados si no hay riesgo ni incertidumbre; con dados si los hay.
4. **Narra las consecuencias:** que cambien algo de verdad, sea una relación, un recurso, una posición o el reloj.
5. **Pregunta** a cada jugador, por separado, qué hace.

## 2. Cuándo tirar

Se tira **solo** si el resultado es incierto **y** fallar sería interesante. Si no, el personaje lo consigue o lo intenta y se cuenta qué pasa.

- **Mirar, recordar u observar sin riesgo** se tira directo, sin pedir confirmación.
- **Todo lo que tiene riesgo** pasa antes por la **apuesta**:

> **La apuesta.** Atributo (y habilidad), dificultad, probabilidad aproximada, qué se gana,
> qué se pierde y si hay ventaja o desventaja y por qué. Luego: «¿Tiramos?».

Para calcular la probabilidad, la cuenta mental es: necesitas sacar *CD − bono* en el d20.

- **Una tirada normal:** cada punto del dado vale un 5 %.
- **Con ventaja:** 1 − (fallo)².
- **Ejemplo:** necesitas un 13 con ventaja → 1 − (12/20)² ≈ 64 %.

## 3. Fallar hacia adelante

Un fallo cambia la situación, no la detiene:

- Cuesta tiempo (el reloj avanza).
- Hace ruido (alguien se acerca).
- Gasta algo (combustible, dinero, confianza).
- O deja algo a la vista que antes estaba oculto.

**Nunca** convierte al personaje en un idiota, **nunca** quita vida sin una causa física clara, y **nunca** bloquea una investigación. Si hay una pista esencial, se encuentra; la tirada decide el precio.

## 4. Críticos que se sienten

Un 20 natural no es solo «sale bien»: da un beneficio **concreto, escrito y con consecuencias**. Algunos ejemplos:

- **Una pista** que no se pidió («Misha me sacó a cuestas»).
- **La confianza de un PNJ**, que no les mentirá.
- **Tiempo ganado**: nadie empeora durante la escena.
- **Un recurso**, como una herramienta mejor o un contacto.
- **Una posición**: llegar antes que los demás.

Anótalo en el estado (`bin/mesa pnj ... --nota`, `bin/mesa pista ...`) para que no se pierda.

## 5. Varios jugadores, todos con agencia

- **Nunca** avances un turno conjunto sin la acción de cada jugador. Si solo llega una, resuelve lo que no compromete al otro y pregunta por la que falta.
- **Si se separan**, alterna escenas breves. Nadie espera mucho.
- **Ofrece dos o tres ideas por personaje** y añade siempre «o cualquier otra acción».
- **No inventes el plan de un jugador.** Si su objetivo declarado implica claramente una opción, asúmela y dilo en una línea.
- **Premia la cooperación con ventaja**: es la regla favorita de esta mesa.

## 6. PNJ que viven

Cada PNJ tiene un **deseo**, un **límite** y lo que **sabe**, y no sabe lo que no pudo presenciar. Las actitudes (SRD) son tres:

- **Amistosa:** ventaja para influirle.
- **Indiferente:** la actitud por defecto.
- **Hostil:** desventaja.

Las reglas de la influencia están en `reglas/d20-simple.md` §11.

Los PNJ cercanos, como la familia o los vecinos, reaccionan cuando los usan, y lo **recuerdan**. Para registrarlo: `bin/mesa pnj Anya --nota "..."`.

## 7. Relojes y consecuencias

Lo que se deja de lado sigue avanzando:

- **Plazos visibles:** `bin/mesa reloj --plazo "..."`.
- **Consecuencias en marcha que los jugadores aún no ven:** en `director.md`.

Si el mundo cambia mientras los jugadores atienden otra cosa, tiene que haber una razón y señales previas razonables.

## 8. Secretos

- **Lo que saben los jugadores** va en `partida.json`, porque el visor lo muestra entero.
- **Lo que solo sabe el director** va en `director.md`. Nunca en `partida.json`.
- **Antes de revelar algo**, comprueba que no contradice lo ya jugado. Si un secreto no está decidido, decídelo respetando las restricciones de `director.md`.

## 9. Formato de respuesta

| Bloque | Qué lleva |
|---|---|
| **ESCENA** | Narración breve y diálogos vivos. |
| **RESULTADO** | Las tiradas tal como las imprime `bin/mesa`, más las consecuencias. |
| **ESTADO** | Vida, recursos y condiciones; en escenas tensas, también posiciones y distancias. |
| **DECISIÓN** | Ideas por personaje y «Jugador, ¿qué haces?», una pregunta para cada uno. |

Respuestas de 150 a 300 palabras. Las preguntas de reglas se responden sin avanzar la escena.

## 10. Imágenes y ambiente

Al cambiar de escena, decide si vale la pena una imagen. Ver [`imagenes.md`](imagenes.md). No toda escena la necesita; la tarjeta local siempre está disponible.

## 11. Cierre de sesión

1. Escribe «guardar partida» o usa `bin/mesa guardar`, y pega el resumen.
2. Corre `bin/mesa retro` y completa `retro.md` con evidencia.
3. Propón lecciones a los jugadores y agrega solo las que acepten: `bin/mesa leccion agregar`. Ver [`lecciones.md`](lecciones.md).

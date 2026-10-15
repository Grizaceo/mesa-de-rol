# Lecciones entre historias

La idea es que cada historia nueva salga mejor que la anterior: un director más ajustado a esta
mesa y a lo que funciona.

## Por qué lecciones y no reentrenar un modelo

Reentrenar un modelo para una mesa de dos jugadores es caro, lento y opaco. Lo que realmente
cambia de una historia a otra cabe en **instrucciones cortas con evidencia**, y el director las
lee al empezar. Eso tiene tres ventajas:

- **Se ve.** Cada lección es una línea legible en `lecciones/lecciones.jsonl`.
- **Se discute.** Los jugadores aprueban o rechazan cada lección.
- **Se revierte.** Una lección se retira con un motivo y queda el historial.

Si algún día se quiere reentrenar de verdad, la materia prima ya existe: la bitácora
(`eventos.jsonl`) guarda las acciones textuales de los jugadores, los resúmenes, las tiradas y
los cambios de reglas de cada sesión.

## Alcances

Cada lección declara a qué partidas aplica:

| Alcance | Aplica a | Ejemplo |
|---|---|---|
| `global` | Cualquier historia con cualquier mesa | «Nunca avances un turno sin la acción de todos» |
| `jugadores` | Cualquier historia con este grupo | «Miden en metros», «quieren crudeza alta» |
| `reglas:<reglamento>` | Partidas con ese reglamento | Ajustes a `d20-simple` |
| `ambientacion:<etiqueta>` | Partidas con esa etiqueta en `ambientacion.etiquetas` | `ambientacion:historica`: «marca qué es real y qué inventado» |

`bin/mesa contexto` incluye solo las lecciones **activas** cuyo alcance corresponde a la partida.

## Estados y fases

| Estado | Qué significa | Cómo |
|---|---|---|
| `activa` | Se inyecta al director | `leccion agregar` |
| `incorporada` | Ya está escrita en `AGENTS.md` (u otro texto que el director lee siempre): repetirla solo mete ruido | `leccion incorporar L001 --donde "AGENTS.md § En cada turno"` |
| `retirada` | Dejó de valer | `leccion retirar L007 --motivo "..."` |

Una lección puede tener **fase** `sesion-cero`: solo se inyecta mientras la partida no ha jugado
ninguna escena (`leccion fase L009 sesion-cero`; `leccion fase L009 siempre` la devuelve).
`leccion listar --todas` muestra todas, con su estado.

## Ciclo de vida

1. **Durante el juego:** cuando los jugadores corrigen algo («no pases de turno», «en metros»), se registra con `bin/mesa regla` si es una regla, o queda en la bitácora con `bin/mesa nota`.
2. **Al cerrar la sesión:** `bin/mesa retro` da números y una plantilla. El director escribe `partidas/<slug>/retro.md` con evidencia (turno o tirada concretos).
3. **Proponer:** el director propone 3–6 lecciones, cada una con alcance, categoría y evidencia.
4. **Confirmar:** los jugadores aprueban, corrigen o rechazan. **Solo lo aprobado entra:**
   ```bash
   bin/mesa leccion agregar "Texto de la lección" --alcance jugadores --categoria tono \
     --evidencia "Qué pasó y cuándo" --origen "slug (fecha)"
   ```
5. **Revisar:** al empezar una historia nueva (en la sesión cero) se repasan las lecciones de `jugadores`. Las que ya no valen se retiran:
   ```bash
   bin/mesa leccion retirar L007 --motivo "En historias de terror prefieren menos humor"
   ```

## Cómo escribir una buena lección

- **Una instrucción**, en imperativo, que se pueda cumplir o incumplir en un turno concreto.
- **Con evidencia:** qué pasó y dónde. Sin evidencia no hay lección.
- **Sin nombres propios** de la historia en lecciones `global` o `jugadores`. «La madre» se generaliza a «los PNJ cercanos».
- **Ni obvia ni genérica.** «Sé buen director» no sirve.

Las categorías disponibles son: agencia, ritmo, reglas, dados, tono, formato, mundo, pnj, seguridad y visor.

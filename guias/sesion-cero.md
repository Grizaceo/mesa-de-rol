# Sesión cero

Son quince minutos antes de la primera escena de una historia nueva. Nacen de la primera mesa
(lección L009): en *Los Hermanos del Neva*, varios turnos se fueron en cambiar reglas a mitad de
escena. Todo lo que se acuerde aquí va a `partida.json` (`reglas` y `reglas_casa`) o a la biblia.

## 1. Lo que ya sabemos de esta mesa

Muéstralo y pregunta si sigue valiendo:

```bash
bin/mesa leccion listar --alcance jugadores
```

Hoy dice:

- Distancias en metros.
- Set completo de dados de D&D.
- Ventaja por cooperar.
- El 20 natural es crítico y el 1 natural es fallo.
- Crudeza alta.

## 2. Preguntas para cerrar antes de empezar

| Tema | Pregunta | Dónde queda |
|---|---|---|
| Dados | ¿d20 como siempre? ¿Daño por dado? ¿Críticos con beneficio extra? | `reglas` |
| Unidades | ¿Metros? | `reglas.unidades` |
| Muerte | ¿Modo letal o «fuera de combate» sin muerte? | `reglas.muerte` |
| Crudeza | ¿Cuán gráfica puede ser la violencia? ¿Hay temas que se consultan antes o que no aparecen (*líneas y velos*)? | `reglas.crudeza` y la biblia |
| Inspiración heroica | ¿Activarla? (repetir un dado; ver el reglamento, §15) | regla de la casa |
| Ritmo | ¿Respuestas de 150 a 300 palabras? ¿Más narración o más acción? | la biblia |
| Imágenes | ¿Ninguna, de la biblioteca o generadas? ¿Generar gasta crédito: está bien? | la biblia |
| Personajes | ¿Quién juega a quién? ¿Atributos, oficio, habilidad y equipo con dado? | `partida.json` |
| Pausa | Una señal para congelar la escena sin explicaciones («congela») | la biblia |

## 3. Crear la partida

```bash
bin/mesa nueva la-isla-sin-nombre --titulo "La isla sin nombre"
# Editar: partidas/la-isla-sin-nombre/biblia.md, partida.json (personajes) y director.md
bin/mesa contexto --completo        # lo que lee el director antes de la primera escena
bin/mesa escena nueva --titulo "..." --lugar "..." --hora "..."
bin/mesa imagen ninguna             # o elegir / generar
```

## 4. Seguridad durante el juego

- Cualquiera puede decir «congela» o «corta» sin dar explicaciones.
- Ante contenido especialmente sensible, el director pregunta en una línea antes de narrarlo.
- La crudeza acordada se puede cambiar a mitad de partida como regla de la casa.

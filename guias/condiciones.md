# Condiciones

Las condiciones son estados con efectos fijos. Vienen del glosario del SRD 5.2.1, sin las
mágicas (*Charmed*, *Paralyzed*, *Petrified*), más algunas propias de la mesa.

- **Cómo se aplican en la CLI:** `bin/mesa condicion <quien> agregar <nombre>` busca el nombre en el catálogo y aplica sus efectos. En las tiradas, la desventaja se suma sola.
- **Condiciones nuevas:** se crean con `--efecto "..." --desventaja agilidad`.
- **Cómo se quitan:** `bin/mesa condicion <quien> quitar <nombre>`.

| Condición | Efecto en esta mesa | Equivalente SRD |
|---|---|---|
| **Agarrado** | No puede moverse. Desventaja al atacar a quien no sea su captor. Se libera con su acción: Fuerza (Atletismo) o Agilidad (Acrobacias) contra la CD del agarre. | Grappled |
| **Apresado** | Atado, enredado en una red o aplastado. No se mueve, ataca con desventaja y tiene desventaja en Agilidad. Los ataques contra él tienen ventaja. | Restrained |
| **Asustado** | Desventaja en pruebas y ataques mientras vea la fuente del miedo. No puede acercarse a ella. | Frightened |
| **Aturdido** | Incapacitado. Los ataques contra él tienen ventaja. | Stunned |
| **Cegado** | Falla todo lo que requiera vista. Ataca con desventaja y lo atacan con ventaja. | Blinded |
| **Derribado** | En el suelo. Ataca con desventaja. Cuerpo a cuerpo (a 1,5 m o menos) lo atacan con ventaja; a distancia, con desventaja. Levantarse cuesta la mitad del movimiento. | Prone |
| **Ensordecido** | No oye; falla lo que requiera oído. | Deafened |
| **Envenenado** | Desventaja en pruebas y ataques. | Poisoned |
| **Incapacitado** | No puede actuar ni hablar. | Incapacitated |
| **Inconsciente** | Incapacitado y derribado, suelta lo que tenga. Los ataques contra él tienen ventaja. | Unconscious |
| **Oculto** | Escondido tras una prueba de Agilidad (Sigilo) CD 15, fuera de la vista. Quien lo busca necesita igualar su total con Ingenio (Percepción). Se pierde al hacer ruido o atacar. | Invisible (por Hide) |
| **Agotamiento** (niveles) | −2 por nivel a toda prueba d20. Un descanso largo quita un nivel. En el nivel 6, fuera de combate (en modo letal, muerte). | Exhaustion |
| **Fuera de combate** [mesa] | Vida en 0: no actúa. Un aliado lo estabiliza con una acción si llega a su lado. No muere salvo modo letal. | 0 Hit Points / Unconscious |
| **Empapado** [mesa] | Ropa mojada y frío: desventaja en Agilidad hasta secarse o cambiarse. | (agua helada, ver entorno) |

## Crear condiciones para una historia

Una condición nueva necesita tres cosas:

- **Nombre corto.**
- **Efecto en una línea.**
- **Atributos afectados**, si los hay.

Por ejemplo, para *Ensangrentado*:

```bash
bin/mesa condicion Jualjin agregar ensangrentado --efecto "Sangra: pierde 1 de vida al final de cada escena hasta que lo venden" --desventaja todo
```

Prefiere condiciones que se quiten con una acción concreta, como secarse, vendarse o dormir.

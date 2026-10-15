# Combate

Basado en *Combat* y *Damage and Healing* del SRD 5.2.1, simplificado. El combate es una de
las tres formas de resolver una escena, no la principal: los enemigos negocian, se rinden y huyen.

## Antes de empezar: mostrar la mesa

Al estallar un combate, el director dice:

- **Dónde está cada uno**, en metros: «el del rifle a 12 m, entre tú y la calle».
- **Las amenazas perceptibles**, con vida, Defensa, protección, ataque y daño, separando lo conocido de lo que todavía no se sabe.
- **Si hay armas de fuego.** Siempre, en cuanto se perciben.

Para cargar a los enemigos en el visor:

```bash
bin/mesa enemigo agregar "Matón del muelle" --plantilla maton
bin/mesa enemigo agregar "Guardia del puente" --plantilla guardia
```

## La ronda

1. Los jugadores declaran sus acciones, todos, antes de resolver nada.
2. El director las resuelve en el orden que tenga sentido.
3. Actúan los enemigos que sigan en pie.

Opcional (SRD): iniciativa con `bin/mesa prueba <quien> agilidad` (sin dificultad) y orden de mayor a menor. Quien es sorprendido tira con desventaja.

Cada turno, un personaje puede **moverse ~9 m** y hacer **una acción**: atacar, correr, destrabarse, esquivar, ayudar, esconderse, influir, preparar, buscar, usar un objeto o proteger. El catálogo está en `reglas/d20-simple.md` §7. Gritar una frase corta no gasta la acción.

## Atacar

```bash
bin/mesa ataque Jualjin "Matón del muelle" --arma bichero              # cuerpo a cuerpo: Fuerza
bin/mesa ataque Crisljin "Guardia del puente" --arma honda --cobertura media   # a distancia: Agilidad
bin/mesa ataque "Matón del muelle" Crisljin                             # el enemigo usa su bono de ataque
```

- **Tirada:** 1d20 + Fuerza (cuerpo a cuerpo) o Agilidad (a distancia, o cuerpo a cuerpo con un arma ligera si se pide `--atributo agilidad`), contra la **Defensa** del objetivo.
- **Cobertura:** media (+2), si otra persona o un objeto tapa la mitad; tres cuartos (+5), detrás de un muro bajo o un pilote. Con cobertura total no se puede apuntar.
- **Disparar con un enemigo encima:** desventaja si hay un enemigo a 1,5 m que te ve.
- **Atacar sin ver:** desventaja. **Atacar sin ser visto:** ventaja, y quien se escondía queda delatado al atacar.
- **20 natural:** acierta siempre y es crítico, con dados de daño dobles. **1 natural:** falla siempre.

## Daño

- **El dado del arma** (ver `reglas/d20-simple.md` §9) menos la **protección** del objetivo, con un **mínimo de 1**.
- **[mesa]** No se suma el atributo al daño.
- **El cálculo y la vida restante** se muestran siempre: `daño 1d8: 6 − protección 1 = 5 → Matón 3/8`.
- **A mano:** `bin/mesa dano Jualjin --arma bichero --objetivo "Matón"` o `bin/mesa vida Jualjin -3`.

## Maniobras sin arma (SRD: *Unarmed Strike*)

| Maniobra | Cómo se resuelve |
|---|---|
| **Golpe** | Ataque con Fuerza. A puño limpio hace 1 de daño; con algo en la mano, 1d4 (arma improvisada del SRD). Mínimo 1 tras la protección |
| **Agarrar** | El objetivo tira Fuerza o Agilidad (elige) contra CD **10 + Fuerza del agarrador** (+2 si su oficio aplica). Si falla, queda **Agarrado** |
| **Empujar o derribar** | Igual que agarrar. Si falla, retrocede 1,5 m o queda **Derribado** |

## Ayudar y proteger

- **Ayudar:** el aliado tiene **ventaja** en su próximo ataque o prueba. Gasta la acción de quien ayuda.
- **Proteger:** con una habilidad como «¡A mi hermano no!» (Jualjin), recibir el golpe dirigido a otro. Se aplica la protección propia.

## Cero de vida

| Situación | Qué pasa |
|---|---|
| Un personaje llega a 0 | **Fuera de combate** (la CLI lo marca sola). No muere. |
| Un aliado llega a su lado | Lo estabiliza con una acción. Con un vendaje después del combate recupera 3. |
| Un enemigo llega a 0 | Muere o queda inconsciente, según lo que se quería (SRD: *Knocking Out*). |
| **Modo letal** (solo si se acordó) | Salvaciones de muerte del SRD: 1d20 al inicio de cada turno; 10 o más es éxito; tres éxitos estabilizan y tres fallos matan; un 1 cuenta como dos fallos y un 20 devuelve 1 de vida. Recibir daño en 0 suma un fallo (dos si es crítico). |

## Diseñar encuentros justos

El SRD calcula la dificultad con presupuestos de experiencia. Para una mesa de dos o tres personajes de nivel bajo basta esta guía:

| Dificultad | Composición | Qué esperar |
|---|---|---|
| **Baja** | 1–2 matones o 1 perro | Un par de sustos; nadie cae |
| **Media** | 1 guardia armado + 1 matón, o 3 matones | Alguien puede quedar fuera de combate |
| **Alta** | 2 guardias armados, o un rifle con cobertura | Hace falta astucia, huir o negociar |

Reglas de oro:

- **Nunca un pelotón por sorpresa.**
- **Más enemigos significa más riesgo de mala racha.** Si hay más de dos por personaje, que sean frágiles.
- **Los enemigos que caen a la mitad de su vida** (SRD: *Bloodied*) piensan en rendirse o huir.

### Amenazas de referencia

Son las plantillas de la CLI:

| Plantilla | Vida | Defensa | Ataque | Daño | Protección | Comparable en el SRD |
|---|---|---|---|---|---|---|
| `rata` | 3 | 10 | +0 | 1d2 | 0 | — |
| `perro` | 5 | 12 | +1 | 1d4 | 0 | Mastiff: CA 12, 5 PG |
| `maton` | 8 | 12 | +1 | 1d6 | 0 | Bandit: CA 12, 11 PG |
| `guardia` | 10 | 14 | +2 | porra 1d6 / rifle 1d12 | 1 | Guard: CA 16, 11 PG |

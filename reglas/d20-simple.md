# Reglamento d20-simple

El reglamento de la mesa: lo bastante simple para principiantes y lo bastante cercano a D&D
quinta edición como para que el vocabulario de los jugadores («tirada de percepción», «tengo
ventaja», «¡20 natural!») funcione tal cual.

- **Base:** el *System Reference Document 5.2.1* (SRD 5.2.1, reglas de 2024, CC-BY-4.0). Atribución en [`LICENCIA-SRD.md`](../LICENCIA-SRD.md).
- **Simplificaciones y reglas propias:** marcadas con **[mesa]**.
- **Qué parte del SRD respalda cada regla:** [`guias/fuente-srd.md`](../guias/fuente-srd.md).
- **Si una historia cambia algo:** lo anota en su `biblia.md` o como regla de la casa (`bin/mesa regla`). Como en el SRD, *la excepción manda sobre la regla general*.

---

## 1. Cómo fluye el juego

Se repite siempre el mismo ciclo (SRD, *Rhythm of Play*):

1. El director describe la escena.
2. Los jugadores dicen qué hacen sus personajes.
3. El director narra el resultado. Si el resultado es incierto **y** fallar tendría consecuencias interesantes, se tiran dados. Si es fácil o no hay riesgo, sale sin tirar.

El juego tiene **tres pilares**: interacción social, exploración y combate. No toda escena es combate.

## 2. Atributos [mesa]

El SRD usa seis características. Aquí hay cuatro, cada una con un bono de −1 a +4:

| Atributo | Sirve para | Equivale en el SRD a |
|---|---|---|
| **Fuerza** | Cargar, empujar, resistir esfuerzo, golpear, aguantar frío o veneno | Fuerza + Constitución |
| **Agilidad** | Correr, equilibrio, esconderse, reflejos, puntería | Destreza |
| **Ingenio** | Reparar, improvisar, investigar, recordar, notar detalles, curar | Inteligencia + Sabiduría (percepción, medicina, supervivencia) |
| **Corazón** | Empatía, valor, persuasión sincera, leer a las personas, actuar | Carisma + Sabiduría (perspicacia) |

El bono no mide lo que vale una persona. Solo dice en qué es buena *bajo presión*.

## 3. Pruebas d20

> **1d20 + atributo + bonos ≥ dificultad → éxito.**

Las dificultades (CD) son las del SRD:

| Dificultad | CD | Ejemplo |
|---|---|---|
| Muy fácil | 5 | Saltar un charco con prisa |
| **Sencilla** | **10** | Trepar a una barca amarrada con el muelle mojado |
| **Exigente** | **15** | Mentirle a un guardia alerta |
| **Difícil** | **20** | Nadar contra la corriente del río en otoño |
| Muy difícil | 25 | Forzar una cerradura de banco con un clavo |
| Casi imposible | 30 | Convencer a un acreedor de perdonar la deuda |

Cómo se aplica:

- Se iguala o supera la CD para tener éxito.
- La CD la fija el director. **[mesa]** Antes de tirar algo con riesgo, el director **anuncia la apuesta**: atributo, dificultad, probabilidad aproximada, qué se gana y qué se pierde. Los jugadores confirman. Mirar o recordar sin riesgo se tira directo.
- Un fallo **no** es una catástrofe ni vuelve tonto al personaje. Cuesta tiempo, hace ruido, gasta recursos o complica la situación. Una investigación nunca se bloquea por una sola tirada.

En la CLI: `bin/mesa prueba Crisljin sigilo --cd exigente`.

### Habilidades

Los jugadores pueden pedir tiradas con nombres de habilidad del SRD (Percepción, Historia, Sigilo, Engaño…). Cada habilidad usa un atributo de la mesa: la tabla completa está en [`guias/habilidades.md`](../guias/habilidades.md). La CLI acepta el nombre directamente: `bin/mesa prueba Jualjin historia --cd 10`.

### Resistir (tiradas de salvación) [mesa]

Cuando algo amenaza al personaje y no lo eligió, el SRD pide una salvación. Aquí es una prueba normal con el atributo que corresponda:

| Amenaza | Atributo |
|---|---|
| Fuerza bruta, veneno, frío, agotamiento | Fuerza |
| Esquivar una caída, un derrumbe, una explosión | Agilidad |
| Ver a través de un engaño, una ilusión o una trampa | Ingenio |
| Miedo, presión mental, mantener la propia identidad | Corazón |

## 4. Oficio: la competencia de la mesa

Cada personaje tiene un **oficio** que dice en qué situaciones suma **+2**. Es el bonificador de competencia del SRD para los niveles 1 a 4. Ejemplo: «Oficio de pescador: Fuerza al remar, tirar redes o manejar cargas con cuerdas».

- El oficio no se suma dos veces.
- **[mesa, opcional]** A partir del nivel 5 sube a +3, como en el SRD.

En la CLI: `--oficio`.

## 5. Ventaja y desventaja

- **Ventaja:** se tiran 2d20 y vale el más alto. **Desventaja:** 2d20 y vale el más bajo.
- **No se acumulan:** tres motivos de ventaja siguen siendo 2d20.
- **Se anulan:** si hay al menos uno de cada, se tira 1d20, aunque sean tres motivos contra uno.
- **Ayudar da ventaja** (acción *Help* del SRD). **[mesa]** Si dos personajes gastan su acción en el mismo objetivo, cada uno a su manera y de forma creíble, quien lidera tira con ventaja. Esto reemplaza al antiguo «+1 por ayudar».
- **Las condiciones** pueden imponer desventaja (por ejemplo, *Empapado* en Agilidad). La CLI la aplica sola.
- **Con una segunda tirada**, como la Inspiración heroica, solo se vuelve a tirar uno de los dos dados (SRD).

En la CLI: `--ventaja "Jualjin distrae"` o `--desventaja "a oscuras"`.

## 6. Veinte natural, uno natural y críticos [mesa]

- **20 natural** (el dado muestra 20): éxito automático en **cualquier** prueba d20. Además es **crítico**:
  - Fuera de combate, da un beneficio extra concreto que el director deja por escrito: una pista, la confianza de alguien o tiempo ganado. Tiene que *marcar la historia*.
  - En combate, los dados de daño se tiran dos veces y el modificador no se duplica (SRD, *Critical Hits*).
- **1 natural:** fallo automático, con complicación pero sin desastre gratuito.
- **Dos excepciones:** lo imposible no se tira, así que ningún 20 lo arregla; y lo trivial tampoco se tira, así que ningún 1 lo arruina.
- **Con ventaja o desventaja**, cuenta solo el dado que queda.
- **Valen para todos**, también para los enemigos.

> El SRD aplica el 20 y el 1 naturales solo a los ataques. Extenderlos a toda prueba es una
> variante muy común que esta mesa pidió expresamente.

## 7. Acciones

En combate, cada personaje puede **moverse** (unos 9 m) y hacer **una acción** por turno. Fuera de combate, las acciones dan el lenguaje para declarar. Basadas en el SRD:

| Acción | Qué hace aquí |
|---|---|
| **Atacar** | Tirada de ataque contra la Defensa del objetivo |
| **Correr** (*Dash*) | El doble de movimiento |
| **Destrabarse** (*Disengage*) | Alejarse sin que el enemigo adyacente aproveche para golpear |
| **Esquivar** (*Dodge*) | Hasta tu próximo turno, los ataques contra ti tienen desventaja |
| **Ayudar** (*Help*) | Da ventaja a la próxima prueba o ataque de un aliado, o estabiliza a alguien en 0 de vida |
| **Esconderse** (*Hide*) | Agilidad (Sigilo) CD 15, fuera de la vista. Quedas **Oculto** y tu total es la CD para encontrarte |
| **Influir** (*Influence*) | Cambiar la actitud de alguien (ver §11) |
| **Preparar** (*Ready*) | «Si cruza la puerta, le tiro la red»: actúas cuando ocurre el disparador |
| **Buscar** (*Search*) | Ingenio (Percepción, Medicina, Supervivencia) o Corazón (Perspicacia) |
| **Estudiar** (*Study*) | Ingenio para recordar o deducir (Historia, Investigación, Naturaleza…) |
| **Usar un objeto** (*Utilize*) | Una cuerda, una palanca, un vendaje |
| **Proteger** [mesa] | Interponerse para que un ataque te apunte a ti (habilidades como «¡A mi hermano no!») |

Hablar con frases cortas no gasta la acción; convencer a alguien sí. Además, cualquier cosa razonable se puede intentar: el director dice si hace falta tirada y cuál.

## 8. Combate (resumen; detalle en [`guias/combate.md`](../guias/combate.md))

1. **Posiciones.** El director dice dónde está cada uno, con distancias en metros, y qué amenazas se perciben: vida, Defensa, protección, daño y si hay armas de fuego. Distingue lo conocido de lo desconocido.
2. **Orden.** **[mesa]** Por defecto se resuelve en el orden que tenga sentido: primero los jugadores, luego los enemigos que sigan en pie. Opcional (SRD): iniciativa con 1d20 + Agilidad, y desventaja si te sorprenden.
3. **Turnos.** Cada uno se mueve y hace una acción. No se dan ataques extra por narrar una combinación larga.

**Atacar:**

- La tirada es 1d20 + Fuerza (cuerpo a cuerpo) o + Agilidad (a distancia) + oficio si aplica, contra la **Defensa** del objetivo.
- La Defensa base de un personaje es 12. Se suma cobertura: media +2, tres cuartos +5.
- Al acertar, se tira el **dado de daño del arma** y se resta la **protección** del objetivo, con un mínimo de 1.
- **[mesa]** No se suma el atributo al daño (el SRD sí lo suma).

**Fuera de combate:**

- Con 0 de vida, el personaje queda **fuera de combate**, no muerto.
- Un aliado lo estabiliza con una acción si llega a su lado.
- **[mesa]** No hay muerte permanente salvo que se acuerde un **modo letal**. En ese caso se usan las salvaciones de muerte del SRD: 1d20 sin modificador, 10 o más es éxito; tres éxitos estabilizan y tres fallos matan; un 1 cuenta como dos fallos y un 20 devuelve 1 de vida.
- **Derrotar sin matar** (SRD): quien deja a alguien en 0 con un ataque cuerpo a cuerpo puede dejarlo inconsciente con 1 de vida.

**Enemigos:** pueden rendirse, negociar o huir. Los animales no atacan sin motivo.

En la CLI: `bin/mesa ataque Jualjin "Matón" --arma bichero`.

## 9. Daño y dados de armas

| Dado | Armas típicas (equivalente SRD) |
|---|---|
| d4 | Cuchillo de trabajo (daga), honda, puño con algo en la mano, arma improvisada (SRD: 1d4) |
| d6 | Cuchillo de pescador, porra, hacha de mano, lanza (SRD: lanza 1d6) |
| d8 | Bichero o tridente (SRD: tridente 1d8), garrote grande |
| d10 | Pistola (SRD: 1d10), hacha de estibador |
| d12 | Rifle o mosquete (SRD: mosquete 1d12) |
| d100 | No es de daño: pura suerte («¿hay alguien en esa calle? 30%») → `bin/mesa suerte 30 --etiqueta "..."` |

Las armas de fuego son peligrosas: el director avisa en cuanto son perceptibles.

## 10. Curación y descanso

- **Dormir con comida y en un lugar seguro** (unas 8 horas; descanso largo del SRD) devuelve toda la vida y quita un nivel de Agotamiento.
- **Un vendaje** fuera de combate devuelve 3 de vida, una vez por personaje entre descansos.
- **[mesa, opcional]** Un descanso corto de 1 hora recarga lo que diga «por descanso».
- Un descanso se interrumpe si empieza un combate o alguien recibe daño.

## 11. Interacción social

Las actitudes de un PNJ, según el SRD, son tres:

- **Amistoso:** tienes ventaja para influirlo.
- **Indiferente:** la actitud por defecto.
- **Hostil:** tienes desventaja.

Cuando un personaje intenta **influir**:

1. Si el PNJ **quiere** hacerlo, no hace falta tirada.
2. Si le **repugna**, tampoco hay tirada: no lo hace.
3. Si **duda**, se tira:
   - Corazón (Persuasión, Interpretación) o Ingenio (Engaño), según el enfoque.
   - CD 15 por defecto.
   - Si falla, no se puede insistir de la misma manera hasta que cambie algo (el SRD dice 24 horas).

**[mesa]** Las mentiras acumuladas a la misma persona suben la dificultad o dan desventaja, y el director lo dice en la apuesta.

## 12. Condiciones

Las condiciones son estados con efectos fijos: Agarrado, Apresado, Asustado, Aturdido, Cegado, Derribado, Empapado, Ensordecido, Envenenado, Incapacitado, Inconsciente, Oculto, Agotamiento y Fuera de combate. El catálogo completo está en [`guias/condiciones.md`](../guias/condiciones.md).

En la CLI: `bin/mesa condicion Crisljin agregar empapado`.

## 13. Entorno

Caídas, agua helada, frío extremo, oscuridad, asfixia y viajes, adaptados del SRD y en metros, están en [`guias/entorno.md`](../guias/entorno.md).

## 14. Progreso por hitos

Al cerrar una **misión significativa** (no por puntos de experiencia):

- **Vida:** +2 al máximo y +2 a la actual.
- **Mejora**, a elegir una: **+1 a un atributo** (máximo +4) **o** una habilidad sencilla que proponga el director.
- **Equipo:** puede mejorar con causa narrativa (botas para superficies resbaladizas, un casco adaptado). Todo bono queda escrito y con un uso concreto.

En la CLI: `bin/mesa nivel Crisljin --atributo ingenio`.

## 15. Inspiración heroica (opcional, SRD)

- **Cuándo se da:** el director la concede por algo especialmente heroico, fiel al personaje o divertido.
- **Para qué sirve:** se gasta para repetir **un** dado justo después de tirarlo, y vale la nueva tirada.
- **Límite:** cada personaje tiene como máximo una. Si recibe otra, debe dársela a un compañero que no tenga.
- **Activación:** está apagada salvo que la mesa la active como regla de la casa.

## 16. Seguridad y tono

En la sesión cero se acuerda la crudeza (cuánta violencia y cuán gráfica), los temas que se consultan antes y el modo letal. El director pregunta antes de introducir algo especialmente sensible. Ver [`guias/sesion-cero.md`](../guias/sesion-cero.md).

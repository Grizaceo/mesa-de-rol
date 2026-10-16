# Fuente: qué sale del SRD 5.2.1 y qué es de la mesa

Este documento es el *grounding* del reglamento: cada regla de `reglas/d20-simple.md`,
contrastada con el **System Reference Document 5.2.1** (reglas de D&D de 2024, publicado por
Wizards of the Coast bajo CC-BY-4.0). Atribución en [`LICENCIA-SRD.md`](../LICENCIA-SRD.md).
Fuente consultada: el PDF oficial, «SRD_CC_v5.2.1», descargado de D&D Beyond el 2026-10-15.

Las secciones del SRD se citan por su nombre en inglés para poder buscarlas en el PDF.

| Regla de la mesa | Sección del SRD 5.2.1 | Relación |
|---|---|---|
| Ciclo describir → declarar → narrar; tres pilares | *Playing the Game › Rhythm of Play* | **Igual** |
| Tirar solo con incertidumbre y fallo significativo | *Ability Checks*: «a chance of meaningful failure… uncertain and narratively interesting» | **Igual** |
| 1d20 + modificador ≥ CD | *D20 Tests* | **Igual** |
| Dificultades 5/10/15/20/25/30 | *Typical Difficulty Classes* | **Igual** |
| Cuatro atributos en vez de seis | *The Six Abilities* | **Simplificada:** Fuerza+Constitución, Destreza, Inteligencia+Sabiduría, Carisma(+Sabiduría) |
| 18 habilidades → atributo de la mesa | *Skills* | **Simplificada** (tabla en `habilidades.md`) |
| Oficio +2 | *Proficiency Bonus* (+2 en niveles 1–4) | **Equivalente:** competencia acotada a un oficio |
| Ventaja y desventaja: 2d20, no se acumulan, se anulan, solo se repite un dado | *Advantage/Disadvantage* | **Igual** |
| Ayudar da ventaja | *Help [Action]* | **Igual**. La regla de la casa R2 la extiende a «mismo objetivo de distinta forma» |
| 20 natural acierta y 1 natural falla | *Rolling 20 or 1* (solo tiradas de ataque) | **Extendida** [mesa] a toda prueba d20 |
| Crítico: dados de daño dobles | *Critical Hits* | **Igual** en combate. Fuera de combate, beneficio narrativo [mesa] |
| Inspiración heroica (opcional) | *Heroic Inspiration* | **Igual**, apagada por defecto |
| Acciones: atacar, correr, destrabarse, esquivar, ayudar, esconderse, influir, preparar, buscar, estudiar, usar | *Actions* y glosario | **Igual**, sin *Magic*. Se añade *Proteger* [mesa] |
| Esconderse: Agilidad (Sigilo) CD 15; el total es la CD para encontrarte | *Hide [Action]* | **Igual** (la condición *Invisible* se llama aquí *Oculto*) |
| Actitudes y CD 15 de influencia | *Social Interaction*, *Influence [Action]*, *Friendly*, *Hostile* | **Igual** (CD 15 fija; el SRD usa «15 o la Inteligencia del objetivo») |
| Defensa (CA) y cobertura +2/+5 | *Armor Class*, *Cover* | **Igual** en cobertura. Defensa base 12 [mesa] |
| Desventaja al disparar con un enemigo adyacente; atacar sin ver | *Ranged Attacks in Close Combat*, *Unseen Attackers and Targets* | **Igual** |
| Daño = dado del arma; protección resta con mínimo 1 | *Damage Rolls* (suma la característica) | **Desviación** [mesa]: no se suma el atributo; la protección es de la mesa |
| Dados de armas d4–d12 | *Equipment › Weapons* (Dagger 1d4, Spear 1d6, Trident 1d8, Pistol 1d10, Musket 1d12) | **Equivalente** |
| Vida 0 = fuera de combate, sin muerte salvo modo letal | *Dropping to 0 Hit Points*, *Death Saving Throws* | **Simplificada.** El modo letal usa las salvaciones del SRD |
| Derrotar sin matar | *Knocking Out a Creature* | **Igual** |
| Estabilizar | *Stabilizing a Character* (Help + Medicina CD 10) | **Simplificada:** una acción a su lado [mesa] |
| Descanso largo → toda la vida | *Long Rest* | **Igual en efecto** (sin dados de golpe) |
| Vendaje 3 de vida, una vez entre descansos | *Short Rest* (dados de golpe) | **Simplificada** [mesa] |
| Condiciones (sin las mágicas) | *Conditions* del glosario | **Igual en efectos**, en castellano. Se añaden *Empapado* y *Fuera de combate* [mesa] |
| Agotamiento −2 por nivel | *Exhaustion [Condition]* | **Igual** (en el nivel 6, fuera de combate si no hay modo letal) |
| Caídas 1d6 cada 3 m; caer al agua CD 15 | *Falling [Hazard]* | **Igual**, en metros |
| Agua helada, frío y calor extremos, asfixia | *Environmental Effects*, *Suffocation* | **Igual**, con Fuerza en lugar de Constitución |
| Luz, penumbra y oscuridad | *Vision and Light* | **Igual** |
| Ritmos de viaje | *Travel Pace* | **Igual**, en km |
| Dificultad de encuentros | *Combat Encounters* (presupuesto de PX) | **Simplificada** a una tabla para 2–3 personajes |
| Amenazas de referencia | Stat blocks *Mastiff*, *Bandit*, *Guard* | **Equivalente** escalado |
| Miedo y estrés | *Fear and Mental Stress* (discutirlo al inicio de la campaña) | **Igual en espíritu:** Corazón para resistir, y hablarlo en la sesión cero |
| Progreso por hitos | *Level Advancement* (PX o hitos) | **Simplificada:** +2 vida y +1 atributo o una habilidad |

## Lo que se dejó fuera a propósito

- **Clases, especies, conjuros y objetos mágicos.** Las historias de la mesa empiezan sin magia, y se pueden añadir por biblia si una historia la necesita.
- **Acciones adicionales, reacciones y ataques de oportunidad.** Sobran en una mesa de principiantes; el ataque de oportunidad se puede activar como regla de la casa.
- **Dados de golpe** y la tabla de puntuaciones 1–20, porque el bono ya es el atributo.

## Catálogo externo (Open5e)

Desde P1.2, `bin/mesa fuentes` copia objetos del SRD 2024 desde la API de Open5e
(`document__key=srd-2024`) a `biblioteca/fuentes/open5e/`, con licencia, permalink, URL y
fecha por entrada, y los mapea al esquema interno de la mesa. El motor nunca sale a la red:
lee esa caché y, si algo no está, avisa en vez de inventarlo. La red solo se toca con
`fuentes buscar` y `fuentes actualizar` (una petición a la vez, timeout de 15 s, hasta 3
intentos, sin reintentar errores HTTP). Cada respuesta se verifica contra el documento: un
objeto de otra fuente se rechaza. La caché es regenerable y no viaja en git.

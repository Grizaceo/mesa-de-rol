# Cobertura 2024: implementado, manual y no soportado

Estado a 2026-10-16 (cierre de P1). Este documento enumera por separado lo que el repo ya
resuelve para D&D 2024, lo que la mesa decide a mano y lo que no está soportado. No promete
«todo D&D»: lo que no está en la primera tabla, no está automatizado.

## Implementado

| Área | Qué | Dónde | Pruebas |
|---|---|---|---|
| Esquema de partida | `schema_version` 2 y reglamento `dnd-2024`: seis características con puntuación 1–30, nivel 1–20, derivados (modificador, competencia) calculados; validación al cargar, escribir y crear | `mesa/esquemas.py` | `tests/test_esquemas.py` |
| Partida nueva | La plantilla y `nueva` crean partidas 2024; la histórica (`d20-simple`, esquema 1) se abre sin alterarse | `partidas/_plantilla/`, `mesa/estado.py` | `tests/test_esquemas.py` |
| Catálogo externo | Conjuros y reglas del documento `srd-2024` vía Open5e, con caché, licencia, URL y fecha por entrada; verificación de fuente en cada respuesta y al leer; sin red se sirve la caché o se avisa | `mesa/fuentes.py` | `tests/test_fuentes.py` |
| Fixture autorizada | Un conjuro (Fireball) y una condición (Prone) con procedencia, cotejados contra el PDF oficial | `tests/fixtures/2024/` | `tests/test_fuentes.py` |

## Manual (la mesa decide; el motor no lo automatiza)

| Área | Cómo se resuelve hoy |
|---|---|
| Motor de reglas 2024 | Pendiente (corte vertical, P2): `prueba`, `ataque` y `nivel` se niegan a calcular sobre una partida 2024 en vez de hacerlo mal |
| Conjuros y condiciones en juego | El director aplica a mano el texto de la caché o la fixture hasta que exista el motor |
| Ficha (clase, especie, trasfondo, dotes, equipo) | Por acordar con los jugadores (entrada de P2/P4) |
| Visor | Tarjetas 2024 (seis características con modificador, CA, HP temporal, condiciones) pendientes (P3.1) |

## No soportado

| Área | Por qué |
|---|---|
| Condiciones desde Open5e `srd-2024` | El documento no trae condiciones (0 en la consulta del 2026-10-16); la fixture se transcribió del PDF oficial |
| Reglas fuera del SRD (PHB comercial y equivalentes) | Licencia: no se descarga ni se publica corpus comercial |
| Sincronización con apps de fichas | Sin app ni versión confirmada (P4) |
| Multijugador remoto | Sin topología confirmada (P5) |

## Cotejo con el SRD 5.2.1 (muestra)

El 2026-10-16 se comparó la fixture contra el PDF oficial `SRD_CC_v5.2.1`: Fireball
(estadísticas, componentes, descripción, niveles superiores y clases) y la condición Prone
coinciden palabra por palabra con lo que sirve Open5e (documento `srd-2024`) y con el PDF.
La D&D 5e API (`/api/2024/conditions/prone`) coincide también en esa condición; se usa como
contraste, nunca se mezcla en la caché. Muestra pequeña: no certifica el resto del catálogo.

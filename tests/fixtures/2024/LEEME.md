# Fixtures 2024

Muestras mínimas del SRD 5.2.1 en el mismo formato que la caché de `mesa/fuentes.py`
(`{cache, fuente, datos}`): sirven para las pruebas y para el corte vertical de reglas
2024 sin depender de la red. No son corpus: un conjuro y una condición, con procedencia.

| Archivo | Origen | Verificación |
|---|---|---|
| `conjuro/srd-2024_fireball.json` | API de Open5e, documento `srd-2024` (regenerable con `bin/mesa fuentes actualizar conjuro srd-2024_fireball`) | Cotejado palabra por palabra el 2026-10-16 contra el PDF oficial `SRD_CC_v5.2.1`: estadísticas, componentes, descripción, niveles superiores y clases coinciden |
| `condicion/srd-2024_prone.json` | Transcrito del PDF oficial `SRD_CC_v5.2.1`, glosario «Prone [Condition]» (Open5e no trae condiciones en `srd-2024`) | La transcripción usa comillas rectas; el PDF usa tipográficas. Texto por lo demás idéntico |

Atribución: material del System Reference Document 5.2.1, © Wizards of the Coast,
bajo CC-BY-4.0 (ver [`LICENCIA-SRD.md`](../../../LICENCIA-SRD.md)).

Notas de cotejo:

- El PDF se descargó a `/tmp` solo para comparar; no se guarda en el repositorio.
- Contraste con la D&D 5e API (`/api/2024/conditions/prone`): su texto coincide con el
  del PDF en esta muestra. Se cita como contraste; no se mezcla en la caché.
- Muestra pequeña: el cotejo no certifica el resto del catálogo de Open5e.

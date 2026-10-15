---
name: mesa-de-rol
description: Dirigir o retomar partidas de rol por chat con el repo mesa-de-rol. Úsala cuando
  pidan "retomemos la partida", "sigamos la historia", "nueva historia de rol", "guardar
  partida" o mencionen Los Hermanos del Neva, Jualjin o Crisljin, aunque la sesión haya
  empezado en otro directorio.
metadata:
  hermes:
    tags:
      - rol
      - juego
---

# Mesa de rol

El repo está en `{RAIZ}`. Todo el estado de las partidas vive ahí: no dependas de la memoria
de sesiones anteriores.

1. Trabaja desde la raíz del repo (`cd {RAIZ}`): así se carga su `AGENTS.md`, que es el contrato del director.
2. Empieza con `bin/mesa retomar --narrador "hermes/<modelo>"`. Si el servidor MCP `mesa` está configurado, usa sus herramientas; si no, la CLI.
3. Sigue `AGENTS.md`:
   - Anuncia la apuesta antes de toda tirada con riesgo.
   - No avances sin la acción de cada jugador.
   - Tira siempre con la herramienta.
   - Registra cada turno.
4. Para parar: `bin/mesa pausar --pendiente "..."` (con `--commit` si se acordó).

"""Motor de reglas D&D 2024 (P2, corte vertical SRD 5.2.1 CC-BY-4.0).

Implementa las mecánicas nucleares del SRD 5.2.1 para partidas con `schema_version: 2`
(`reglamento: dnd-2024`):
- Seis características (1–30), modificadores `(puntuación - 10) // 2`, competencia (+2..+6)
  y pericia (×2), separando pruebas de característica/habilidad y tiradas de salvación.
- Ataques contra CA (+ cobertura), daño con modificador de característica, críticos que
  duplican dados (no modificadores), resistencias (÷2 hacia abajo), inmunidades (0) y
  vulnerabilidades (×2), sin restar la protección plana de `d20-simple`.
- Propiedades (`sutil`, `versatil`, `dos-manos`, `ligera`, etc.) y maestrías de armas
  (`rozar`/`graze`, `agotar`/`sap`, `mellar`/`nick`, `derribar`/`topple`, `empujar`/`push`).
- PG temporales (no se acumulan; absorben daño primero), caída a 0 PG, muerte instantánea
  por daño masivo, salvaciones de muerte y Agotamiento 2024 (−2 × nivel a toda prueba d20
  y −1,5 m × nivel a la velocidad; nivel 6 = muerte).
- Iniciativa (1d20 + mod Destreza; Sorprendido impone desventaja en 2024), descansos corto
  (con gasto de Dados de Golpe) y largo, conjuros (espacios, CD = 8 + comp + mod,
  concentración) y degradación honesta (`requiere_resolucion_manual` + `adjudicar`).
"""

from __future__ import annotations

from .catalogo import CLASES_2024, COBERTURA, CONDICIONES_2024, HABILIDADES_2024
from .combate import ataque, caracteristica_de_arma, prueba, tirar_iniciativa
from .personaje import (
    aplicar_vida, bono_competencia, clase_de, condicion_de_catalogo, descanso,
    fijar_vida_temporal, ficha_inicial, gastar_dados_golpe, mod_caracteristica,
    monedas_de, resolver_atributo, salvacion_muerte, velocidad_efectiva, dano,
)
from .magia import adjudicar, lanzar_conjuro, usar_consumible

__all__ = [
    "CLASES_2024", "COBERTURA", "CONDICIONES_2024", "HABILIDADES_2024",
    "adjudicar", "aplicar_vida", "ataque", "bono_competencia", "caracteristica_de_arma",
    "clase_de", "condicion_de_catalogo", "dano", "descanso", "ficha_inicial",
    "fijar_vida_temporal", "gastar_dados_golpe", "lanzar_conjuro", "mod_caracteristica",
    "monedas_de", "prueba", "resolver_atributo", "salvacion_muerte", "tirar_iniciativa",
    "usar_consumible", "velocidad_efectiva",
]

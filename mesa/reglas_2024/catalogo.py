"""Catálogo SRD 5.2.1: habilidades, condiciones, coberturas y clases."""

from __future__ import annotations

import re

from ..texto import norm

HABILIDADES_2024 = (
    ("Acrobacias", "destreza", "Acrobatics"),
    ("Trato con animales", "sabiduria", "Animal Handling"),
    ("Arcanos", "inteligencia", "Arcana"),
    ("Atletismo", "fuerza", "Athletics"),
    ("Engaño", "carisma", "Deception"),
    ("Historia", "inteligencia", "History"),
    ("Perspicacia", "sabiduria", "Insight"),
    ("Intimidación", "carisma", "Intimidation"),
    ("Investigación", "inteligencia", "Investigation"),
    ("Medicina", "sabiduria", "Medicine"),
    ("Naturaleza", "inteligencia", "Nature"),
    ("Percepción", "sabiduria", "Perception"),
    ("Interpretación", "carisma", "Performance"),
    ("Persuasión", "carisma", "Persuasion"),
    ("Religión", "inteligencia", "Religion"),
    ("Juego de manos", "destreza", "Sleight of Hand"),
    ("Sigilo", "destreza", "Stealth"),
    ("Supervivencia", "sabiduria", "Survival"),
)

_HABILIDAD_POR_CLAVE: dict[str, tuple[str, str]] = {}
for _es, _attr, _en in HABILIDADES_2024:
    _HABILIDAD_POR_CLAVE[norm(_es)] = (_attr, _es)
    _HABILIDAD_POR_CLAVE[norm(_en)] = (_attr, _es)

_ATRIBUTOS_SOLO_LEGACY = {
    "agilidad": "destreza",
    "agi": "destreza",
    "ingenio": "inteligencia o sabiduria",
    "ing": "inteligencia o sabiduria",
    "corazon": "carisma",
    "cor": "carisma",
}

_TIPOS_DANO_ALIAS = {
    "acid": "acido", "acido": "acido",
    "bludgeoning": "contundente", "contundente": "contundente",
    "cold": "frio", "frio": "frio",
    "fire": "fuego", "fuego": "fuego",
    "force": "fuerza_magica", "fuerza": "fuerza_magica", "fuerza_magica": "fuerza_magica",
    "lightning": "relampago", "relampago": "relampago",
    "necrotic": "necrotico", "necrotico": "necrotico",
    "piercing": "perforante", "perforante": "perforante",
    "poison": "veneno", "veneno": "veneno",
    "psychic": "psiquico", "psiquico": "psiquico",
    "radiant": "radiante", "radiante": "radiante",
    "slashing": "cortante", "cortante": "cortante",
    "thunder": "trueno", "trueno": "trueno",
}

COBERTURA = {"media": 2, "tres-cuartos": 5, "tres cuartos": 5}

# Las 15 condiciones del SRD 5.2.1 + Sorprendido (que en 2024 da desventaja en Iniciativa).
CONDICIONES_2024 = {
    "agarrado": {
        "nombre": "Agarrado",
        "en": "Grappled",
        "efecto": "Velocidad 0; desventaja al atacar a objetivos distintos de quien lo agarra.",
        "desventaja": ["ataques"],
        "velocidad_cero": True,
    },
    "apresado": {
        "nombre": "Apresado",
        "en": "Restrained",
        "efecto": "Velocidad 0; ataques con desventaja, ataques en contra con ventaja y desventaja en salvaciones de Destreza.",
        "desventaja": ["ataques", "salvacion:destreza"],
        "ventaja_contra": True,
        "velocidad_cero": True,
    },
    "asustado": {
        "nombre": "Asustado",
        "en": "Frightened",
        "efecto": "Desventaja en pruebas de característica y ataques mientras vea la fuente del miedo; no puede acercarse voluntariamente.",
        "desventaja": ["pruebas", "ataques"],
    },
    "aturdido": {
        "nombre": "Aturdido",
        "en": "Stunned",
        "efecto": "Incapacitado; falla automáticamente salvaciones de Fuerza y Destreza; ataques en contra tienen ventaja.",
        "ventaja_contra": True,
        "falla_salvacion_fue_des": True,
        "no_actua": True,
        "velocidad_cero": True,
    },
    "cegado": {
        "nombre": "Cegado",
        "en": "Blinded",
        "efecto": "Falla pruebas que requieran la vista; sus ataques tienen desventaja y los ataques en contra tienen ventaja.",
        "desventaja": ["ataques"],
        "ventaja_contra": True,
    },
    "derribado": {
        "nombre": "Derribado",
        "en": "Prone",
        "efecto": "Desventaja en ataques; ataques en contra tienen ventaja a 1,5 m (desventaja más lejos). Levantarse cuesta la mitad de la velocidad.",
        "desventaja": ["ataques"],
        "ventaja_contra": True,
    },
    "encantado": {
        "nombre": "Encantado",
        "en": "Charmed",
        "efecto": "No puede atacar a quien lo encantó; quien lo encantó tiene ventaja en pruebas sociales con él.",
    },
    "ensordecido": {
        "nombre": "Ensordecido",
        "en": "Deafened",
        "efecto": "No oye y falla automáticamente pruebas que requieran solo el oído.",
    },
    "envenenado": {
        "nombre": "Envenenado",
        "en": "Poisoned",
        "efecto": "Desventaja en ataques y pruebas de característica.",
        "desventaja": ["pruebas", "ataques"],
    },
    "agotamiento": {
        "nombre": "Agotamiento",
        "en": "Exhaustion",
        "efecto": "SRD 5.2.1: −2 × nivel a toda prueba d20 y −1,5 m × nivel a la velocidad. En nivel 6, muere.",
        "penalizador_por_nivel": 2,
        "niveles": 1,
    },
    "incapacitado": {
        "nombre": "Incapacitado",
        "en": "Incapacitated",
        "efecto": "No puede realizar acciones, acciones adicionales ni reacciones; pierde la concentración y tiene desventaja en Iniciativa.",
        "desventaja": ["iniciativa"],
        "no_actua": True,
    },
    "inconsciente": {
        "nombre": "Inconsciente",
        "en": "Unconscious",
        "efecto": "Incapacitado y derribado; velocidad 0; falla salvaciones de Fuerza y Destreza; ataques en contra tienen ventaja (crítico a 1,5 m).",
        "ventaja_contra": True,
        "falla_salvacion_fue_des": True,
        "no_actua": True,
        "velocidad_cero": True,
    },
    "invisible": {
        "nombre": "Invisible",
        "en": "Invisible",
        "efecto": "Ventaja en Iniciativa y en ataques; los ataques en su contra tienen desventaja mientras no lo vean.",
        "ventaja": ["iniciativa", "ataques"],
        "desventaja_contra": True,
    },
    "paralizado": {
        "nombre": "Paralizado",
        "en": "Paralyzed",
        "efecto": "Incapacitado; velocidad 0; falla automáticamente salvaciones de Fuerza y Destreza; ataques en contra tienen ventaja.",
        "ventaja_contra": True,
        "falla_salvacion_fue_des": True,
        "no_actua": True,
        "velocidad_cero": True,
    },
    "petrificado": {
        "nombre": "Petrificado",
        "en": "Petrified",
        "efecto": "Incapacitado; velocidad 0; falla salvaciones de Fuerza y Destreza; resistencia a todo daño; inmune a veneno y enfermedad.",
        "ventaja_contra": True,
        "falla_salvacion_fue_des": True,
        "no_actua": True,
        "velocidad_cero": True,
    },
    "sorprendido": {
        "nombre": "Sorprendido",
        "en": "Surprised",
        "efecto": "SRD 5.2.1: desventaja en la tirada de Iniciativa al empezar el combate.",
        "desventaja": ["iniciativa"],
    },
}

_ALIAS_CONDICION_EN = {norm(v["en"]): k for k, v in CONDICIONES_2024.items() if v.get("en")}
_NO_ACTUA = {"inconsciente", "incapacitado", "aturdido", "paralizado", "petrificado", "fuera de combate"}

# Dado de golpe, característica principal y salvaciones de cada clase (SRD 5.2.1).
CLASES_2024 = {
    "barbaro": ("d12", "fuerza", ("fuerza", "constitucion")),
    "bardo": ("d8", "carisma", ("destreza", "carisma")),
    "brujo": ("d8", "carisma", ("sabiduria", "carisma")),
    "clerigo": ("d8", "sabiduria", ("sabiduria", "carisma")),
    "druida": ("d8", "sabiduria", ("inteligencia", "sabiduria")),
    "explorador": ("d10", "destreza", ("fuerza", "destreza")),
    "guerrero": ("d10", "fuerza", ("fuerza", "constitucion")),
    "hechicero": ("d6", "carisma", ("constitucion", "carisma")),
    "mago": ("d6", "inteligencia", ("inteligencia", "sabiduria")),
    "monje": ("d8", "destreza", ("fuerza", "destreza")),
    "paladin": ("d10", "fuerza", ("sabiduria", "carisma")),
    "picaro": ("d8", "destreza", ("destreza", "inteligencia")),
}
_FORMAS_CLASE = {
    "barbaro": ("barbaro", "barbara", "barbarian"), "bardo": ("bardo", "barda", "bard"),
    "brujo": ("brujo", "bruja", "warlock"), "clerigo": ("clerigo", "cleriga", "cleric"),
    "druida": ("druida", "druid"), "explorador": ("explorador", "exploradora", "ranger", "montaraz"),
    "guerrero": ("guerrero", "guerrera", "fighter"), "hechicero": ("hechicero", "hechicera", "sorcerer"),
    "mago": ("mago", "maga", "wizard"), "monje": ("monje", "monja", "monk"),
    "paladin": ("paladin", "paladina"), "picaro": ("picaro", "picara", "rogue"),
}
_ARRAY_ESTANDAR = (15, 14, 13, 12, 10, 8)
_COLORES_PJ = ("#2a78d6", "#d97706", "#16a34a", "#9333ea", "#dc2626", "#0891b2")


_FANTASIA = re.compile(r"magi|fantas|reino|imperio|reliqui|gremio|dragon|mazmorra|cripta|elf|enan|caballer|medieval|espada|corsari|pirat|aethermark|contrato")
_FUTURO = re.compile(r"futur|espacial|nave estelar|ciber|cyber|galax|androide|planeta")

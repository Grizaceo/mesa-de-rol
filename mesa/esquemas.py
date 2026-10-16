"""Esquema de la partida: qué forma tiene partida.json y qué reglamento la interpreta.

Dos esquemas conviven:

- **legacy** (1, `d20-simple`): cuatro atributos-bono (−1 a +4). Lo usan las partidas
  creadas antes de los esquemas, como *Los Hermanos del Neva*.
- **2024** (2, `dnd-2024`): seis características con puntuación (1 a 30) y valores
  derivados (modificador y competencia). Es el esquema de las partidas nuevas; el
  motor de reglas que lo juega llega con el corte vertical de reglas 2024 (P2).

La partida declara su esquema con `schema_version`; sin el campo manda el `reglamento`,
y sin ninguno de los dos el archivo es legacy (no se toca: migrar es una decisión, no
un efecto de abrir). Los valores derivados se calculan desde la puntuación y el nivel,
nunca se guardan: una sola fuente de verdad.

El catálogo es solo presentación: el ID es la identidad, y los nombres y alias
(español/inglés) sirven para mostrar y para interpretar lo que teclea una persona.
"""

from __future__ import annotations

from .texto import norm

VERSION_LEGACY = 1
VERSION_2024 = 2

REGLAMENTO_LEGACY = "d20-simple"
REGLAMENTO_2024 = "dnd-2024"

ESQUEMAS = {
    VERSION_LEGACY: {"nombre": "legacy", "reglamento": REGLAMENTO_LEGACY},
    VERSION_2024: {"nombre": "2024", "reglamento": REGLAMENTO_2024},
}
_VERSIÓN_POR_REGLAMENTO = {d["reglamento"]: v for v, d in ESQUEMAS.items()}

# Catálogo 2024: el ID es la identidad; "es"/"en" solo se muestran.
ATRIBUTOS_2024 = (
    {"id": "fuerza", "es": "Fuerza", "en": "Strength"},
    {"id": "destreza", "es": "Destreza", "en": "Dexterity"},
    {"id": "constitucion", "es": "Constitución", "en": "Constitution"},
    {"id": "inteligencia", "es": "Inteligencia", "en": "Intelligence"},
    {"id": "sabiduria", "es": "Sabiduría", "en": "Wisdom"},
    {"id": "carisma", "es": "Carisma", "en": "Charisma"},
)
IDS_2024 = tuple(a["id"] for a in ATRIBUTOS_2024)
NOMBRES_2024 = {a["id"]: a["es"] for a in ATRIBUTOS_2024}
NOMBRES_EN_2024 = {a["id"]: a["en"] for a in ATRIBUTOS_2024}

NOMBRES_LEGACY = {"fuerza": "Fuerza", "agilidad": "Agilidad", "ingenio": "Ingenio", "corazon": "Corazón"}
_NOMBRES = {**NOMBRES_LEGACY, **NOMBRES_2024}

ALIASES_2024: dict[str, str] = {}
for _a in ATRIBUTOS_2024:
    for _texto in (_a["id"], _a["es"], _a["en"]):
        ALIASES_2024[norm(_texto)] = _a["id"]
ALIASES_2024.update({
    "fue": "fuerza", "fuer": "fuerza", "str": "fuerza",
    "des": "destreza", "dex": "destreza",
    "con": "constitucion",
    "int": "inteligencia",
    "sab": "sabiduria", "wis": "sabiduria",
    "car": "carisma", "cha": "carisma",
})

PUNTUACION_MINIMA = 1
PUNTUACION_MAXIMA = 30
NIVEL_MINIMO = 1
NIVEL_MAXIMO = 20


def version_de(datos: dict) -> int:
    """Esquema de la partida: el declarado, el del reglamento, o legacy si no dice nada."""
    declarada = datos.get("schema_version")
    if declarada is not None:
        try:
            declarada = int(declarada)
        except (TypeError, ValueError):
            raise ValueError(f"schema_version inválido: {datos.get('schema_version')!r}") from None
        if declarada not in ESQUEMAS:
            conocidos = ", ".join(map(str, sorted(ESQUEMAS)))
            raise ValueError(f"schema_version desconocido: {declarada} (conocidos: {conocidos})")
        return declarada
    return _VERSIÓN_POR_REGLAMENTO.get(datos.get("reglamento"), VERSION_LEGACY)


def modificador(puntuacion: int) -> int:
    """Modificador 2024 de una puntuación: (puntuación − 10) / 2, redondeando hacia abajo."""
    return (int(puntuacion) - 10) // 2


def competencia(nivel: int) -> int:
    """Bonificador de competencia por nivel: +2 en 1–4, +3 en 5–8, +4 en 9–12, +5 en 13–16, +6 en 17–20."""
    return 2 + (int(nivel) - 1) // 4


def resolver_atributo_2024(nombre: str) -> str | None:
    """Alias de entrada (español o inglés) → ID de característica; None si no es ninguna."""
    return ALIASES_2024.get(norm(nombre))


def nombre_atributo(clave: str) -> str:
    """Nombre para mostrar de un ID de atributo (legacy o 2024); el ID tal cual si no hay nombre."""
    return _NOMBRES.get(norm(clave), clave)


def validar(datos: dict, slug: str = "") -> None:
    """Comprueba la forma de la partida según su esquema; ValueError con motivo legible.

    Legacy se valida flojo a propósito: la partida histórica tiene que abrir tal como
    quedó. 2024 se valida estricto: las seis características, sus rangos y el nivel.
    """
    prefijo = f"{slug}: " if slug else ""
    if not isinstance(datos, dict):
        raise ValueError(f"{prefijo}la partida tiene que ser un objeto JSON")
    version = version_de(datos)
    reglamento = datos.get("reglamento")
    if reglamento is not None and reglamento not in _VERSIÓN_POR_REGLAMENTO:
        conocidos = ", ".join(sorted(_VERSIÓN_POR_REGLAMENTO))
        raise ValueError(f"{prefijo}reglamento desconocido: {reglamento!r} (conocidos: {conocidos})")
    esperada = _VERSIÓN_POR_REGLAMENTO.get(reglamento)
    if esperada is not None and esperada != version:
        raise ValueError(
            f"{prefijo}schema_version {version} no concuerda con el reglamento {reglamento!r} (sería {esperada})"
        )
    personajes = datos.get("personajes", [])
    if not isinstance(personajes, list):
        raise ValueError(f"{prefijo}«personajes» tiene que ser una lista")
    for posicion, p in enumerate(personajes, start=1):
        if not isinstance(p, dict) or not str(p.get("nombre") or "").strip():
            raise ValueError(f"{prefijo}el personaje {posicion} no tiene nombre")
        atributos = p.get("atributos")
        if atributos is not None and not isinstance(atributos, dict):
            raise ValueError(f"{prefijo}{p['nombre']}: «atributos» tiene que ser un objeto")
        if version == VERSION_2024:
            _validar_ficha_2024(p, f"{prefijo}{p['nombre']}")


def _validar_ficha_2024(p: dict, quien: str) -> None:
    nivel = p.get("nivel", NIVEL_MINIMO)
    if not isinstance(nivel, int) or isinstance(nivel, bool) or not NIVEL_MINIMO <= nivel <= NIVEL_MAXIMO:
        raise ValueError(f"{quien}: el nivel va de {NIVEL_MINIMO} a {NIVEL_MAXIMO} (dice {nivel!r})")
    atributos = p.get("atributos")
    if not isinstance(atributos, dict):
        raise ValueError(f"{quien}: faltan las seis características con su puntuación")
    faltan = [i for i in IDS_2024 if i not in atributos]
    if faltan:
        raise ValueError(f"{quien}: faltan características: {', '.join(faltan)}")
    sobran = [k for k in atributos if k not in IDS_2024]
    if sobran:
        raise ValueError(f"{quien}: características desconocidas: {', '.join(sobran)}")
    for clave in IDS_2024:
        valor = atributos[clave]
        if not isinstance(valor, int) or isinstance(valor, bool) or not PUNTUACION_MINIMA <= valor <= PUNTUACION_MAXIMA:
            raise ValueError(
                f"{quien}: {NOMBRES_2024[clave]} tiene que ser una puntuación entera "
                f"de {PUNTUACION_MINIMA} a {PUNTUACION_MAXIMA} (dice {valor!r})"
            )

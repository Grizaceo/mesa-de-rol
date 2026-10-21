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

import re

from . import dados, esquemas, fuentes
from .texto import con_signo, norm

# Las 18 habilidades del SRD 5.2.1 asociadas a su característica canónica 2024.
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


def condicion_de_catalogo(nombre: str) -> dict | None:
    clave = norm(nombre)
    clave = _ALIAS_CONDICION_EN.get(clave, clave)
    base = CONDICIONES_2024.get(clave)
    return dict(base) if base else None


def resolver_atributo(nombre: str) -> tuple[str, str | None]:
    """Resuelve una característica 2024 o una de las 18 habilidades del SRD 5.2.1."""
    clave = norm(nombre)
    if clave in _ATRIBUTOS_SOLO_LEGACY:
        sugerencia = _ATRIBUTOS_SOLO_LEGACY[clave]
        raise ValueError(
            f"{nombre!r} es un atributo de d20-simple; en D&D 2024 usa las 6 características "
            f"(p. ej. {sugerencia}) o una habilidad del SRD"
        )
    canon = esquemas.resolver_atributo_2024(clave)
    if canon is not None:
        return canon, None
    if clave in _HABILIDAD_POR_CLAVE:
        return _HABILIDAD_POR_CLAVE[clave]
    opciones = ", ".join(esquemas.NOMBRES_2024.values())
    raise ValueError(f"{nombre!r} no es característica 2024 ni habilidad conocida (características: {opciones})")


def mod_caracteristica(ficha: dict, attr: str) -> int:
    attrs = ficha.get("atributos") or {}
    if attr in attrs:
        return esquemas.modificador(int(attrs[attr]))
    return 0


def bono_competencia(ficha: dict) -> int:
    if "competencia_bono" in ficha:
        return int(ficha["competencia_bono"])
    return esquemas.competencia(int(ficha.get("nivel", 1)))


def _competencia_en_habilidad(ficha: dict, habilidad: str | None) -> tuple[int, str | None]:
    if not habilidad:
        return 0, None
    comp = ficha.get("competencias") or {}
    clave = norm(habilidad)
    hab_en = next((norm(en) for es, _, en in HABILIDADES_2024 if norm(es) == clave), "")
    claves_hab = {clave, hab_en} - {""}
    pericia = {norm(x) for x in (comp.get("pericia") or comp.get("expertise") or [])}
    habilidades = {norm(x) for x in (comp.get("habilidades") or [])}
    bono = bono_competencia(ficha)
    if claves_hab & pericia:
        return bono * 2, "Pericia"
    if claves_hab & habilidades:
        return bono, "Competencia"
    return 0, None


def _competencia_en_salvacion(ficha: dict, attr: str) -> tuple[int, str | None]:
    comp = ficha.get("competencias") or {}
    salvaciones = {esquemas.resolver_atributo_2024(str(x)) or norm(str(x)) for x in (comp.get("salvaciones") or [])}
    if attr in salvaciones:
        return bono_competencia(ficha), "Competencia (salvación)"
    return 0, None


def velocidad_efectiva(ficha: dict) -> float:
    base = float(ficha.get("velocidad", 9.0))
    niveles_agotamiento = 0
    for c in ficha.get("condiciones", []):
        cat = condicion_de_catalogo(c.get("nombre", "")) or c
        if cat.get("velocidad_cero"):
            return 0.0
        if norm(c.get("nombre", "")) in ("agotamiento", "exhaustion"):
            niveles_agotamiento += int(c.get("niveles", 1))
    if niveles_agotamiento >= 6:
        return 0.0
    return max(0.0, round(base - 1.5 * niveles_agotamiento, 2))


def _efectos_condiciones(ficha: dict, attr: str | None, clase_tirada: str) -> tuple[list[str], list[str], int, bool]:
    """Devuelve (ventajas, desventajas, penalizador_agotamiento, fallo_automatico).

    `clase_tirada` es `'prueba'`, `'salvacion'`, `'ataques'` o `'iniciativa'`.
    """
    ventajas: list[str] = []
    desventajas: list[str] = []
    penalizador = 0
    fallo_auto = False

    ambitos = {clase_tirada}
    if attr:
        ambitos.add(attr)
        if clase_tirada == "salvacion":
            ambitos.add(f"salvacion:{attr}")
        elif clase_tirada == "prueba":
            ambitos.add("pruebas")

    for c in ficha.get("condiciones", []):
        cat = condicion_de_catalogo(c.get("nombre", "")) or {}
        combinada = {**cat, **c}
        if clase_tirada == "salvacion" and attr in ("fuerza", "destreza") and combinada.get("falla_salvacion_fue_des"):
            fallo_auto = True
        afectados = {norm(a) for a in combinada.get("desventaja", [])}
        if "todo" in afectados or (ambitos & afectados):
            desventajas.append(combinada["nombre"])
        favorecidos = {norm(a) for a in combinada.get("ventaja", [])}
        if "todo" in favorecidos or (ambitos & favorecidos):
            ventajas.append(combinada["nombre"])
        if combinada.get("penalizador_por_nivel"):
            penalizador -= int(combinada["penalizador_por_nivel"]) * int(combinada.get("niveles", 1))
    return ventajas, desventajas, penalizador, fallo_auto


def _motivos(declarada: bool | str, extra: list[str]) -> list[str]:
    motivos = list(extra)
    if declarada:
        motivos.insert(0, declarada if isinstance(declarada, str) else "declarada")
    return motivos


def prueba(
    partida: dict,
    ficha: dict,
    atributo: str,
    cd: int | None = None,
    ventaja: bool | str = False,
    desventaja: bool | str = False,
    bonos: list[tuple[int, str]] | None = None,
    oficio: bool = False,
    usar: str | None = None,
    etiqueta: str = "",
    salvacion: bool = False,
    buscar_habilidad_fn=None,
) -> dict:
    """Prueba de característica/habilidad o tirada de salvación en D&D 2024."""
    reglas_mesa = partida.get("reglas", {})
    attr, habilidad = resolver_atributo(atributo)
    if salvacion and habilidad:
        raise ValueError(f"las tiradas de salvación se hacen por característica, no con la habilidad {habilidad!r}")

    mod_attr = mod_caracteristica(ficha, attr)
    partes = [{"fuente": esquemas.NOMBRES_2024[attr], "valor": mod_attr}]

    if salvacion:
        val_comp, fuente_comp = _competencia_en_salvacion(ficha, attr)
    else:
        val_comp, fuente_comp = _competencia_en_habilidad(ficha, habilidad)
        if not val_comp and oficio:
            val_comp, fuente_comp = bono_competencia(ficha), "Competencia"
    if val_comp and fuente_comp:
        partes.append({"fuente": fuente_comp, "valor": val_comp})

    if usar and buscar_habilidad_fn is not None:
        hab = buscar_habilidad_fn(ficha, usar)
        if not hab.get("disponible", True):
            raise ValueError(f"«{hab['nombre']}» ya está gastada ({hab.get('recarga', 'sin recarga')})")
        if hab.get("bono"):
            partes.append({"fuente": hab["nombre"], "valor": int(hab["bono"])})
        hab["disponible"] = False

    for valor, fuente in bonos or []:
        partes.append({"fuente": fuente or "bono", "valor": valor})

    clase_tirada = "salvacion" if salvacion else "prueba"
    v_cond, d_cond, penalizador, fallo_auto = _efectos_condiciones(ficha, attr, clase_tirada)
    if penalizador:
        partes.append({"fuente": "Agotamiento", "valor": penalizador})
    ventajas = _motivos(ventaja, v_cond)
    desventajas = _motivos(desventaja, d_cond)
    modo = dados.resolver_modo(ventajas, desventajas)
    modificador = sum(p["valor"] for p in partes)
    # En SRD 5.2.1 solo las tiradas de ataque tienen éxito/fallo automático con 20/1 natural,
    # salvo que la mesa haya activado `reglas.naturales = true`.
    naturales = bool(reglas_mesa.get("naturales", False))
    r = dados.prueba_d20(modificador, cd, modo, naturales=naturales)
    if fallo_auto:
        r["exito"] = False
        r["resultado"] = "fallo_automatico"

    return {
        "tipo": "prueba",
        "reglamento": esquemas.REGLAMENTO_2024,
        "salvacion": salvacion,
        "quien": ficha["nombre"],
        "atributo": attr,
        "habilidad": habilidad,
        "etiqueta": etiqueta,
        "partes": partes,
        "ventajas": ventajas,
        "desventajas": desventajas,
        "habilidad_usada": usar,
        **r,
    }


def _normalizar_tipo_dano(tipo: str | None) -> str | None:
    if not tipo:
        return None
    clave = norm(tipo)
    return _TIPOS_DANO_ALIAS.get(clave, clave)


def _ajustar_por_resistencias(bruto: int, objetivo: dict, tipo_dano: str | None) -> tuple[int, str | None]:
    """Orden SRD 5.2.1: inmunidad (0) → resistencia (÷2 hacia abajo) → vulnerabilidad (×2)."""
    total = max(0, int(bruto))
    canon = _normalizar_tipo_dano(tipo_dano)
    if not canon:
        return total, None
    inm = {_normalizar_tipo_dano(x) for x in (objetivo.get("inmunidades") or [])}
    res = {_normalizar_tipo_dano(x) for x in (objetivo.get("resistencias") or [])}
    vul = {_normalizar_tipo_dano(x) for x in (objetivo.get("vulnerabilidades") or [])}
    efectos = []
    if canon in inm or "todo" in inm:
        return 0, "inmune"
    if canon in res or "todo" in res:
        total = total // 2
        efectos.append("resistente (÷2)")
    if canon in vul:
        total = total * 2
        efectos.append("vulnerable (×2)")
    return total, ", ".join(efectos) if efectos else None


def fijar_vida_temporal(ficha: dict, cantidad: int) -> dict:
    """Fija PG temporales siguiendo el SRD 5.2.1: no se acumulan, prevalece el mayor."""
    if cantidad < 0:
        raise ValueError("los PG temporales no pueden ser negativos")
    antes = int(ficha.get("vida_temporal", 0))
    ficha["vida_temporal"] = max(antes, int(cantidad))
    return {"antes": antes, "despues": ficha["vida_temporal"]}


def aplicar_vida(ficha: dict, delta: int, partida: dict | None = None) -> dict:
    """Aplica daño o curación según SRD 5.2.1 (PG temporales, 0 PG, daño masivo e inconsciencia)."""
    maximo = int(ficha.get("vida_max", ficha.get("vida", 0)))
    antes = int(ficha.get("vida", 0))
    temp_antes = int(ficha.get("vida_temporal", 0))
    absorbido_temp = 0
    muerte_instantanea = False

    if delta > 0 and ficha.get("muerto"):
        raise ValueError(
            f"{ficha['nombre']} ha muerto: curarlo no lo devuelve (si un conjuro lo revive, `vida \"{ficha['nombre']}\" +N --revivir`)"
        )
    if delta < 0:
        dano_recibido = -delta
        if temp_antes > 0:
            absorbido_temp = min(temp_antes, dano_recibido)
            ficha["vida_temporal"] = temp_antes - absorbido_temp
            dano_recibido -= absorbido_temp
        if antes == 0 and dano_recibido > 0 and not ficha.get("muerto"):
            if dano_recibido >= maximo:
                muerte_instantanea = True
                ficha["muerto"] = True
            else:
                sm = ficha.setdefault("salvaciones_muerte", {"exitos": 0, "fallos": 0, "estable": False})
                sm["estable"] = False
                sm["fallos"] = min(3, int(sm.get("fallos", 0)) + 1)
                if sm["fallos"] >= 3:
                    ficha["muerto"] = True
        else:
            sobrante = max(0, dano_recibido - antes)
            ficha["vida"] = max(0, antes - dano_recibido)
            if ficha["vida"] == 0 and sobrante >= maximo and maximo > 0:
                muerte_instantanea = True
                ficha["muerto"] = True
    elif delta > 0:
        ficha["vida"] = min(maximo, antes + delta)
        if ficha["vida"] > 0:
            ficha.pop("salvaciones_muerte", None)

    lista_cond = ficha.setdefault("condiciones", [])
    nombres = {norm(c["nombre"]) for c in lista_cond}
    if ficha["vida"] == 0:
        if "inconsciente" not in nombres and "fuera de combate" not in nombres:
            lista_cond.append(condicion_de_catalogo("inconsciente"))
        if not ficha.get("muerto") and "salvaciones_muerte" not in ficha:
            ficha["salvaciones_muerte"] = {"exitos": 0, "fallos": 0, "estable": False}
    elif ficha["vida"] > 0:
        ficha["condiciones"] = [
            c for c in lista_cond if norm(c["nombre"]) not in ("inconsciente", "fuera de combate")
        ]

    return {
        "antes": antes,
        "despues": ficha["vida"],
        "maximo": maximo,
        "temporal_antes": temp_antes,
        "temporal_despues": int(ficha.get("vida_temporal", 0)),
        "absorbido_temporal": absorbido_temp,
        "muerte_instantanea": muerte_instantanea,
    }


def salvacion_muerte(partida: dict, ficha: dict) -> dict:
    """Tirada de salvación de muerte SRD 5.2.1: 1 = 2 fallos, 20 = recupera 1 PG, >=10 = 1 éxito."""
    if int(ficha.get("vida", 0)) > 0:
        raise ValueError(f"{ficha['nombre']} no está en 0 PG: no hace salvaciones de muerte")
    if ficha.get("muerto"):
        raise ValueError(f"{ficha['nombre']} ya ha muerto")
    sm = ficha.setdefault("salvaciones_muerte", {"exitos": 0, "fallos": 0, "estable": False})
    if sm.get("estable"):
        raise ValueError(f"{ficha['nombre']} está estable: no tira salvaciones de muerte hasta que vuelva a recibir daño")
    valor = dados.tirar_dado(20)
    revive = False
    if valor == 20:
        aplicar_vida(ficha, 1, partida=partida)
        revive = True
        exitos, fallos, estable = 0, 0, False
    elif valor == 1:
        sm["fallos"] = min(3, int(sm.get("fallos", 0)) + 2)
        exitos, fallos, estable = int(sm.get("exitos", 0)), sm["fallos"], False
    elif valor >= 10:
        sm["exitos"] = min(3, int(sm.get("exitos", 0)) + 1)
        if sm["exitos"] >= 3:
            sm["estable"] = True
            sm["exitos"] = 0
            sm["fallos"] = 0
        exitos, fallos, estable = sm["exitos"], int(sm.get("fallos", 0)), bool(sm.get("estable"))
    else:
        sm["fallos"] = min(3, int(sm.get("fallos", 0)) + 1)
        exitos, fallos, estable = int(sm.get("exitos", 0)), sm["fallos"], False

    if fallos >= 3:
        ficha["muerto"] = True

    return {
        "tipo": "salvacion_muerte",
        "quien": ficha["nombre"],
        "valor": valor,
        "exitos": exitos,
        "fallos": fallos,
        "estable": estable,
        "revive": revive,
        "muerto": bool(ficha.get("muerto", False)),
    }


def dano(
    partida: dict,
    expr: str,
    objetivo: dict | None = None,
    critico: bool = False,
    *,
    bonus_mod: int = 0,
    fuente_mod: str | None = None,
    tipo_dano: str | None = None,
) -> dict:
    """Tira daño en D&D 2024: suma modificador (sin duplicar en crítico) y aplica resistencias/inmunidades."""
    tirada = dados.tirar(expr, critico=critico)
    bruto = max(0, tirada["total"] + int(bonus_mod))
    resultado: dict = {
        "tirada": tirada,
        "bonus_mod": int(bonus_mod),
        "fuente_mod": fuente_mod,
        "tipo_dano": _normalizar_tipo_dano(tipo_dano),
        "bruto": bruto,
    }
    if objetivo is not None:
        final, ajuste = _ajustar_por_resistencias(bruto, objetivo, tipo_dano)
        cambio_vida = aplicar_vida(objetivo, -final, partida=partida)
        resultado.update({
            "objetivo": objetivo["nombre"],
            "proteccion": 0,
            "ajuste_resistencia": ajuste,
            "final": final,
            "vida": cambio_vida,
        })
        if objetivo.get("concentracion") and final > 0:
            cd_conc = min(30, max(10, final // 2))
            resultado["concentracion_cd"] = cd_conc
    return resultado


def caracteristica_de_arma(atacante: dict, arma: dict) -> str:
    """Con qué característica ataca (y suma al daño) un arma: Sutil elige la mejor; a distancia, Destreza."""
    return _elegir_caracteristica_arma(atacante, arma, None)


def _elegir_caracteristica_arma(atacante: dict, arma: dict, atributo_forzado: str | None) -> str:
    if atributo_forzado:
        return resolver_atributo(atributo_forzado)[0]
    props = {norm(p) for p in (arma.get("propiedades") or [])}
    if {"sutil", "finesse"} & props:
        return "destreza" if mod_caracteristica(atacante, "destreza") >= mod_caracteristica(atacante, "fuerza") else "fuerza"
    if arma.get("distancia"):
        return "destreza"
    return "fuerza"


def ataque(
    partida: dict,
    atacante: dict,
    objetivo: dict,
    arma: str | None = None,
    ventaja: bool | str = False,
    desventaja: bool | str = False,
    bonos: list[tuple[int, str]] | None = None,
    oficio: bool = False,
    cobertura: str | None = None,
    atributo: str | None = None,
    etiqueta: str = "",
    *,
    buscar_arma_fn,
) -> dict:
    """Ataque D&D 2024 contra la CA del objetivo, con propiedades y maestrías de arma."""
    if int(atacante.get("vida", 1)) <= 0:
        raise ValueError(f"{atacante['nombre']} está en 0 de vida: no puede atacar")
    impide = next((c["nombre"] for c in atacante.get("condiciones", []) if norm(c["nombre"]) in _NO_ACTUA), None)
    if impide:
        raise ValueError(f"{atacante['nombre']} no puede atacar: está {impide}")

    elegida = buscar_arma_fn(atacante, arma)
    tiene_ficha_completa = bool(atacante.get("atributos")) and ("ataque" not in atacante or bool(atacante.get("equipo")))
    mod_dano = 0
    fuente_dano = None
    attr = None

    if tiene_ficha_completa:
        attr = _elegir_caracteristica_arma(atacante, elegida, atributo)
        mod_attr = mod_caracteristica(atacante, attr)
        partes = [{"fuente": esquemas.NOMBRES_2024[attr], "valor": mod_attr}]
        if elegida.get("competente", True) or oficio:
            partes.append({"fuente": "Competencia", "valor": bono_competencia(atacante)})
        mod_dano = mod_attr
        fuente_dano = esquemas.NOMBRES_2024[attr]
    else:
        partes = [{"fuente": "Ataque", "valor": int(atacante.get("ataque", 0))}]

    for valor, fuente in bonos or []:
        partes.append({"fuente": fuente or "bono", "valor": valor})

    v_cond, d_cond, penalizador, _ = _efectos_condiciones(atacante, attr, "ataques")
    if penalizador:
        partes.append({"fuente": "Agotamiento", "valor": penalizador})
    ventajas = _motivos(ventaja, v_cond)
    for c in objetivo.get("condiciones", []):
        cat = condicion_de_catalogo(c.get("nombre", "")) or c
        if cat.get("ventaja_contra") or c.get("ventaja_contra"):
            ventajas.append(f"{c['nombre']} (objetivo)")
        if cat.get("desventaja_contra") or c.get("desventaja_contra"):
            desventajas_extra = f"{c['nombre']} (objetivo)"
            if desventajas_extra not in d_cond:
                d_cond.append(desventajas_extra)
    desventajas = _motivos(desventaja, d_cond)

    ca_base = int(objetivo.get("ca", objetivo.get("defensa", 10)))
    extra = COBERTURA.get(norm(cobertura or ""), 0)
    modo = dados.resolver_modo(ventajas, desventajas)
    naturales = bool(partida.get("reglas", {}).get("naturales", True))
    r = dados.prueba_d20(sum(p["valor"] for p in partes), ca_base + extra, modo, naturales=naturales)

    tipo_dano = elegida.get("tipo_dano") or atacante.get("tipo_dano")
    propiedades = list(elegida.get("propiedades") or [])
    maestria = norm(elegida.get("maestria") or "") or None

    evento: dict = {
        "tipo": "ataque",
        "reglamento": esquemas.REGLAMENTO_2024,
        "quien": atacante["nombre"],
        "objetivo": objetivo["nombre"],
        "arma": elegida["nombre"],
        "etiqueta": etiqueta,
        "partes": partes,
        "ventajas": ventajas,
        "desventajas": desventajas,
        "cobertura": extra,
        "propiedades": propiedades,
        "maestria": maestria,
        **r,
    }
    if r["exito"]:
        evento["dano"] = dano(
            partida,
            elegida["dano"],
            objetivo,
            critico=r["resultado"] == "critico",
            bonus_mod=mod_dano,
            fuente_mod=fuente_dano,
            tipo_dano=tipo_dano,
        )
    elif maestria in ("rozar", "graze") and mod_dano > 0:
        final_rozar, ajuste = _ajustar_por_resistencias(mod_dano, objetivo, tipo_dano)
        vida_rozar = aplicar_vida(objetivo, -final_rozar, partida=partida)
        evento["dano_maestria"] = {
            "maestria": "rozar",
            "bruto": mod_dano,
            "tipo_dano": _normalizar_tipo_dano(tipo_dano),
            "ajuste_resistencia": ajuste,
            "final": final_rozar,
            "objetivo": objetivo["nombre"],
            "vida": vida_rozar,
        }
    return evento


def tirar_iniciativa(
    partida: dict,
    quienes: list[dict] | None = None,
    ventaja: bool | str = False,
    desventaja: bool | str = False,
    fusionar: bool = False,
) -> list[dict]:
    """Tira iniciativa (1d20 + mod Destreza) para los combatientes en escena.

    La ventaja o desventaja declarada se suma a la de las condiciones (Sorprendido, Invisible...).
    Con `fusionar`, solo se tiran `quienes` y se colocan en el orden que ya había, sin borrar a los demás.
    """
    combatientes = quienes if quienes is not None else (
        list(partida.get("personajes", [])) + [e for e in partida.get("enemigos", []) if int(e.get("vida", 0)) > 0]
    )
    orden = []
    for c in combatientes:
        mod_des = mod_caracteristica(c, "destreza")
        v_cond, d_cond, penalizador, _ = _efectos_condiciones(c, "destreza", "iniciativa")
        ventajas, desventajas = _motivos(ventaja, v_cond), _motivos(desventaja, d_cond)
        modo = dados.resolver_modo(ventajas, desventajas)
        r = dados.prueba_d20(mod_des + penalizador, cd=None, modo=modo, naturales=False)
        orden.append({
            "quien": c["nombre"],
            "modificador": mod_des + penalizador,
            "modo": modo,
            "ventajas": ventajas,
            "desventajas": desventajas,
            "valores": r["valores"],
            "elegido": r["elegido"],
            "total": r["total"],
            "destreza": int((c.get("atributos") or {}).get("destreza", 10)),
        })
    if fusionar:
        tirados = {x["quien"] for x in orden}
        previos = (partida.get("combate") or {}).get("orden_iniciativa") or []
        orden = [x for x in previos if isinstance(x, dict) and x.get("quien") not in tirados] + orden
    orden.sort(key=lambda x: (x.get("total", 0), x.get("destreza", 10)), reverse=True)
    partida.setdefault("combate", {})["orden_iniciativa"] = orden
    return orden


def descanso(
    partida: dict,
    clase: str,
    quienes: list[dict] | None = None,
    dados_golpe: int = 0,
) -> list[str]:
    """Descanso corto o largo según SRD 5.2.1."""
    objetivos = quienes if quienes is not None else partida.get("personajes", [])
    recargas = {"descanso_corto", "corto", "descanso"} if clase == "corto" else {
        "descanso_corto", "corto", "descanso", "descanso_largo", "largo", "dia", "escena", "combate",
    }
    lineas = []
    for p in objetivos:
        # SRD 5.2.1: para empezar un descanso, corto o largo, hace falta al menos 1 PG.
        if p.get("muerto"):
            lineas.append(f"{p['nombre']}: ha muerto, el descanso no lo devuelve")
            continue
        if int(p.get("vida", 0)) < 1:
            lineas.append(f"{p['nombre']}: a 0 PG no puede empezar un descanso (hace falta al menos 1 PG)")
            continue
        cambios = []
        if clase == "corto" and dados_golpe > 0 and isinstance(p.get("dados_golpe"), dict):
            if int(p["dados_golpe"].get("actual", 0)) > 0:
                g = gastar_dados_golpe(partida, p, dados_golpe)
                cv = g["vida"]
                cambios.append(f"gasta {g['gastados']}{g['dado']} → vida {cv['antes']} → {cv['despues']}/{cv['maximo']}")
            else:
                cambios.append("sin Dados de Golpe que gastar")
        elif clase == "largo":
            cambio_vida = aplicar_vida(p, int(p.get("vida_max", 0)), partida=partida)
            if cambio_vida["despues"] != cambio_vida["antes"]:
                cambios.append(f"vida {cambio_vida['antes']} → {cambio_vida['despues']}/{cambio_vida['maximo']}")
            if p.get("vida_temporal"):
                p["vida_temporal"] = 0
                cambios.append("PG temporales a 0")
            if isinstance(p.get("dados_golpe"), dict):
                dg = p["dados_golpe"]
                dg["actual"] = int(dg.get("max", dg.get("actual", 0)))
                cambios.append(f"Dados de Golpe {dg['actual']}/{dg['max']}")
            for niv, slot in (p.get("espacios_conjuro") or {}).items():
                if isinstance(slot, dict) and "max" in slot:
                    slot["actual"] = int(slot["max"])
            if p.get("espacios_conjuro"):
                cambios.append("espacios de conjuro restaurados")
            for c in list(p.get("condiciones", [])):
                if norm(c.get("nombre", "")) in ("agotamiento", "exhaustion"):
                    c["niveles"] = int(c.get("niveles", 1)) - 1
                    if c["niveles"] <= 0:
                        p["condiciones"].remove(c)
                    cambios.append(f"agotamiento {c['niveles']}" if c["niveles"] > 0 else "sin agotamiento")
        for h in p.get("habilidades", []):
            if h.get("recarga") in recargas and h.get("disponible") is False:
                h["disponible"] = True
                cambios.append(f"«{h['nombre']}» disponible")
        lineas.append(f"{p['nombre']}: {', '.join(cambios) or 'nada que recuperar'}")
    return lineas


def _caras_dado_golpe(dg: dict) -> int:
    m = re.fullmatch(r"\s*(?:\d+)?[dD](\d+)\s*", str(dg.get("dado", "d8")))
    if not m:
        raise ValueError(f"Dado de Golpe ilegible: {dg.get('dado')!r} (usa d6, d8, d10 o d12)")
    return int(m.group(1))


def gastar_dados_golpe(partida: dict, ficha: dict, cantidad: int = 1) -> dict:
    """Gasta Dados de Golpe como en un descanso corto (SRD 5.2.1): dado + mod CON por dado, mínimo 1 PG."""
    dg = ficha.get("dados_golpe")
    if not isinstance(dg, dict):
        raise ValueError(f"{ficha['nombre']} no tiene Dados de Golpe en la ficha")
    if ficha.get("muerto"):
        raise ValueError(f"{ficha['nombre']} ha muerto")
    if int(ficha.get("vida", 0)) < 1:
        raise ValueError(f"{ficha['nombre']} está a 0 PG: para descansar y gastar Dados de Golpe hace falta al menos 1 PG")
    disponibles = int(dg.get("actual", 0))
    if disponibles <= 0:
        raise ValueError(f"{ficha['nombre']} no tiene Dados de Golpe (0/{dg.get('max', 0)}): se recuperan con un descanso largo")
    if int(ficha.get("vida", 0)) >= int(ficha.get("vida_max", 0)):
        raise ValueError(f"{ficha['nombre']} ya tiene la vida al máximo: no hace falta gastar Dados de Golpe")
    caras = _caras_dado_golpe(dg)
    a_gastar = min(disponibles, max(1, int(cantidad)))
    mod_con = mod_caracteristica(ficha, "constitucion")
    valores = [dados.tirar_dado(caras) for _ in range(a_gastar)]
    curado = sum(max(1, v + mod_con) for v in valores)
    dg["actual"] = disponibles - a_gastar
    return {
        "dado": f"d{caras}", "valores": valores, "mod_con": mod_con, "curado": curado,
        "gastados": a_gastar, "restantes": dg["actual"], "vida": aplicar_vida(ficha, curado, partida=partida),
    }


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


def monedas_de(ambientacion: dict) -> list[str]:
    """Las monedas que corren en la ambientación: oro, plata y cobre solo en fantasía; si no, las de su época."""
    if ambientacion.get("monedas"):
        return [str(m) for m in ambientacion["monedas"]][:4]
    texto = norm(" ".join([str(ambientacion.get("epoca") or ""), str(ambientacion.get("lugar") or ""), " ".join(ambientacion.get("tono") or [])]))
    if _FANTASIA.search(texto):
        return ["oro", "plata", "cobre"]
    if _FUTURO.search(texto):
        return ["creditos"]
    anio = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", texto)
    if "chile" in texto:
        return ["escudos"] if anio and 1960 <= int(anio.group(1)) <= 1975 else ["pesos"]
    return ["dinero"]


def clase_de(rol: str) -> str | None:
    palabras = set(re.findall(r"[a-z]+", norm(rol or "")))
    return next((clase for clase, formas in _FORMAS_CLASE.items() if palabras & set(formas)), None)


def ficha_inicial(nombre: str, rol: str, indice: int = 0, monedas: list[str] | None = None) -> dict:
    """Una ficha de nivel 1 para empezar: matriz estándar según la clase, PG = dado máximo + CON, sin armadura.

    Es un punto de partida honesto, no una ficha completa: el narrador la ajusta en la sesión cero.
    """
    clase = clase_de(rol)
    dado, principal, salvaciones = CLASES_2024.get(clase, ("d8", ("fuerza", "destreza", "inteligencia", "carisma")[indice % 4], ()))
    orden = [principal, "constitucion"] + [a for a in ("destreza", "sabiduria", "inteligencia", "carisma", "fuerza") if a not in (principal, "constitucion")]
    valores = dict(zip(orden, _ARRAY_ESTANDAR))
    atributos = {a: valores[a] for a in esquemas.IDS_2024}
    ficha = {"atributos": atributos}
    vida = int(dado.lstrip("d")) + mod_caracteristica(ficha, "constitucion")
    ca = 10 + mod_caracteristica(ficha, "destreza")
    monedas = monedas or ["oro", "plata", "cobre"]
    fantasia = monedas == ["oro", "plata", "cobre"]  # fuera de la fantasía, nada de espadas ni dagas
    if principal == "fuerza":
        arma = ({"nombre": "Arma principal", "dano": "1d8", "tipo_dano": "cortante", "competente": True} if fantasia
                else {"nombre": "Barra de hierro", "dano": "1d6", "tipo_dano": "contundente", "competente": True})
    else:
        arma = {"nombre": "Daga" if fantasia else "Navaja", "dano": "1d4", "tipo_dano": "perforante", "propiedades": ["sutil", "ligera"], "competente": True}
    return {
        "id": re.sub(r"[^a-z0-9]+", "-", norm(nombre)).strip("-") or f"pj{indice + 1}",
        "nombre": nombre, "rol": rol, "nivel": 1, "vida": vida, "vida_max": vida, "ca": ca, "defensa": ca,
        "proteccion": 0, "velocidad": 9.0, "color": _COLORES_PJ[indice % len(_COLORES_PJ)], "atributos": atributos,
        "dados_golpe": {"dado": dado, "actual": 1, "max": 1},
        "competencias": {"salvaciones": list(salvaciones), "habilidades": []},
        "aspecto": "", "personalidad": "", "bueno_para": rol, "rasgos": [], "habilidades": [], "equipo": [arma],
        "condiciones": [], "monedas": {m: 0 for m in monedas},
    }


def _buscar_conjuro_en_ficha_o_cache(lanzador: dict, nombre_o_clave: str) -> dict | None:
    clave = norm(nombre_o_clave)
    for c in lanzador.get("conjuros", []):
        if clave in {norm(c.get("nombre", "")), norm(c.get("key", ""))}:
            return dict(c)
    try:
        entrada = fuentes.obtener("conjuro", nombre_o_clave)
        return dict(entrada["datos"])
    except (FileNotFoundError, ValueError):
        return None


def _expresion_escalada(conjuro_doc: dict, nivel_base: int, nivel_slot: int) -> str:
    expr = ""
    if isinstance(conjuro_doc.get("dano"), dict):
        expr = conjuro_doc["dano"].get("expresion") or ""
    elif isinstance(conjuro_doc.get("dano"), str):
        expr = conjuro_doc["dano"]
    for op in conjuro_doc.get("opciones_de_lanzamiento") or []:
        if op.get("type") == f"slot_level_{nivel_slot}" and op.get("damage_roll"):
            return str(op["damage_roll"])
    if nivel_slot > nivel_base and expr and "d" in expr and "+" not in expr:
        cant_txt, _, caras_txt = expr.partition("d")
        if cant_txt.isdigit() and caras_txt.isdigit():
            return f"{int(cant_txt) + (nivel_slot - nivel_base)}d{caras_txt}"
    return expr


def lanzar_conjuro(
    partida: dict,
    lanzador: dict,
    nombre_o_clave: str,
    *,
    nivel_slot: int | None = None,
    objetivos: list[dict] | None = None,
) -> dict:
    """Lanza un conjuro en D&D 2024 o devuelve `requiere_resolucion_manual` con su referencia."""
    conj = _buscar_conjuro_en_ficha_o_cache(lanzador, nombre_o_clave)
    if conj is None:
        return {
            "tipo": "conjuro",
            "quien": lanzador["nombre"],
            "conjuro": nombre_o_clave,
            "requiere_resolucion_manual": True,
            "referencia": f"Conjuro {nombre_o_clave!r} no está en la ficha ni en la caché local (`mesa fuentes buscar conjuro ...`).",
            "motivo": "sin_datos_locales",
        }

    nivel_base = int(conj.get("nivel", 0))
    slot_usado = nivel_base if nivel_slot is None else int(nivel_slot)
    if slot_usado < nivel_base:
        raise ValueError(f"«{conj.get('nombre')}» es de nivel {nivel_base}: no puede lanzarse en espacio de nivel {slot_usado}")

    if slot_usado >= 1:
        espacios = lanzador.get("espacios_conjuro") or {}
        slot = espacios.get(str(slot_usado))
        if not isinstance(slot, dict) or int(slot.get("actual", 0)) <= 0:
            raise ValueError(f"{lanzador['nombre']} no tiene espacios de conjuro de nivel {slot_usado} disponibles")
        slot["actual"] = int(slot["actual"]) - 1

    concentracion_anterior = None
    if conj.get("concentracion"):
        if lanzador.get("concentracion"):
            concentracion_anterior = lanzador["concentracion"].get("conjuro")
        lanzador["concentracion"] = {"conjuro": conj.get("nombre", nombre_o_clave), "nivel": slot_usado}

    attr_conj = resolver_atributo(lanzador.get("atributo_conjuro", "inteligencia"))[0]
    cd_conjuro = 8 + bono_competencia(lanzador) + mod_caracteristica(lanzador, attr_conj)

    expr_dano = _expresion_escalada(conj, nivel_base, slot_usado)
    if conj.get("automatizado") is False or not expr_dano or not conj.get("salvacion"):
        referencia = conj.get("referencia") or conj.get("key") or f"SRD 5.2.1 › Spells › {conj.get('nombre', nombre_o_clave)}"
        return {
            "tipo": "conjuro",
            "quien": lanzador["nombre"],
            "conjuro": conj.get("nombre", nombre_o_clave),
            "nivel_slot": slot_usado,
            "cd": cd_conjuro,
            "concentracion": bool(conj.get("concentracion")),
            "concentracion_reemplazada": concentracion_anterior,
            "requiere_resolucion_manual": True,
            "referencia": referencia,
            "motivo": "El conjuro no tiene resolución numérica automática completa; la mesa adjudica el efecto con su texto del SRD.",
        }

    attr_salv = resolver_atributo(str(conj["salvacion"]))[0]
    tipo_dano = None
    if isinstance(conj.get("dano"), dict):
        tipos = conj["dano"].get("tipos") or []
        tipo_dano = tipos[0] if tipos else None
    else:
        tipo_dano = conj.get("tipo_dano")

    tirada_base = dados.tirar(expr_dano, critico=False)
    bruto = tirada_base["total"]
    mitad_en_exito = bool(conj.get("mitad_en_exito", True))
    resultados_objetivos = []
    for obj in objetivos or []:
        salv = prueba(partida, obj, attr_salv, cd=cd_conjuro, salvacion=True)
        dano_inicial = (bruto // 2) if (salv["exito"] and mitad_en_exito) else (0 if salv["exito"] else bruto)
        dano_final, ajuste = _ajustar_por_resistencias(dano_inicial, obj, tipo_dano)
        cambio_vida = aplicar_vida(obj, -dano_final, partida=partida)
        resultados_objetivos.append({
            "objetivo": obj["nombre"],
            "salvacion": salv,
            "dano_bruto": bruto,
            "dano_final": dano_final,
            "ajuste_resistencia": ajuste,
            "vida": cambio_vida,
        })

    return {
        "tipo": "conjuro",
        "quien": lanzador["nombre"],
        "conjuro": conj.get("nombre", nombre_o_clave),
        "nivel_slot": slot_usado,
        "cd": cd_conjuro,
        "salvacion": attr_salv,
        "tirada_dano": tirada_base,
        "tipo_dano": _normalizar_tipo_dano(tipo_dano),
        "concentracion": bool(conj.get("concentracion")),
        "concentracion_reemplazada": concentracion_anterior,
        "requiere_resolucion_manual": False,
        "resultados_objetivos": resultados_objetivos,
    }


def usar_consumible(
    partida: dict,
    ficha: dict,
    nombre: str,
    *,
    objetivo: dict | None = None,
) -> dict:
    """Consume una unidad de un consumible de `equipo` y aplica su curación si es numérica.

    El nombre exacto manda; si no, un prefijo que señale a un solo objeto. Lo que no es consumible no se gasta.
    """
    clave = norm(nombre or "")
    if not clave:
        raise ValueError("falta el nombre del objeto que se usa")
    equipo = ficha.get("equipo", [])
    candidatos = [e for e in equipo if norm(e.get("nombre", "")) == clave] or [e for e in equipo if norm(e.get("nombre", "")).startswith(clave)]
    if len(candidatos) != 1:
        if candidatos:
            raise ValueError(f"{nombre!r} es ambiguo en el equipo de {ficha['nombre']}: {', '.join(e['nombre'] for e in candidatos)}")
        raise ValueError(f"{ficha['nombre']} no lleva {nombre!r} en su equipo")
    item = candidatos[0]
    if not item.get("consumible"):
        raise ValueError(f"«{item['nombre']}» no es un consumible: se equipa o se usa en una acción, no se gasta")
    cantidad = int(item.get("cantidad", 1))
    if cantidad <= 0:
        raise ValueError(f"de «{item['nombre']}» ya no quedan unidades")
    item["cantidad"] = cantidad - 1
    receptor = objetivo or ficha
    efecto_txt = str(item.get("efecto") or "").strip()
    expr_curacion = efecto_txt.split()[0] if efecto_txt and ("pg" in norm(efecto_txt) or "vida" in norm(efecto_txt)) else ""
    curacion = None
    if expr_curacion:
        tirada = dados.tirar(expr_curacion, critico=False)
        vida = aplicar_vida(receptor, tirada["total"], partida=partida)
        curacion = {"tirada": tirada, "total": tirada["total"], "objetivo": receptor["nombre"], "vida": vida}
    return {
        "tipo": "consumible",
        "quien": ficha["nombre"],
        "objeto": item["nombre"],
        "restantes": item["cantidad"],
        "objetivo": receptor["nombre"],
        "curacion": curacion,
    }


def adjudicar(
    partida: dict,
    *,
    regla: str,
    decision: str,
    autor: str,
    motivo: str = "",
    efectos: list[str] | None = None,
) -> dict:
    """Registra una adjudicación manual de la mesa cuando una regla devuelve `requiere_resolucion_manual`."""
    if not regla.strip() or not decision.strip() or not autor.strip():
        raise ValueError("la adjudicación manual exige regla, decisión y autor")
    return {
        "tipo": "adjudicacion",
        "reglamento": esquemas.version_de(partida) == esquemas.VERSION_2024 and esquemas.REGLAMENTO_2024 or esquemas.REGLAMENTO_LEGACY,
        "regla": regla.strip(),
        "decision": decision.strip(),
        "autor": autor.strip(),
        "motivo": motivo.strip(),
        "efectos": list(efectos or []),
    }

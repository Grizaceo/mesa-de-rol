"""Ficha 2024: características, vida, descansos y personaje inicial."""

from __future__ import annotations

import re

from .. import dados, esquemas
from ..texto import norm
from .catalogo import (
    CLASES_2024, CONDICIONES_2024, HABILIDADES_2024, _ALIAS_CONDICION_EN,
    _ARRAY_ESTANDAR, _ATRIBUTOS_SOLO_LEGACY, _COLORES_PJ, _FANTASIA, _FORMAS_CLASE,
    _FUTURO, _HABILIDAD_POR_CLAVE, _NO_ACTUA, _TIPOS_DANO_ALIAS,
)

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

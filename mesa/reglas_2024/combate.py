"""Pruebas, ataques e iniciativa del motor D&D 2024."""

from __future__ import annotations

from .. import dados, esquemas
from ..texto import norm
from .catalogo import COBERTURA, _NO_ACTUA
from .personaje import (
    _ajustar_por_resistencias, _competencia_en_habilidad, _competencia_en_salvacion,
    _efectos_condiciones, _motivos, _normalizar_tipo_dano, aplicar_vida,
    bono_competencia, condicion_de_catalogo, dano, mod_caracteristica, resolver_atributo,
)

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

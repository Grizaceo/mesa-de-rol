"""Conjuros, consumibles y adjudicación manual del motor D&D 2024."""

from __future__ import annotations

from .. import dados, esquemas, fuentes
from ..texto import norm


def _motor():
    from .combate import prueba
    from .personaje import (
        _ajustar_por_resistencias, _normalizar_tipo_dano, aplicar_vida, bono_competencia,
        mod_caracteristica, resolver_atributo,
    )
    return resolver_atributo, bono_competencia, mod_caracteristica, prueba, _ajustar_por_resistencias, aplicar_vida, _normalizar_tipo_dano

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
    resolver_atributo, bono_competencia, mod_caracteristica, prueba, _ajustar_por_resistencias, aplicar_vida, _normalizar_tipo_dano = _motor()
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
    from . import aplicar_vida
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

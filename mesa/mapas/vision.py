"""Línea de visión y cobertura entre casillas (SRD 5.2.1)."""

from __future__ import annotations

import math

from .base import BONO_COBERTURA, COBERTURAS, coordenada, distancia_casillas, nombre_celda, validar_celda
from .terreno import _semanticas
from .tokens import fichas

def _grado_cobertura(a: str, b: str) -> str:
    """El SRD 5.2.1 no suma coberturas: prevalece solo el grado más protector."""
    return a if COBERTURAS.index(a) >= COBERTURAS.index(b) else b


def linea_entre(mapa: dict, origen: str, destino: str, datos: dict | None = None,
                semanticas: dict[str, dict] | None = None) -> dict:
    """Traza la línea entre dos casillas y calcula visión y cobertura según el SRD 5.2.1.

    `semanticas` es la tabla de `_semanticas`: quien traza muchas líneas sobre el
    mismo mapa (una plantilla de área, toda la iluminación) la calcula una vez y
    la pasa aquí, en vez de re-inferir el terreno en cada casilla candidata.
    """
    c_orig = validar_celda(mapa, origen)
    c_dest = validar_celda(mapa, destino)
    (c1, f1), (c2, f2) = coordenada(c_orig), coordenada(c_dest)
    filas = mapa["filas"]
    sem_tabla = semanticas if semanticas is not None else _semanticas(mapa)
    ocupantes = {}
    for f in fichas(datos or {}):
        ocupantes.setdefault(f["celda"], []).append(f["quien"])
    if (c1, f1) == (c2, f2):
        return {
            "origen": c_orig, "destino": c_dest, "distancia_casillas": 0,
            "distancia_m": 0.0, "visible": True, "cobertura": "ninguna",
            "bono_cobertura": 0, "obstaculos": [], "casillas": [c_orig],
        }
    dx, dy = c2 - c1, f2 - f1
    largo = math.hypot(dx, dy)
    ux, uy = dx / largo, dy / largo
    min_c, max_c = min(c1, c2), max(c1, c2)
    min_f, max_f = min(f1, f2), max(f1, f2)
    candidatas = []
    for f in range(min_f, max_f + 1):
        for c in range(min_c, max_c + 1):
            if (c, f) in ((c1, f1), (c2, f2)):
                continue
            rx, ry = c - c1, f - f1
            proj = rx * ux + ry * uy
            if proj <= 1e-7 or proj >= largo - 1e-7:
                continue
            perp = abs(-rx * uy + ry * ux)
            if perp <= 0.72:
                candidatas.append((proj, perp, c, f))
    candidatas.sort(key=lambda x: (round(x[0], 3), x[1]))

    visible = True
    cobertura = "ninguna"
    obstaculos: list[dict] = []
    casillas_linea: list[str] = [c_orig]
    usadas: set[tuple[int, int]] = set()

    for i, (proj, perp, c, f) in enumerate(candidatas):
        if (c, f) in usadas:
            continue
        ch = filas[f][c]
        sem = sem_tabla[ch]
        celda = nombre_celda(c, f)
        significado = (mapa.get("leyenda") or {}).get(ch, ch)
        pareja = next(
            (x for x in candidatas[i + 1:] if abs(x[0] - proj) < 0.05 and x[2:4] != (c, f)),
            None,
        )
        if perp < 0.35 and pareja is None:
            casillas_linea.append(celda)
            cob_celda = sem["cobertura"]
            if sem["bloquea_vision"]:
                visible = False
                cob_celda = "total"
            if cob_celda != "ninguna":
                cobertura = _grado_cobertura(cobertura, cob_celda)
                obstaculos.append({"celda": celda, "caracter": ch, "significado": significado, "efecto": cob_celda})
            if celda in ocupantes:
                cobertura = _grado_cobertura(cobertura, "media")
                obstaculos.append({
                    "celda": celda, "caracter": "@",
                    "significado": ", ".join(ocupantes[celda]), "efecto": "media",
                })
        elif pareja is not None:
            _, _, c_b, f_b = pareja
            usadas.add((c_b, f_b))
            ch_b = filas[f_b][c_b]
            sem_b = sem_tabla[ch_b]
            celda_b = nombre_celda(c_b, f_b)
            sig_b = (mapa.get("leyenda") or {}).get(ch_b, ch_b)
            casillas_linea.append(celda if not sem["bloquea_vision"] else celda_b)
            bloq_a = sem["bloquea_vision"] or sem["cobertura"] == "total"
            bloq_b = sem_b["bloquea_vision"] or sem_b["cobertura"] == "total"
            if bloq_a and bloq_b:
                visible = False
                cobertura = "total"
                obstaculos.append({"celda": f"{celda}/{celda_b}", "caracter": ch, "significado": significado, "efecto": "total"})
            elif bloq_a or bloq_b:
                c_muro, ch_muro, sig_muro = (celda, ch, significado) if bloq_a else (celda_b, ch_b, sig_b)
                efecto = "tres-cuartos" if perp < 0.5 else "media"
                cobertura = _grado_cobertura(cobertura, efecto)
                obstaculos.append({"celda": c_muro, "caracter": ch_muro, "significado": f"esquina de {sig_muro}", "efecto": efecto})
            else:
                for cel_x, ch_x, sig_x, sem_x in ((celda, ch, significado, sem), (celda_b, ch_b, sig_b, sem_b)):
                    if sem_x["cobertura"] != "ninguna" and perp < 0.5:
                        cobertura = _grado_cobertura(cobertura, sem_x["cobertura"])
                        obstaculos.append({"celda": cel_x, "caracter": ch_x, "significado": sig_x, "efecto": sem_x["cobertura"]})

    casillas_linea.append(c_dest)
    if not visible:
        cobertura = "total"
    dist_c = distancia_casillas(c_orig, c_dest)
    return {
        "origen": c_orig,
        "destino": c_dest,
        "distancia_casillas": dist_c,
        "distancia_m": round(dist_c * mapa["celda"], 2),
        "visible": visible,
        "cobertura": cobertura,
        "bono_cobertura": BONO_COBERTURA[cobertura],
        "obstaculos": obstaculos,
        "casillas": casillas_linea,
    }

"""Movimiento (A*) y plantillas de área sobre la zona."""

from __future__ import annotations

import heapq
import math

from ..texto import norm
from .base import CELDA, FORMAS_AREA, RUMBOS, coordenada, metros, nombre_celda, validar_celda
from .luz import iluminacion_celda
from .terreno import _semanticas
from .tokens import fichas, resolver_punto
from .vision import linea_entre

def camino_movimiento(mapa: dict, origen: str, destino: str) -> dict:
    """Camino de menor coste de movimiento (A* en cuadrícula D&D; terreno difícil cuesta ×2)."""
    c_orig = validar_celda(mapa, origen)
    c_dest = validar_celda(mapa, destino)
    start = coordenada(c_orig)
    goal = coordenada(c_dest)
    celda_m = float(mapa.get("celda", CELDA))
    if start == goal:
        return {"alcanzable": True, "casillas_coste": 0, "metros_coste": 0.0, "camino": [c_orig], "dificiles": []}
    filas = mapa["filas"]
    alto, ancho = len(filas), len(filas[0])
    sem_cache = _semanticas(mapa)

    def pasable(col: int, fila: int) -> bool:
        if not (0 <= col < ancho and 0 <= fila < alto):
            return False
        ch = filas[fila][col]
        if ch == " ":
            return False
        if (col, fila) == goal:
            return not sem_cache[ch]["bloquea_paso"]
        return not sem_cache[ch]["bloquea_paso"]

    abiertos: list[tuple[float, int, tuple[int, int]]] = [(0.0, 0, start)]
    g_score: dict[tuple[int, int], float] = {start: 0.0}
    viene_de: dict[tuple[int, int], tuple[int, int]] = {}
    orden = 0

    while abiertos:
        _, _, actual = heapq.heappop(abiertos)
        if actual == goal:
            ruta_coords = [actual]
            while actual in viene_de:
                actual = viene_de[actual]
                ruta_coords.append(actual)
            ruta_coords.reverse()
            camino = [nombre_celda(c, f) for c, f in ruta_coords]
            dificiles = [nombre_celda(c, f) for c, f in ruta_coords[1:] if sem_cache[filas[f][c]]["dificil"]]
            coste_casillas = sum(2 if sem_cache[filas[f][c]]["dificil"] else 1 for c, f in ruta_coords[1:])
            return {
                "alcanzable": True,
                "casillas_coste": coste_casillas,
                "metros_coste": round(coste_casillas * celda_m, 2),
                "camino": camino,
                "dificiles": dificiles,
            }
        ac, af = actual
        for dc in (-1, 0, 1):
            for df in (-1, 0, 1):
                if dc == 0 and df == 0:
                    continue
                nc, nf = ac + dc, af + df
                if not pasable(nc, nf):
                    continue
                if dc != 0 and df != 0 and not pasable(ac + dc, af) and not pasable(ac, af + df):
                    continue
                ch_n = filas[nf][nc]
                paso = 2.0 if sem_cache[ch_n]["dificil"] else 1.0
                # Ligero desempate a favor de pasos ortogonales cuando el coste en casillas empata.
                extra = 0.001 if (dc != 0 and df != 0) else 0.0
                nuevo_g = g_score[actual] + paso + extra
                vecino = (nc, nf)
                if nuevo_g + 1e-9 < g_score.get(vecino, float("inf")):
                    g_score[vecino] = nuevo_g
                    viene_de[vecino] = actual
                    h = max(abs(goal[0] - nc), abs(goal[1] - nf))
                    orden += 1
                    heapq.heappush(abiertos, (nuevo_g + h, orden, vecino))

    return {"alcanzable": False, "casillas_coste": None, "metros_coste": None, "camino": [], "dificiles": []}


def _vector_hacia(datos: dict | None, mapa: dict, c_orig: str, hacia: str | None) -> tuple[float, float, str]:
    if not hacia:
        raise ValueError("esta plantilla requiere --hacia (un rumbo N/NE/E/SE/S/SO/O/NO o una casilla/ficha)")
    clave = norm(hacia)
    if clave in RUMBOS:
        dx, dy = RUMBOS[clave]
        largo = math.hypot(dx, dy)
        return dx / largo, dy / largo, clave.upper()
    c_dest, quien = resolver_punto(datos, mapa, hacia)
    if c_dest == c_orig:
        raise ValueError("--hacia debe ser distinto de la casilla de origen")
    (c1, f1), (c2, f2) = coordenada(c_orig), coordenada(c_dest)
    dx, dy = c2 - c1, f2 - f1
    largo = math.hypot(dx, dy)
    etiqueta = f"{c_dest} ({quien})" if quien else c_dest
    return dx / largo, dy / largo, etiqueta


def area_efecto(mapa: dict, forma: str, tamano: float, origen: str, hacia: str | None = None,
                ancho: float | None = None, datos: dict | None = None) -> dict:
    """Casillas y fichas dentro de una plantilla de área del SRD 5.2.1 (métrica de cuadrícula D&D)."""
    if not mapa or not mapa.get("filas"):
        raise ValueError("no hay mapa de zona activo")
    tipo = norm(forma or "")
    if tipo == "radio":
        tipo = "esfera"
    if tipo not in FORMAS_AREA:
        raise ValueError(f"forma de área desconocida {forma!r} (usa: {', '.join(FORMAS_AREA)})")
    tamano_m = float(tamano)
    if tamano_m <= 0:
        raise ValueError("el tamaño del área tiene que ser positivo (en metros)")
    celda_m = float(mapa.get("celda", CELDA))
    c_orig, quien_orig = resolver_punto(datos, mapa, origen)
    c0, f0 = coordenada(c_orig)
    n_celdas = max(1, round(tamano_m / celda_m))
    filas = mapa["filas"]
    alto_m, ancho_m_grid = len(filas), len(filas[0])

    ux = uy = 0.0
    rumbo_txt = None
    if tipo in ("cono", "linea") or (tipo == "cubo" and hacia):
        ux, uy, rumbo_txt = _vector_hacia(datos, mapa, c_orig, hacia)

    ancho_linea_m = float(ancho) if ancho is not None else celda_m
    if ancho_linea_m <= 0:
        raise ValueError("el ancho de la línea tiene que ser positivo")
    medio_ancho_celdas = max(0.45, (ancho_linea_m / celda_m) * 0.5)

    candidatas: list[str] = []
    bloqueadas: list[str] = []
    sem_tabla = _semanticas(mapa)
    for f in range(alto_m):
        for c in range(ancho_m_grid):
            ch = filas[f][c]
            if ch == " ":
                continue
            sem = sem_tabla[ch]
            if sem["bloquea_paso"] and sem["bloquea_vision"]:
                continue
            celda = nombre_celda(c, f)
            dx, dy = c - c0, f - f0
            dist_cheb = max(abs(dx), abs(dy))
            dentro = False
            if tipo in ("esfera", "emanacion", "cilindro"):
                dentro = dist_cheb <= n_celdas and (tipo != "emanacion" or (c, f) != (c0, f0))
            elif tipo == "cubo":
                p_min, p_max = -((n_celdas - 1) // 2), n_celdas // 2
                if not hacia:
                    dentro = p_min <= dx <= p_max and p_min <= dy <= p_max
                else:
                    proj = dx * ux + dy * uy
                    s_perp = -dx * uy + dy * ux
                    dentro = -0.25 <= proj <= n_celdas - 0.75 and p_min - 0.35 <= s_perp <= p_max + 0.35 and dist_cheb <= n_celdas
            elif tipo == "cono":
                if (c, f) != (c0, f0) and 1 <= dist_cheb <= n_celdas:
                    proj = dx * ux + dy * uy
                    perp = abs(-dx * uy + dy * ux)
                    dentro = proj > 0.1 and perp <= proj * 0.5 + 0.2
            elif tipo == "linea":
                if (c, f) != (c0, f0) and 1 <= dist_cheb <= n_celdas:
                    proj = dx * ux + dy * uy
                    perp = abs(-dx * uy + dy * ux)
                    dentro = 0.1 < proj <= n_celdas + 0.25 and perp <= medio_ancho_celdas
            if not dentro:
                continue
            if celda != c_orig and not linea_entre(mapa, c_orig, celda, datos, sem_tabla)["visible"]:
                bloqueadas.append(celda)
                continue
            candidatas.append(celda)

    afectados = [f["quien"] for f in fichas(datos or {}) if f["celda"] in candidatas]
    return {
        "forma": tipo,
        "tamano_m": tamano_m,
        "casillas_radio": n_celdas,
        "origen": c_orig,
        "quien_origen": quien_orig,
        "hacia": rumbo_txt,
        "casillas": candidatas,
        "bloqueadas": bloqueadas,
        "fichas": afectados,
    }


def consultar_linea(datos: dict, origen: str, destino: str) -> tuple[dict, str]:
    """Consulta táctica completa entre dos puntos (visión, cobertura, luz y camino más corto)."""
    mapa = (datos.get("escena") or {}).get("mapa")
    if not mapa or not mapa.get("filas"):
        raise ValueError("no hay mapa de zona activo")
    c_orig, q_orig = resolver_punto(datos, mapa, origen)
    c_dest, q_dest = resolver_punto(datos, mapa, destino)
    lin = linea_entre(mapa, c_orig, c_dest, datos=datos)
    cam = camino_movimiento(mapa, c_orig, c_dest)
    luz_dest = iluminacion_celda(mapa, c_dest)
    etiq_o = f"{c_orig} ({q_orig})" if q_orig else c_orig
    etiq_d = f"{c_dest} ({q_dest})" if q_dest else c_dest
    n_c = lin["distancia_casillas"]
    cabecera = f"Línea {etiq_o} → {etiq_d}: {n_c} {'casilla' if n_c == 1 else 'casillas'} ({metros(lin['distancia_m'])} en recta)"
    vis_txt = "clara" if lin["visible"] else "bloqueada (sin línea de visión)"
    cob = lin["cobertura"]
    bono = lin["bono_cobertura"]
    cob_txt = cob if bono in (None, 0) else f"{cob} (+{bono} Defensa/Destreza)"
    if lin["obstaculos"]:
        motivos = ", ".join(f"{o['celda']} ({o['significado']})" for o in lin["obstaculos"])
        cob_txt += f" por {motivos}"
    efecto_luz = {
        "brillante": "brillante (visión normal)",
        "penumbra": "penumbra (ligeramente oscurecida: desventaja en Percepción visual)",
        "oscuridad": "oscuridad (fuertemente oscurecida: Cegado al mirar allí)",
    }[luz_dest]
    if cam["alcanzable"]:
        pasos = " → ".join(cam["camino"])
        dif = f"; terreno difícil en {', '.join(cam['dificiles'])}" if cam["dificiles"] else ""
        cam_txt = f"Camino más corto: {cam['casillas_coste']} casillas ({metros(cam['metros_coste'])} de movimiento{dif}): {pasos}"
    else:
        cam_txt = "Camino más corto: inalcanzable a pie (paso bloqueado)"
    resultado = {**lin, "quien_origen": q_orig, "quien_destino": q_dest, "luz_destino": luz_dest, "camino": cam}
    texto = f"{cabecera}\nVisión: {vis_txt} · Cobertura: {cob_txt} · Luz en {c_dest}: {efecto_luz}\n{cam_txt}"
    return resultado, texto


def consultar_area(datos: dict, forma: str, tamano: float, origen: str,
                   hacia: str | None = None, ancho: float | None = None) -> tuple[dict, str]:
    """Calcula las casillas y fichas dentro de una plantilla de área y devuelve su resumen."""
    mapa = (datos.get("escena") or {}).get("mapa")
    res = area_efecto(mapa, forma, tamano, origen, hacia=hacia, ancho=ancho, datos=datos)
    etiq_o = f"{res['origen']} ({res['quien_origen']})" if res.get("quien_origen") else res["origen"]
    dir_txt = f" hacia {res['hacia']}" if res.get("hacia") else ""
    lineas = [
        f"Área: {res['forma']} de {metros(res['tamano_m'])} ({res['casillas_radio']} casillas) desde {etiq_o}{dir_txt}",
        f"Casillas afectadas ({len(res['casillas'])}): {', '.join(res['casillas']) or 'ninguna'}",
    ]
    if res["bloqueadas"]:
        lineas.append(f"En sombra por cobertura total ({len(res['bloqueadas'])}): {', '.join(res['bloqueadas'])}")
    lineas.append(f"Fichas dentro: {', '.join(res['fichas']) or 'ninguna'}")
    return res, "\n".join(lineas)

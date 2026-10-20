"""Generadores deterministas de zona.

Cada tipo (`mazmorra`, `taberna`, `calle`, `bosque`, `cueva`, `puente`)
sale de su semilla, así que el mismo número da el mismo mapa en cualquier
máquina. Lo que sale es un borrador: el narrador lo retoca con `mapa zona`,
`mapa terreno` y `mapa luz`.
"""

from __future__ import annotations

import math
import random
import re
from ..texto import norm

from .base import (
    ALIAS_TIPO_ZONA,
    COLUMNAS,
    DENSIDADES,
    MAX_FILAS,
    TIPOS_ZONA,
    _DIMENSIONES_BASE,
    _semilla_entera,
    nombre_celda,
)

from .zona import (
    nueva_zona,
    poner_luz,
)


def _gen_mazmorra(rng: random.Random, ancho: int, alto: int, factor: float) -> tuple[list[list[str]], dict[str, str], list[str]]:
    g = [["#"] * ancho for _ in range(alto)]
    ley = {"P": "pilar de piedra", "C": "cofre", "E": "escombros"}
    salas: list[tuple[int, int, int, int]] = []
    n_salas = max(2, min(5, round(3 * factor)))
    for _ in range(n_salas * 8):
        if len(salas) >= n_salas:
            break
        w = rng.randint(3, max(3, min(6, ancho // 2 - 1)))
        h = rng.randint(3, max(3, min(5, alto // 2 - 1)))
        x = rng.randint(1, max(1, ancho - w - 1))
        y = rng.randint(1, max(1, alto - h - 1))
        if any(not (x + w + 1 <= sx or sx + sw + 1 <= x or y + h + 1 <= sy or sy + sh + 1 <= y) for sx, sy, sw, sh in salas):
            continue
        salas.append((x, y, w, h))
        for fy in range(y, y + h):
            for cx in range(x, x + w):
                g[fy][cx] = "."
    if len(salas) < 2:
        w1, h1 = max(3, ancho // 3), max(3, alto - 4)
        salas = [(1, 2, w1, h1), (ancho - w1 - 1, 2, w1, h1)]
        for sx, sy, sw, sh in salas:
            for fy in range(sy, sy + sh):
                for cx in range(sx, sx + sw):
                    g[fy][cx] = "."
    salas.sort(key=lambda s: (s[0], s[1]))
    for (x1, y1, w1, h1), (x2, y2, w2, h2) in zip(salas, salas[1:]):
        cx1, cy1 = x1 + w1 // 2, y1 + h1 // 2
        cx2, cy2 = x2 + w2 // 2, y2 + h2 // 2
        paso_x = 1 if cx2 >= cx1 else -1
        for x in range(cx1, cx2 + paso_x, paso_x):
            g[cy1][x] = "."
        paso_y = 1 if cy2 >= cy1 else -1
        for y in range(cy1, cy2 + paso_y, paso_y):
            g[y][cx2] = "."
        if x1 + w1 < ancho - 1 and g[cy1][x1 + w1] == ".":
            g[cy1][x1 + w1] = "+"
    sx0, sy0, sw0, sh0 = salas[0]
    g[sy0 + sh0 // 2][sx0] = "^"
    sxu, syu, swu, shu = salas[-1]
    g[syu + shu // 2][sxu + swu - 1] = "C"
    for sx, sy, sw, sh in salas:
        if sw >= 4 and sh >= 4 and rng.random() < 0.7 * factor:
            g[sy + 1][sx + 1] = "P"
        if rng.random() < 0.6 * factor:
            rx, ry = sx + rng.randint(0, sw - 1), sy + rng.randint(0, sh - 1)
            if g[ry][rx] == ".":
                g[ry][rx] = "E"
    focos = [f"{nombre_celda(s[0] + s[2] // 2, s[1] + s[3] // 2)}:4.5:4.5:antorcha" for s in salas[:2]]
    return g, ley, focos


def _gen_taberna(rng: random.Random, ancho: int, alto: int, factor: float) -> tuple[list[list[str]], dict[str, str], list[str]]:
    g = [["."] * ancho for _ in range(alto)]
    for x in range(ancho):
        g[0][x] = g[alto - 1][x] = "#"
    for y in range(alto):
        g[y][0] = g[y][ancho - 1] = "#"
    g[alto - 1][ancho // 2] = "+"
    for x in range(2, ancho - 2, 4):
        g[0][x] = "="
        if x != ancho // 2:
            g[alto - 1][x] = "="
    # Trastienda al norte o al este si hay espacio
    y_muro = max(2, min(3, alto // 3))
    if alto >= 8:
        for x in range(1, ancho - 1):
            g[y_muro][x] = "#"
        g[y_muro][ancho - 3] = "+"
        g[1][2] = "b"
        g[1][ancho - 2] = "^"
    else:
        y_muro = 0
        g[1][ancho - 2] = "^"
    # Barra y chimenea
    y_barra = y_muro + 2 if y_muro else 2
    for x in range(2, max(4, ancho // 2)):
        if y_barra < alto - 2:
            g[y_barra][x] = "B"
    g[min(alto - 2, y_barra + 1)][1] = "F"
    # Mesas y barriles según densidad
    n_mesas = max(2, min(8, round((ancho * alto // 28) * factor)))
    for _ in range(n_mesas * 5):
        if sum(fila.count("T") for fila in g) >= n_mesas:
            break
        mx = rng.randint(2, ancho - 3)
        my = rng.randint(y_barra + 1, alto - 3)
        if g[my][mx] == ".":
            g[my][mx] = "T"
    if g[alto - 2][2] == ".":
        g[alto - 2][2] = "b"
    ley = {
        "B": "barra de madera [bloquea-paso, cobertura=media]",
        "T": "mesa",
        "b": "barril",
        "F": "chimenea encendida",
    }
    focos = [f"{nombre_celda(1, min(alto - 2, y_barra + 1))}:6:6:chimenea"]
    return g, ley, focos


def _gen_calle(rng: random.Random, ancho: int, alto: int, factor: float) -> tuple[list[list[str]], dict[str, str], list[str]]:
    g = [["."] * ancho for _ in range(alto)]
    h_edif = max(2, alto // 4)
    for y in range(h_edif):
        for x in range(ancho):
            if x not in (ancho // 2 - 1, ancho // 2):
                g[y][x] = "#" if y == h_edif - 1 or x in (0, ancho - 1, ancho // 2 - 2, ancho // 2 + 1) else "."
                g[alto - 1 - y][x] = "#" if y == h_edif - 1 or x in (0, ancho - 1, ancho // 2 - 2, ancho // 2 + 1) else "."
    if ancho >= 10:
        g[h_edif - 1][max(1, ancho // 4)] = "+"
        g[h_edif - 1][min(ancho - 2, 3 * ancho // 4)] = "="
        g[alto - h_edif][max(1, ancho // 4)] = "="
        g[alto - h_edif][min(ancho - 2, 3 * ancho // 4)] = "+"
    cx, cy = ancho // 2, alto // 2
    g[cy][cx] = "O"
    n_obst = max(2, round(4 * factor))
    for _ in range(n_obst * 4):
        if sum(f.count("C") + f.count("b") for f in g) >= n_obst:
            break
        ox = rng.randint(1, ancho - 2)
        oy = rng.randint(h_edif, alto - h_edif - 1)
        if g[oy][ox] == "." and (ox, oy) != (cx, cy):
            g[oy][ox] = "C" if rng.random() < 0.45 else "b"
    ley = {
        "O": "fuente de piedra [bloquea-paso, cobertura=tres-cuartos]",
        "C": "carro o puesto",
        "b": "barriles y cajas",
    }
    focos = [f"{nombre_celda(cx, cy)}:6:6:farol de la plaza"]
    return g, ley, focos


def _gen_bosque(rng: random.Random, ancho: int, alto: int, factor: float) -> tuple[list[list[str]], dict[str, str], list[str]]:
    g = [["."] * ancho for _ in range(alto)]
    cx, cy = ancho // 2, alto // 2
    # Arroyo opcional en un lateral
    x_rio = rng.randint(max(2, ancho - 4), ancho - 2)
    for y in range(alto):
        rx = max(1, min(ancho - 2, x_rio + rng.choice((-1, 0, 0, 1))))
        g[y][rx] = "~"
    for y in range(alto):
        for x in range(ancho):
            if g[y][x] != ".":
                continue
            dist_centro = math.hypot(x - cx, y - cy)
            borde = x in (0, ancho - 1) or y in (0, alto - 1)
            if abs(y - cy) <= 1 and x < cx + 2:
                continue  # sendero despejado hacia el claro
            p = (0.45 if borde else 0.18 if dist_centro > 2.6 else 0.05) * factor
            r = rng.random()
            if r < p * 0.55:
                g[y][x] = "A"
            elif r < p * 0.9:
                g[y][x] = "m"
            elif r < p:
                g[y][x] = "R"
    g[cy][cx] = "."
    ley = {
        "A": "árbol grueso [dificil, cobertura=tres-cuartos]",
        "m": "maleza y arbustos [dificil, cobertura=media]",
        "R": "roca musgosa [bloquea-paso, cobertura=tres-cuartos]",
    }
    return g, ley, []


def _gen_cueva(rng: random.Random, ancho: int, alto: int, factor: float) -> tuple[list[list[str]], dict[str, str], list[str]]:
    g = [["#"] * ancho for _ in range(alto)]
    cx, cy = ancho // 2, alto // 2
    for y in range(1, alto - 1):
        for x in range(1, ancho - 1):
            if math.hypot((x - cx) / max(1, ancho / 2), (y - cy) / max(1, alto / 2)) < 0.72 or rng.random() < 0.48:
                g[y][x] = "."
    for _ in range(2):
        nueva = [fila[:] for fila in g]
        for y in range(1, alto - 1):
            for x in range(1, ancho - 1):
                muros = sum(
                    1 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                    if (dx or dy) and g[y + dy][x + dx] == "#"
                )
                nueva[y][x] = "#" if muros >= 5 else "."
        g = nueva
    # Garantizar el centro y una entrada al sur abiertos y conectados
    for y in range(cy, alto):
        g[y][cx] = "."
    visitadas: set[tuple[int, int]] = set()
    cola = [(cx, cy)]
    while cola:
        vx, vy = cola.pop()
        if (vx, vy) in visitadas:
            continue
        visitadas.add((vx, vy))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = vx + dx, vy + dy
            if 0 <= nx < ancho and 0 <= ny < alto and g[ny][nx] == "." and (nx, ny) not in visitadas:
                cola.append((nx, ny))
    for y in range(1, alto - 1):
        for x in range(1, ancho - 1):
            if g[y][x] == "." and (x, y) not in visitadas:
                g[y][x] = "#"
    # Estalagmitas y charcas según densidad
    interiores = [(x, y) for (x, y) in sorted(visitadas) if 1 < y < alto - 2 and 1 < x < ancho - 2 and (x, y) != (cx, cy)]
    rng.shuffle(interiores)
    n_elem = max(2, min(len(interiores) // 3, round(4 * factor)))
    for i, (x, y) in enumerate(interiores[:n_elem]):
        g[y][x] = "E" if i % 2 == 0 else "~"
    ley = {"E": "estalagmita [dificil, cobertura=tres-cuartos]"}
    focos = [f"{nombre_celda(cx, alto - 1)}:4.5:4.5:entrada de la cueva"]
    return g, ley, focos


def _gen_puente(rng: random.Random, ancho: int, alto: int, factor: float) -> tuple[list[list[str]], dict[str, str], list[str]]:
    g = [["."] * ancho for _ in range(alto)]
    cx, cy = ancho // 2, alto // 2
    x_izq = max(2, cx - max(2, ancho // 6))
    x_der = min(ancho - 3, cx + max(2, ancho // 6))
    y_arr = max(1, cy - 2)
    y_aba = min(alto - 2, cy + 1)
    for y in range(alto):
        for x in range(x_izq, x_der + 1):
            if y < y_arr or y > y_aba:
                g[y][x] = "~"
            elif y in (y_arr, y_aba):
                g[y][x] = "="
            else:
                g[y][x] = "."
    if factor >= 1.0 and x_der > x_izq + 1:
        g[y_arr + 1][(x_izq + x_der) // 2] = "C"
    for _ in range(max(1, round(3 * factor))):
        bx = rng.choice([rng.randint(0, max(0, x_izq - 1)), rng.randint(min(ancho - 1, x_der + 1), ancho - 1)])
        by = rng.randint(0, alto - 1)
        if g[by][bx] == "." and not (y_arr <= by <= y_aba):
            g[by][bx] = "R" if rng.random() < 0.5 else "m"
    ley = {
        "=": "parapeto del puente [bloquea-paso, cobertura=media]",
        "C": "carro o puesto",
        "R": "roca en la orilla [bloquea-paso, cobertura=tres-cuartos]",
        "m": "maleza [dificil, cobertura=media]",
    }
    return g, ley, []


_GENERADORES_ZONA = {
    "mazmorra": _gen_mazmorra,
    "taberna": _gen_taberna,
    "calle": _gen_calle,
    "bosque": _gen_bosque,
    "cueva": _gen_cueva,
    "puente": _gen_puente,
}


def generar_zona(tipo: str, *, semilla: int | str | None = None, ancho: int | None = None,
                 alto: int | None = None, densidad: str | None = None, celda: float | None = None,
                 nombre: str | None = None, luz: str | None = None, anterior: dict | None = None) -> dict:
    """Genera un mapa de zona reproducible en texto con leyenda y semántica de terreno."""
    clave = ALIAS_TIPO_ZONA.get(norm(tipo or ""))
    if not clave:
        raise ValueError(f"tipo de zona desconocido {tipo!r} (usa: {', '.join(TIPOS_ZONA)})")
    dens = norm(densidad or "normal")
    if dens not in DENSIDADES:
        raise ValueError(f"densidad inválida {densidad!r} (usa: {', '.join(DENSIDADES)})")
    ancho_def, alto_def, luz_def, nombre_def = _DIMENSIONES_BASE[clave]
    w = int(ancho if ancho is not None else ancho_def)
    h = int(alto if alto is not None else alto_def)
    if not (5 <= w <= len(COLUMNAS)):
        raise ValueError(f"el ancho del mapa va de 5 a {len(COLUMNAS)} columnas (dice {w})")
    if not (5 <= h <= MAX_FILAS):
        raise ValueError(f"el alto del mapa va de 5 a {MAX_FILAS} filas (dice {h})")
    sem_num = _semilla_entera(semilla, f"{clave}:{w}x{h}:{dens}:{nombre or ''}")
    rng = random.Random(sem_num)
    factor = {"baja": 0.6, "normal": 1.0, "alta": 1.5}[dens]
    rejilla, ley_extra, focos = _GENERADORES_ZONA[clave](rng, w, h, factor)
    dibujo = "\n".join("".join(fila) for fila in rejilla)
    items_leyenda = [f"{k}={v}" for k, v in ley_extra.items()]
    mapa = nueva_zona(
        dibujo,
        leyenda=items_leyenda,
        celda=celda,
        nombre=nombre or (anterior or {}).get("nombre") or nombre_def,
        anterior=None,
        luz=luz or luz_def,
    )
    if focos:
        poner_luz(mapa, mapa.get("luz"), focos)
    mapa["generador"] = {"tipo": clave, "semilla": sem_num, "ancho": w, "alto": h, "densidad": dens}
    return mapa

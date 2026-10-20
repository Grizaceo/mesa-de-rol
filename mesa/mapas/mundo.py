"""El mapa del mundo: lugares, rutas, regiones y ríos.

Solo lo que los personajes conocen: lo demás sigue en `director.md`. Las
distancias y los tiempos de viaje salen de `srd-2024_exploration_travel`.
"""

from __future__ import annotations

import math
import random
import re
from ..texto import norm

from .base import (
    UNIDAD,
    _semilla_entera,
    cifra,
)


RITMOS_VIAJE = {
    "rapido": {"km_hora": 6.4, "km_dia": 48.0, "efecto": "desventaja en Percepción, Supervivencia y Sigilo"},
    "normal": {"km_hora": 4.8, "km_dia": 38.0, "efecto": "desventaja en Sigilo"},
    "lento": {"km_hora": 3.2, "km_dia": 29.0, "efecto": "ventaja en Percepción y Supervivencia"},
}


BIOMAS = ("bosque", "llanura", "montana", "pantano", "desierto", "costa", "agua", "urbano", "helado")


TIPOS_TRAZO = ("rio", "camino", "costa", "frontera", "canal", "sendero")


def _mundo(datos: dict) -> dict:
    m = datos.setdefault("mundo", {})
    m.setdefault("unidad", UNIDAD)
    m.setdefault("lugares", [])
    m.setdefault("rutas", [])
    return m


def _parsear_puntos(espec: str | list | None, minimo: int = 2) -> list[list[float]]:
    """Convierte «0,0 15,8 42,28» o [[0,0], ...] en lista de pares [x, y]."""
    if espec is None:
        raise ValueError("faltan los puntos (usa «x1,y1 x2,y2 ...»)")
    if isinstance(espec, str):
        tokens = [t.strip() for t in re.split(r"[\s;]+", espec.strip()) if t.strip()]
        crudos = []
        for t in tokens:
            partes = t.split(",")
            if len(partes) != 2:
                raise ValueError(f"punto inválido {t!r}: usa «x,y» separados por espacio, p. ej. «0,0 10,5»")
            crudos.append(partes)
    elif isinstance(espec, list):
        crudos = espec
    else:
        raise ValueError("formato de puntos inválido")
    puntos = []
    for p in crudos:
        if isinstance(p, str):
            partes = p.split(",")
            if len(partes) != 2:
                raise ValueError(f"punto inválido {p!r}: usa «x,y»")
            px, py = partes
        elif isinstance(p, (list, tuple)) and len(p) == 2:
            px, py = p
        else:
            raise ValueError(f"punto inválido {p!r}")
        puntos.append([_coordenada(px, "x"), _coordenada(py, "y")])
    if len(puntos) < minimo:
        raise ValueError(f"hacen falta al menos {minimo} puntos (hay {len(puntos)})")
    return puntos


def longitud_trazo(puntos: list[list[float]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(puntos, puntos[1:]))


def formatear_tiempo_viaje(distancia_km: float, ritmo: str = "normal") -> str:
    clave = norm(ritmo or "normal")
    if clave not in RITMOS_VIAJE:
        raise ValueError(f"ritmo de viaje inválido {ritmo!r} (usa: {', '.join(RITMOS_VIAJE)})")
    info = RITMOS_VIAJE[clave]
    km_h, km_d = info["km_hora"], info["km_dia"]
    if distancia_km <= 0:
        return "0 min"
    if distancia_km < km_h:
        mins = max(1, round((distancia_km / km_h) * 60))
        return f"{mins} min a pie ({clave})"
    if distancia_km < km_d:
        horas = distancia_km / km_h
        return f"{cifra(horas)} h a pie ({clave})"
    dias = int(distancia_km // km_d)
    resto = distancia_km - dias * km_d
    horas = round(resto / km_h)
    if horas >= 8:
        dias += 1
        horas = 0
    d_txt = f"{dias} {'día' if dias == 1 else 'días'}"
    h_txt = f" y {horas} h" if horas > 0 else ""
    return f"{d_txt}{h_txt} a pie ({clave})"


def ajustar_mundo(datos: dict, nombre: str | None = None, unidad: str | None = None) -> dict:
    m = _mundo(datos)
    if nombre:
        m["nombre"] = nombre.strip()
    if unidad:
        m["unidad"] = unidad.strip()
    return m


def _id_lugar(nombre: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(nombre)).strip("-") or "lugar"


def _exacto(datos: dict, nombre: str) -> dict | None:
    clave = norm(nombre or "")
    if not clave:
        raise ValueError("falta el nombre del lugar")
    return next((l for l in (datos.get("mundo") or {}).get("lugares", []) if clave in {norm(l["nombre"]), l["id"]}), None)


def buscar_lugar(datos: dict, nombre: str) -> dict:
    """Por nombre o id (sin tildes); un prefijo único también vale."""
    exacto = _exacto(datos, nombre)
    if exacto is not None:
        return exacto
    lugares = (datos.get("mundo") or {}).get("lugares", [])
    candidatos = [l for l in lugares if norm(l["nombre"]).startswith(norm(nombre))]
    if len(candidatos) == 1:
        return candidatos[0]
    if candidatos:
        raise ValueError(f"{nombre!r} es ambiguo: {', '.join(l['nombre'] for l in candidatos)}")
    raise ValueError(f"no hay lugar {nombre!r} en el mapa del mundo (hay: {', '.join(l['nombre'] for l in lugares) or 'ninguno'})")


def _coordenada(valor, eje: str) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{eje} tiene que ser un número") from None
    if not math.isfinite(numero) or abs(numero) > 100000:
        raise ValueError(f"{eje} fuera de rango")
    return numero


def poner_lugar(datos: dict, nombre: str, x=None, y=None, tipo=None, nota=None,
                en: str | None = None, visitado: bool | None = None) -> tuple[dict, bool]:
    """Crea o actualiza un lugar conocido; devuelve (lugar, es_nuevo).

    Para editar hace falta el nombre o el id exactos: un prefijo podría ser otro sitio.
    """
    lugar = _exacto(datos, nombre)
    m = _mundo(datos)
    nuevo = lugar is None
    padre_id = None
    if en is not None:
        if norm(en) not in ("", "-", "ninguno", "raiz"):
            padre = buscar_lugar(datos, en)
            if lugar is not None and padre["id"] == lugar["id"]:
                raise ValueError("un lugar no puede estar dentro de sí mismo")
            padre_id = padre["id"]
    if nuevo:
        if x is None or y is None:
            raise ValueError(f"{nombre!r} es un lugar nuevo: dale --x y --y en el mapa del mundo")
        base = ident = _id_lugar(nombre)
        n = 2
        while any(l["id"] == ident for l in m["lugares"]):
            ident, n = f"{base}-{n}", n + 1
        lugar = {"id": ident, "nombre": nombre.strip(), "tipo": "lugar"}
        m["lugares"].append(lugar)
    if x is not None:
        lugar["x"] = _coordenada(x, "x")
    if y is not None:
        lugar["y"] = _coordenada(y, "y")
    if tipo:
        lugar["tipo"] = tipo.strip()
    if nota:
        lugar["nota"] = nota.strip()
    if en is not None:
        if padre_id:
            lugar["en"] = padre_id
        else:
            lugar.pop("en", None)
    if visitado is not None:
        lugar["visitado"] = bool(visitado)
    return lugar, nuevo


def quitar_lugar(datos: dict, nombre: str) -> dict:
    m = _mundo(datos)
    lugar = buscar_lugar(datos, nombre)
    m["lugares"].remove(lugar)
    for h in m["lugares"]:
        if h.get("en") == lugar["id"]:
            h.pop("en", None)
    m["rutas"] = [r for r in m["rutas"] if lugar["id"] not in (r["de"], r["a"])]
    if m.get("actual") == lugar["id"]:
        m.pop("actual")
    return lugar


def poner_ruta(datos: dict, de: str, a: str, tipo=None, tiempo=None, distancia=None,
               quitar: bool = False, trazo: str | list | None = None, ritmo: str | None = None) -> dict:
    m = _mundo(datos)
    origen, destino = buscar_lugar(datos, de), buscar_lugar(datos, a)
    if origen is destino:
        raise ValueError("una ruta une dos lugares distintos")
    if ritmo is not None and norm(ritmo) not in RITMOS_VIAJE:
        raise ValueError(f"ritmo de viaje inválido {ritmo!r} (usa: {', '.join(RITMOS_VIAJE)})")
    pts = _parsear_puntos(trazo, minimo=2) if trazo is not None else None
    par = {origen["id"], destino["id"]}
    existente = next((r for r in m["rutas"] if {r["de"], r["a"]} == par), None)
    if quitar:
        if existente is None:
            raise ValueError(f"no hay ruta entre {origen['nombre']} y {destino['nombre']}")
        m["rutas"].remove(existente)
        return existente
    ruta = existente or {"de": origen["id"], "a": destino["id"]}
    if existente is None:
        m["rutas"].append(ruta)
    if pts is not None:
        ruta["puntos"] = pts
        dist_km = longitud_trazo(pts)
        ruta["distancia_km"] = round(dist_km, 2)
        if not distancia:
            ruta["distancia"] = f"{cifra(dist_km)} {m.get('unidad', UNIDAD)}"
    for campo, valor in (("tipo", tipo), ("tiempo", tiempo), ("distancia", distancia)):
        if valor:
            ruta[campo] = str(valor).strip()
    if (ritmo is not None or (pts is not None and not tiempo and not ruta.get("tiempo"))):
        dist_base = ruta.get("distancia_km") or (longitud_trazo(ruta["puntos"]) if ruta.get("puntos") else recta(origen, destino))
        ruta["tiempo"] = formatear_tiempo_viaje(dist_base, ritmo or "normal")
    return ruta


def poner_region(datos: dict, nombre: str, bioma: str | None = None, puntos: str | list | None = None,
                 nota: str | None = None, en: str | None = None, quitar: bool = False) -> dict:
    """Crea, actualiza o quita una región poligonal con bioma en el mapa del mundo."""
    m = _mundo(datos)
    regiones = m.setdefault("regiones", [])
    clave = norm(nombre or "")
    if not clave:
        raise ValueError("falta el nombre de la región")
    reg = next((r for r in regiones if clave in {norm(r["nombre"]), r["id"]}), None)
    if quitar:
        if reg is None:
            raise ValueError(f"no hay región {nombre!r} en el mapa del mundo")
        regiones.remove(reg)
        return reg
    if bioma is not None and norm(bioma) not in BIOMAS:
        raise ValueError(f"bioma desconocido {bioma!r} (usa: {', '.join(BIOMAS)})")
    pts = _parsear_puntos(puntos, minimo=3) if puntos is not None else None
    padre_id = buscar_lugar(datos, en)["id"] if en else None
    if reg is None:
        if pts is None:
            raise ValueError(f"{nombre!r} es una región nueva: dale al menos 3 vértices con --puntos 'x1,y1 x2,y2 x3,y3'")
        base = ident = _id_lugar(nombre)
        n = 2
        while any(r["id"] == ident for r in regiones):
            ident, n = f"{base}-{n}", n + 1
        reg = {"id": ident, "nombre": nombre.strip(), "bioma": norm(bioma or "bosque"), "puntos": pts}
        regiones.append(reg)
    else:
        if bioma:
            reg["bioma"] = norm(bioma)
        if pts is not None:
            reg["puntos"] = pts
    if nota:
        reg["nota"] = nota.strip()
    if en is not None:
        if padre_id:
            reg["en"] = padre_id
        else:
            reg.pop("en", None)
    return reg


def poner_trazo(datos: dict, nombre: str, tipo: str | None = None, puntos: str | list | None = None,
                nota: str | None = None, en: str | None = None, quitar: bool = False) -> dict:
    """Crea, actualiza o quita un río, camino, costa o frontera con trazado poligonal."""
    m = _mundo(datos)
    trazos = m.setdefault("trazos", [])
    clave = norm(nombre or "")
    if not clave:
        raise ValueError("falta el nombre del trazo")
    trazo = next((t for t in trazos if clave in {norm(t["nombre"]), t["id"]}), None)
    if quitar:
        if trazo is None:
            raise ValueError(f"no hay trazo {nombre!r} en el mapa del mundo")
        trazos.remove(trazo)
        return trazo
    if tipo is not None and norm(tipo) not in TIPOS_TRAZO:
        raise ValueError(f"tipo de trazo desconocido {tipo!r} (usa: {', '.join(TIPOS_TRAZO)})")
    pts = _parsear_puntos(puntos, minimo=2) if puntos is not None else None
    padre_id = buscar_lugar(datos, en)["id"] if en else None
    if trazo is None:
        if pts is None:
            raise ValueError(f"{nombre!r} es un trazo nuevo: dale al menos 2 puntos con --puntos 'x1,y1 x2,y2'")
        base = ident = _id_lugar(nombre)
        n = 2
        while any(t["id"] == ident for t in trazos):
            ident, n = f"{base}-{n}", n + 1
        trazo = {
            "id": ident, "nombre": nombre.strip(),
            "tipo": norm(tipo or "rio"), "puntos": pts,
            "longitud": round(longitud_trazo(pts), 2),
        }
        trazos.append(trazo)
    else:
        if tipo:
            trazo["tipo"] = norm(tipo)
        if pts is not None:
            trazo["puntos"] = pts
            trazo["longitud"] = round(longitud_trazo(pts), 2)
    if nota:
        trazo["nota"] = nota.strip()
    if en is not None:
        if padre_id:
            trazo["en"] = padre_id
        else:
            trazo.pop("en", None)
    return trazo


def consultar_viaje(datos: dict, de: str, a: str, ritmo: str | None = None) -> tuple[dict, str]:
    """Calcula distancia y tiempo de viaje entre dos lugares según el SRD 5.2.1 (sin mutar)."""
    m = datos.get("mundo") or {}
    unidad = m.get("unidad", UNIDAD)
    origen, destino = buscar_lugar(datos, de), buscar_lugar(datos, a)
    dist_recta = recta(origen, destino)
    par = {origen["id"], destino["id"]}
    ruta = next((r for r in (m.get("rutas") or []) if {r["de"], r["a"]} == par), None)
    if ruta and ruta.get("puntos"):
        dist_ruta = longitud_trazo(ruta["puntos"])
    elif ruta and ruta.get("distancia_km"):
        dist_ruta = float(ruta["distancia_km"])
    else:
        dist_ruta = dist_recta
    ritmos_ped = [norm(ritmo)] if ritmo else ["rapido", "normal", "lento"]
    for r in ritmos_ped:
        if r not in RITMOS_VIAJE:
            raise ValueError(f"ritmo de viaje inválido {ritmo!r} (usa: {', '.join(RITMOS_VIAJE)})")
    tiempos = {r: formatear_tiempo_viaje(dist_ruta, r) for r in ritmos_ped}
    via_txt = f"por ruta ({ruta.get('tipo', 'camino')}): {cifra(dist_ruta)} {unidad}" if ruta else f"en línea recta: {cifra(dist_recta)} {unidad}"
    lineas = [f"Viaje {origen['nombre']} → {destino['nombre']} ({via_txt}; recta {cifra(dist_recta)} {unidad})"]
    for r in ritmos_ped:
        info = RITMOS_VIAJE[r]
        lineas.append(f"- Ritmo {r} ({cifra(info['km_hora'])} km/h, {cifra(info['km_dia'])} km/día): {tiempos[r]} · {info['efecto']}")
    res = {
        "de": origen["id"], "a": destino["id"],
        "distancia_recta": round(dist_recta, 2),
        "distancia_viaje": round(dist_ruta, 2),
        "unidad": unidad,
        "ruta": ruta,
        "tiempos": tiempos,
    }
    return res, "\n".join(lineas)


def generar_mundo(datos: dict, *, semilla: int | str | None = None, bioma: str | None = None,
                  lugares_n: int = 4, en: str | None = None, nombre: str | None = None) -> dict:
    """Genera de forma determinista una comarca (o el mapa interior de un lugar con `--en`)."""
    bioma_ef = norm(bioma or "bosque")
    if bioma_ef not in BIOMAS:
        raise ValueError(f"bioma desconocido {bioma!r} (usa: {', '.join(BIOMAS)})")
    if not (2 <= int(lugares_n) <= 12):
        raise ValueError("el número de lugares a generar va de 2 a 12")
    padre = buscar_lugar(datos, en) if en else None
    sem_num = _semilla_entera(semilla, f"mundo:{bioma_ef}:{lugares_n}:{padre['id'] if padre else ''}:{nombre or ''}")
    rng = random.Random(sem_num)
    m = _mundo(datos)
    if nombre and not padre:
        m["nombre"] = nombre.strip()
    elif not m.get("nombre") and not padre:
        m["nombre"] = f"Comarca de {bioma_ef.capitalize()}"

    escala = 0.8 if padre else 18.0
    cx = float(padre["x"]) if padre else 0.0
    cy = float(padre["y"]) if padre else 0.0
    padre_id = padre["id"] if padre else None

    # Región de bioma y río/camino principal
    reg_nombre = f"Entorno de {padre['nombre']}" if padre else f"Tierras de {bioma_ef}"
    reg_pts = [
        [round(cx + math.cos(a) * escala * (1.1 + 0.25 * rng.random()), 1),
         round(cy + math.sin(a) * escala * (0.9 + 0.25 * rng.random()), 1)]
        for a in (i * math.pi / 3 for i in range(6))
    ]
    poner_region(datos, reg_nombre, bioma="urbano" if padre else bioma_ef, puntos=reg_pts, en=padre_id)

    rio_nombre = f"Canal de {padre['nombre']}" if padre else "Río Mayor"
    rio_pts = [
        [round(cx - escala * 1.1, 1), round(cy + escala * 0.6, 1)],
        [round(cx + rng.uniform(-0.2, 0.2) * escala, 1), round(cy + rng.uniform(-0.2, 0.2) * escala, 1)],
        [round(cx + escala * 1.1, 1), round(cy - escala * 0.6, 1)],
    ]
    poner_trazo(datos, rio_nombre, tipo="rio", puntos=rio_pts, en=padre_id)

    catalogo_pueblo = [
        ("Plaza del Mercado", "plaza"), ("Posada del Camino", "edificio"), ("Herrería", "edificio"),
        ("Puente Viejo", "puente"), ("Templo", "edificio"), ("Torre de Guardia", "castillo"),
        ("Muelle del Canal", "puerto"), ("Almacén", "edificio"), ("Archivo", "edificio"),
        ("Puerta Norte", "edificio"), ("Molino", "edificio"), ("Pozo Viejo", "lugar"),
    ]
    catalogo_comarca = [
        ("Valdris", "pueblo"), ("Fuerte Gris", "castillo"), ("Puerto Bruma", "puerto"),
        ("Ruinas del Pacto", "ruina"), ("Aldea del Río", "aldea"), ("Atalaya Norte", "torre"),
        ("Cruce de Piedra", "pueblo"), ("Santuario Viejo", "ruina"), ("Mina Honda", "mina"),
        ("Vado del Roble", "lugar"), ("Campamento Sur", "aldea"), ("Cumbre Helada", "montana"),
    ]
    base_nombres = catalogo_pueblo if padre else catalogo_comarca
    creados = []
    for i in range(int(lugares_n)):
        nom_base, tipo_l = base_nombres[i % len(base_nombres)]
        ang = (2 * math.pi * i) / int(lugares_n) + rng.uniform(-0.25, 0.25)
        rad = (0.15 if i == 0 else rng.uniform(0.35, 0.9)) * escala
        lx = round(cx + math.cos(ang) * rad, 1)
        ly = round(cy + math.sin(ang) * rad, 1)
        lug, _ = poner_lugar(datos, nom_base, x=lx, y=ly, tipo=tipo_l, en=padre_id, visitado=(i == 0))
        creados.append(lug)

    for a_lug, b_lug in zip(creados, creados[1:]):
        mx = round((a_lug["x"] + b_lug["x"]) / 2 + rng.uniform(-0.12, 0.12) * escala, 1)
        my = round((a_lug["y"] + b_lug["y"]) / 2 + rng.uniform(-0.12, 0.12) * escala, 1)
        poner_ruta(
            datos, a_lug["id"], b_lug["id"],
            tipo="calle" if padre else "camino",
            trazo=[[a_lug["x"], a_lug["y"]], [mx, my], [b_lug["x"], b_lug["y"]]],
            ritmo="normal",
        )
    if not m.get("actual") and creados:
        m["actual"] = creados[0]["id"]
    m["generador"] = {"semilla": sem_num, "bioma": bioma_ef, "lugares": len(creados), "en": padre_id}
    return m["generador"]


def ir_a(datos: dict, nombre: str) -> dict:
    m = _mundo(datos)
    lugar = buscar_lugar(datos, nombre)
    m["actual"] = lugar["id"]
    lugar["visitado"] = True
    if lugar.get("en"):
        padre = _por_id(datos).get(lugar["en"])
        if padre:
            padre["visitado"] = True
    return lugar


def _por_id(datos: dict) -> dict[str, dict]:
    return {l["id"]: l for l in (datos.get("mundo") or {}).get("lugares", [])}


def recta(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _detalle_ruta(ruta: dict) -> str:
    return ", ".join(ruta[k] for k in ("tipo", "distancia", "tiempo") if ruta.get(k))


def mundo_texto(datos: dict) -> str:
    """El mapa del mundo para el narrador: dónde están, qué conocen y a cuánto queda."""
    m = datos.get("mundo") or {}
    lugares = m.get("lugares") or []
    regiones = m.get("regiones") or []
    trazos = m.get("trazos") or []
    if not lugares and not regiones and not trazos:
        return ""
    unidad = m.get("unidad", UNIDAD)
    por_id = _por_id(datos)
    actual = por_id.get(m.get("actual"))
    rutas = [r for r in m.get("rutas") or [] if r["de"] in por_id and r["a"] in por_id]
    en_actual = f" (en {por_id[actual['en']]['nombre']})" if actual and actual.get("en") in por_id else ""
    lineas = [
        f"Mapa del mundo: {m.get('nombre') or 'sin nombre'} (coordenadas en {unidad})",
        f"Están en: {actual['nombre']}{en_actual}" if actual else "Están en: (sin marcar: `mundo aqui \"<lugar>\"`)",
    ]
    if lugares:
        def _etiq_lugar(l: dict) -> str:
            padre = f" en {por_id[l['en']]['nombre']}" if l.get("en") in por_id else ""
            return f"{l['nombre']} ({l.get('tipo', 'lugar')}{padre}, {cifra(l['x'])}·{cifra(l['y'])})"
        lineas.append("Lugares conocidos: " + " · ".join(_etiq_lugar(l) for l in lugares))
    if regiones:
        lineas.append("Regiones: " + " · ".join(f"{r['nombre']} ({r.get('bioma', 'región')})" for r in regiones))
    if trazos:
        lineas.append(
            "Trazos: "
            + " · ".join(f"{t['nombre']} ({t.get('tipo', 'rio')}, {cifra(t.get('longitud', longitud_trazo(t['puntos'])))} {unidad})" for t in trazos)
        )
    if actual:
        tramos = []
        for l in lugares:
            if l is actual:
                continue
            ruta = next((r for r in rutas if {r["de"], r["a"]} == {actual["id"], l["id"]}), None)
            extra = "" if ruta is None else f" (ruta: {_detalle_ruta(ruta) or 'conocida'})"
            tramos.append(f"{l['nombre']} {cifra(recta(actual, l))} {unidad} en línea recta{extra}")
        if tramos:
            lineas.append(f"Desde {actual['nombre']}: " + " · ".join(tramos))
    if rutas:
        lineas.append("Rutas: " + " · ".join(
            f"{por_id[r['de']]['nombre']} – {por_id[r['a']]['nombre']}" + (f" ({_detalle_ruta(r)})" if _detalle_ruta(r) else "")
            for r in rutas
        ))
    return "\n".join(lineas)

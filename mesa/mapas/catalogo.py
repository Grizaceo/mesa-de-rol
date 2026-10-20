"""El catálogo curado y los importadores.

Lo que hay en `biblioteca/mapas/` (con su procedencia y licencia) y lo que
entra desde fuera: Universal VTT (`.dd2vtt` y `.uvtt`), Watabou y Azgaar.
Importar lee un archivo de fuera de la partida, así que es de la CLI
deliberada, no del MCP de juego (ver `mesa/capacidades.py`).
"""

from __future__ import annotations

import base64
import json
import math
import re
from pathlib import Path
from .. import distribucion, estado, imagenes
from ..texto import norm

from .base import (
    CELDA,
    COLUMNAS,
    MAX_FILAS,
    nombre_celda,
)

from .zona import (
    nueva_zona,
    poner_luz,
    reubicar,
    semantica_terreno,
)

from .generadores import generar_zona

from .mundo import (
    _id_lugar,
    _mundo,
    ir_a,
    poner_lugar,
    poner_region,
    poner_ruta,
    poner_trazo,
)


def _carpetas_catalogo() -> list[Path]:
    carpetas = [estado.RAIZ / "biblioteca" / "mapas"]
    checkout = distribucion.raiz_checkout()
    if checkout is not None:
        otra = checkout / "biblioteca" / "mapas"
        if otra not in carpetas:
            carpetas.append(otra)
    return carpetas


def leer_catalogo_mapas(consulta: str = "") -> list[dict]:
    """Lee las entradas curadas de `biblioteca/mapas/indice.json` (con licencia y procedencia)."""
    vistos: set[str] = set()
    entradas: list[dict] = []
    for carpeta in _carpetas_catalogo():
        indice = carpeta / "indice.json"
        if not indice.is_file():
            continue
        for item in json.loads(indice.read_text(encoding="utf-8")):
            if item.get("id") and item["id"] not in vistos:
                vistos.add(item["id"])
                entradas.append({**item, "_carpeta": str(carpeta)})
    if not consulta.strip():
        return entradas
    q = norm(consulta)
    palabras = [p for p in re.split(r"\W+", q) if p]
    filtradas = []
    for item in entradas:
        bolsa = norm(" ".join([
            item.get("id", ""), item.get("nombre", ""), item.get("ambito", ""),
            item.get("formato", ""), item.get("descripcion", ""),
            " ".join(item.get("etiquetas") or []),
        ]))
        if all(p in bolsa for p in palabras):
            filtradas.append(item)
    return filtradas


def _rasterizar_segmento(rejilla: list[list[str]], x1: float, y1: float, x2: float, y2: float, ch: str) -> None:
    alto, ancho = len(rejilla), len(rejilla[0])
    pasos = max(1, int(math.hypot(x2 - x1, y2 - y1) * 4))
    for i in range(pasos + 1):
        t = i / pasos
        cx = int(round(x1 + (x2 - x1) * t))
        fy = int(round(y1 + (y2 - y1) * t))
        if 0 <= cx < ancho and 0 <= fy < alto:
            rejilla[fy][cx] = ch


def importar_watabou_json(doc: dict, *, nombre: str | None = None, celda: float | None = None,
                          luz: str | None = None, origen: dict | None = None) -> dict:
    """Convierte un JSON de Watabou One Page Dungeon (`rects`, `doors`, `columns`, `water`, `notes`) en `escena.mapa`."""
    rects = doc.get("rects")
    if not isinstance(rects, list) or not rects:
        raise ValueError("JSON de Watabou inválido: falta la lista `rects`")
    xs = [r["x"] for r in rects] + [r["x"] + r["w"] for r in rects]
    ys = [r["y"] for r in rects] + [r["y"] + r["h"] for r in rects]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(1, max_x - min_x)
    span_y = max(1, max_y - min_y)
    # Margen de 1 casilla de muro alrededor; escalar si supera 26×40
    esc_x = min(1.0, (len(COLUMNAS) - 2) / span_x)
    esc_y = min(1.0, (MAX_FILAS - 2) / span_y)
    escala = min(esc_x, esc_y)
    ancho = max(5, min(len(COLUMNAS), int(math.ceil(span_x * escala)) + 2))
    alto = max(5, min(MAX_FILAS, int(math.ceil(span_y * escala)) + 2))

    def mapear(vx: float, vy: float) -> tuple[int, int]:
        cx = max(1, min(ancho - 2, int(round((vx - min_x) * escala)) + 1))
        fy = max(1, min(alto - 2, int(round((vy - min_y) * escala)) + 1))
        return cx, fy

    g = [[" "] * ancho for _ in range(alto)]
    for r in rects:
        c1, f1 = mapear(r["x"], r["y"])
        c2, f2 = mapear(r["x"] + r["w"] - 1, r["y"] + r["h"] - 1)
        if r.get("rotunda"):
            mc, mf = (c1 + c2) / 2.0, (f1 + f2) / 2.0
            rx, ry = max(1.0, (c2 - c1) / 2.0 + 0.5), max(1.0, (f2 - f1) / 2.0 + 0.5)
            for fy in range(f1, f2 + 1):
                for cx in range(c1, c2 + 1):
                    if ((cx - mc) / rx) ** 2 + ((fy - mf) / ry) ** 2 <= 1.15:
                        g[fy][cx] = "."
        else:
            for fy in range(f1, f2 + 1):
                for cx in range(c1, c2 + 1):
                    g[fy][cx] = "."

    # Rodear con muros '#' toda casilla de suelo
    for fy in range(alto):
        for cx in range(ancho):
            if g[fy][cx] != " ":
                continue
            if any(
                0 <= fy + df < alto and 0 <= cx + dc < ancho and g[fy + df][cx + dc] == "."
                for df in (-1, 0, 1) for dc in (-1, 0, 1) if (df or dc)
            ):
                g[fy][cx] = "#"

    ley_extra: dict[str, str] = {}
    for w in doc.get("water") or []:
        if "w" in w and "h" in w:
            c1, f1 = mapear(w["x"], w["y"])
            c2, f2 = mapear(w["x"] + w["w"] - 1, w["y"] + w["h"] - 1)
            for fy in range(f1, f2 + 1):
                for cx in range(c1, c2 + 1):
                    if g[fy][cx] == ".":
                        g[fy][cx] = "~"
        elif "x" in w and "y" in w:
            cx, fy = mapear(w["x"], w["y"])
            if g[fy][cx] == ".":
                g[fy][cx] = "~"

    for col in doc.get("columns") or []:
        cx, fy = mapear(col["x"], col["y"])
        if g[fy][cx] == ".":
            g[fy][cx] = "P"
            ley_extra["P"] = "pilar de piedra [bloquea-paso, cobertura=tres-cuartos]"

    for d in doc.get("doors") or []:
        cx, fy = mapear(d["x"], d["y"])
        dtype = int(d.get("type", 1))
        if dtype in (0, 2):
            g[fy][cx] = "."
        elif dtype in (3, 8, 9):
            g[fy][cx] = "^"
        elif dtype in (4, 7):
            g[fy][cx] = "="
            ley_extra["="] = "reja de hierro [bloquea-paso, cobertura=tres-cuartos]"
        else:
            g[fy][cx] = "+"

    notas_publicas = []
    for n in doc.get("notes") or []:
        pos = n.get("pos") or {}
        if "x" in pos and "y" in pos:
            cx, fy = mapear(pos["x"], pos["y"])
            if g[fy][cx] == ".":
                g[fy][cx] = "A"
                ley_extra["A"] = "altar u objeto notable [dificil, cobertura=media]"
            if n.get("text"):
                notas_publicas.append({"celda": nombre_celda(cx, fy), "texto": str(n["text"]).strip()})

    focos = [str(f) for f in (doc.get("luces") or [])]
    dibujo = "\n".join("".join(fila) for fila in g)
    mapa = nueva_zona(
        dibujo,
        leyenda=[f"{k}={v}" for k, v in ley_extra.items()],
        celda=celda,
        nombre=nombre or doc.get("title") or "Mazmorra",
        luz=luz or doc.get("luz") or "oscuridad",
    )
    if focos:
        poner_luz(mapa, mapa.get("luz"), focos)
    if notas_publicas:
        mapa["notas_mapa"] = notas_publicas
    if origen:
        mapa["origen"] = origen
    return mapa


def importar_uvtt(doc: dict, *, slug: str | None = None, nombre: str | None = None,
                  celda: float | None = None, luz: str | None = None, origen: dict | None = None) -> dict:
    """Convierte un archivo Universal VTT (`.dd2vtt` / `.uvtt`) en `escena.mapa` + imagen de fondo opcional."""
    res = doc.get("resolution")
    if not isinstance(res, dict) or "map_size" not in res:
        raise ValueError("archivo Universal VTT (.dd2vtt/.uvtt) inválido: falta `resolution.map_size`")
    orig_x = float((res.get("map_origin") or {}).get("x", 0))
    orig_y = float((res.get("map_origin") or {}).get("y", 0))
    size_x = max(1.0, float(res["map_size"].get("x", 14)))
    size_y = max(1.0, float(res["map_size"].get("y", 10)))
    ancho = max(5, min(len(COLUMNAS), int(round(size_x))))
    alto = max(5, min(MAX_FILAS, int(round(size_y))))
    sx = (ancho - 1) / max(1.0, size_x - 1) if size_x > 1 else 1.0
    sy = (alto - 1) / max(1.0, size_y - 1) if size_y > 1 else 1.0

    def a_celda(px: float, py: float) -> tuple[float, float]:
        return (px - orig_x) * sx, (py - orig_y) * sy

    filas_base = doc.get("filas_terreno")
    if isinstance(filas_base, list) and len(filas_base) == alto and all(len(f) == ancho for f in filas_base):
        g = [list(f) for f in filas_base]
    else:
        g = [["."] * ancho for _ in range(alto)]

    for trazo in (doc.get("line_of_sight") or []) + (doc.get("objects_line_of_sight") or []):
        if not isinstance(trazo, list) or len(trazo) < 2:
            continue
        for p1, p2 in zip(trazo, trazo[1:]):
            x1, y1 = a_celda(float(p1["x"]), float(p1["y"]))
            x2, y2 = a_celda(float(p2["x"]), float(p2["y"]))
            _rasterizar_segmento(g, x1, y1, x2, y2, "#")

    ley_extra = dict(doc.get("leyenda_extra") or {})
    for portal in doc.get("portals") or []:
        pos = portal.get("position") or {}
        if "x" not in pos or "y" not in pos:
            continue
        cx_f, fy_f = a_celda(float(pos["x"]), float(pos["y"]))
        cx, fy = max(0, min(ancho - 1, int(round(cx_f)))), max(0, min(alto - 1, int(round(fy_f))))
        if portal.get("window") or portal.get("tipo") == "ventana":
            g[fy][cx] = "="
        elif portal.get("closed", True) is False:
            g[fy][cx] = "/"
            ley_extra["/"] = "puerta abierta"
        else:
            g[fy][cx] = "+"

    amb = luz
    if not amb:
        env = doc.get("environment") or {}
        amb_raw = norm(str(env.get("ambient_light") or ""))
        amb = "oscuridad" if amb_raw in ("darkness", "oscuridad", "none", "false") else (
            "penumbra" if amb_raw in ("dim", "penumbra", "low") else "brillante"
        )

    dibujo = "\n".join("".join(fila) for fila in g)
    celda_m = float(celda if celda is not None else doc.get("celda", CELDA))
    mapa = nueva_zona(
        dibujo,
        leyenda=[f"{k}={v}" for k, v in ley_extra.items()],
        celda=celda_m,
        nombre=nombre or doc.get("nombre") or doc.get("title") or "Mapa VTT",
        luz=amb,
    )

    focos = []
    for i, lgt in enumerate(doc.get("lights") or [], start=1):
        pos = lgt.get("position") or {}
        if "x" not in pos or "y" not in pos:
            continue
        cx_f, fy_f = a_celda(float(pos["x"]), float(pos["y"]))
        cx, fy = max(0, min(ancho - 1, int(round(cx_f)))), max(0, min(alto - 1, int(round(fy_f))))
        r_sq = max(1.0, float(lgt.get("range", 4.0)))
        r_m = round(r_sq * celda_m * 0.5, 1)
        nom_f = lgt.get("nombre") or f"luz {i}"
        focos.append(f"{nombre_celda(cx, fy)}:{r_m}:{r_m}:{nom_f}")
    if focos:
        poner_luz(mapa, mapa.get("luz"), focos)

    img_b64 = doc.get("image")
    if isinstance(img_b64, str) and img_b64.strip() and slug:
        if "," in img_b64 and img_b64.strip().startswith("data:"):
            img_b64 = img_b64.split(",", 1)[1]
        raw = base64.b64decode(img_b64)
        if len(raw) > imagenes.TAMANO_MAXIMO:
            raise ValueError("la imagen embebida en el .dd2vtt supera 15 MB")
        ext = imagenes.verificar_raster(raw, "fondo-uvtt")
        base_nom = _id_lugar(mapa.get("nombre") or "zona")
        nombre_img = f"mapa-{base_nom}{ext}"
        carpeta_img = estado.dir_partida(slug) / "imagenes"
        carpeta_img.mkdir(exist_ok=True)
        (carpeta_img / nombre_img).write_bytes(raw)
        mapa["fondo"] = nombre_img
    if origen:
        mapa["origen"] = origen
    return mapa


def importar_zona_archivo(ruta: str | Path, *, slug: str | None = None, nombre: str | None = None,
                          celda: float | None = None, luz: str | None = None,
                          licencia: str | None = None, fuente: str | None = None) -> dict:
    """Importa un archivo local `.dd2vtt`/`.uvtt` o JSON de Watabou y devuelve `escena.mapa`."""
    p = Path(ruta).expanduser()
    if not p.is_file():
        raise ValueError(f"no existe el archivo de mapa: {ruta}")
    if p.stat().st_size > imagenes.TAMANO_MAXIMO:
        raise ValueError("el archivo de mapa supera 15 MB")
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{p.name} no es un archivo JSON/.dd2vtt válido: {e}") from None
    if not isinstance(doc, dict):
        raise ValueError(f"{p.name}: el contenido debe ser un objeto JSON")
    meta_doc = doc.get("meta") or {}
    origen = {
        "archivo": p.name,
        "licencia": licencia or meta_doc.get("licencia") or doc.get("licencia") or "uso local",
        "fuente": fuente or meta_doc.get("fuente") or doc.get("fuente") or p.name,
    }
    if meta_doc.get("autor") or doc.get("autor"):
        origen["autor"] = meta_doc.get("autor") or doc.get("autor")
    if "resolution" in doc and isinstance(doc["resolution"], dict):
        return importar_uvtt(doc, slug=slug, nombre=nombre or p.stem, celda=celda, luz=luz, origen=origen)
    if "rects" in doc and isinstance(doc["rects"], list):
        return importar_watabou_json(doc, nombre=nombre or p.stem, celda=celda, luz=luz, origen=origen)
    if "filas" in doc and isinstance(doc["filas"], list):
        mapa = nueva_zona("\n".join(doc["filas"]), doc.get("leyenda"), celda or doc.get("celda"), nombre or doc.get("nombre"), luz=luz or doc.get("luz"))
        mapa["origen"] = origen
        return mapa
    raise ValueError(f"{p.name}: formato no reconocido (se esperaba Universal VTT `.dd2vtt`/`.uvtt` o Watabou JSON con `rects`)")


def importar_mundo_datos(datos: dict, doc: dict, *, nombre: str | None = None, origen: dict | None = None) -> dict:
    """Importa lugares, regiones, ríos y rutas desde un JSON de Azgaar, GeoJSON o plantilla de mundo."""
    if not isinstance(doc, dict):
        raise ValueError("el mapa del mundo debe ser un objeto JSON")
    m = _mundo(datos)
    info = doc.get("info") or {}
    if nombre or doc.get("nombre") or info.get("mapName"):
        m["nombre"] = (nombre or doc.get("nombre") or info.get("mapName")).strip()
    if doc.get("unidad"):
        m["unidad"] = str(doc["unidad"]).strip()

    n_lug = n_reg = n_trz = n_rut = 0
    # 1. Formato directo o plantilla curada (lugares, regiones, trazos, rutas)
    for reg in doc.get("regiones") or []:
        poner_region(datos, reg["nombre"], bioma=reg.get("bioma", "bosque"), puntos=reg["puntos"], nota=reg.get("nota"), en=reg.get("en"))
        n_reg += 1
    for t in doc.get("trazos") or []:
        poner_trazo(datos, t["nombre"], tipo=t.get("tipo", "rio"), puntos=t["puntos"], nota=t.get("nota"), en=t.get("en"))
        n_trz += 1
    # Primero lugares raíz, luego lugares anidados con `en`
    lugares_doc = list(doc.get("lugares") or [])
    for l in [x for x in lugares_doc if not x.get("en")] + [x for x in lugares_doc if x.get("en")]:
        poner_lugar(datos, l["nombre"], x=l["x"], y=l["y"], tipo=l.get("tipo", "lugar"), nota=l.get("nota"), en=l.get("en"), visitado=l.get("visitado"))
        n_lug += 1
    for r in doc.get("rutas") or []:
        poner_ruta(datos, r["de"], r["a"], tipo=r.get("tipo", "camino"), tiempo=r.get("tiempo"), distancia=r.get("distancia"), trazo=r.get("puntos"), ritmo=r.get("ritmo"))
        n_rut += 1

    # 2. Formato Azgaar Fantasy Map Generator (`pack.burgs`, `pack.rivers`, `pack.routes`)
    pack = doc.get("pack")
    if isinstance(pack, dict):
        for b in pack.get("burgs") or []:
            if not isinstance(b, dict) or not b.get("name") or b.get("removed"):
                continue
            bx, by = b.get("x"), b.get("y")
            if bx is None or by is None:
                continue
            tipo_b = "capital" if b.get("capital") else ("puerto" if b.get("port") else "pueblo")
            poner_lugar(datos, b["name"], x=round(float(bx), 1), y=round(-float(by), 1), tipo=tipo_b, nota=b.get("type"))
            n_lug += 1
        for rv in pack.get("rivers") or []:
            pts_rv = rv.get("points") or rv.get("cells_points")
            if isinstance(pts_rv, list) and len(pts_rv) >= 2 and rv.get("name"):
                poner_trazo(datos, rv["name"], tipo="rio", puntos=[[round(float(p[0]), 1), round(-float(p[1]), 1)] for p in pts_rv])
                n_trz += 1

    # 3. Formato GeoJSON (`FeatureCollection`)
    if doc.get("type") == "FeatureCollection" and isinstance(doc.get("features"), list):
        for feat in doc["features"]:
            geom = (feat or {}).get("geometry") or {}
            props = (feat or {}).get("properties") or {}
            gtype = geom.get("type")
            coords = geom.get("coordinates") or []
            nom = props.get("name") or props.get("nombre") or props.get("burg") or props.get("id")
            if not nom or not coords:
                continue
            if gtype == "Point" and len(coords) >= 2:
                poner_lugar(datos, str(nom), x=coords[0], y=coords[1], tipo=props.get("type") or props.get("tipo") or "lugar", nota=props.get("note") or props.get("nota"))
                n_lug += 1
            elif gtype == "LineString" and len(coords) >= 2:
                poner_trazo(datos, str(nom), tipo=props.get("type") or "rio", puntos=[[c[0], c[1]] for c in coords])
                n_trz += 1
            elif gtype == "Polygon" and coords and len(coords[0]) >= 3:
                poner_region(datos, str(nom), bioma=props.get("biome") or props.get("bioma") or "bosque", puntos=[[c[0], c[1]] for c in coords[0][:-1] if len(coords[0]) > 3] or [[c[0], c[1]] for c in coords[0]])
                n_reg += 1

    if doc.get("actual"):
        try:
            ir_a(datos, doc["actual"])
        except ValueError:
            pass
    if origen:
        m["origen"] = origen
    return {"lugares": n_lug, "regiones": n_reg, "trazos": n_trz, "rutas": n_rut}


def importar_mundo_archivo(datos: dict, ruta: str | Path, *, nombre: str | None = None,
                           licencia: str | None = None, fuente: str | None = None) -> dict:
    p = Path(ruta).expanduser()
    if not p.is_file():
        raise ValueError(f"no existe el archivo de mundo: {ruta}")
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{p.name} no es un JSON válido: {e}") from None
    meta = (doc.get("meta") if isinstance(doc, dict) else None) or {}
    origen = {
        "archivo": p.name,
        "licencia": licencia or meta.get("licencia") or "uso local",
        "fuente": fuente or meta.get("fuente") or p.name,
    }
    return importar_mundo_datos(datos, doc, nombre=nombre, origen=origen)


def cargar_mapa_catalogo(datos: dict, ident: str, *, slug: str | None = None, nombre: str | None = None) -> tuple[str, dict]:
    """Carga un mapa pre-hecho de `biblioteca/mapas/` por su `id`. Devuelve (ambito, info)."""
    clave = norm(ident or "")
    if not clave:
        raise ValueError("falta el id del mapa del catálogo")
    catalogo = leer_catalogo_mapas()
    item = next((x for x in catalogo if clave in {norm(x["id"]), norm(x.get("nombre", ""))}), None)
    if item is None:
        disponibles = ", ".join(x["id"] for x in catalogo) or "ninguno"
        raise ValueError(f"no hay mapa {ident!r} en biblioteca/mapas (disponibles: {disponibles})")
    ruta = Path(item["_carpeta"]) / item["archivo"]
    origen = {
        "id": item["id"],
        "archivo": item["archivo"],
        "licencia": item.get("licencia", "CC0-1.0"),
        "fuente": item.get("fuente", "biblioteca/mapas"),
        "autor": item.get("autor", ""),
    }
    if item.get("ambito") == "mundo":
        doc = json.loads(ruta.read_text(encoding="utf-8"))
        res = importar_mundo_datos(datos, doc, nombre=nombre or item.get("nombre"), origen=origen)
        return "mundo", {"id": item["id"], "nombre": item.get("nombre"), "licencia": origen["licencia"], **res}
    mapa = importar_zona_archivo(
        ruta, slug=slug, nombre=nombre or item.get("nombre"),
        licencia=origen["licencia"], fuente=origen["fuente"],
    )
    mapa["origen"] = origen
    datos.setdefault("escena", {})["mapa"] = mapa
    return "zona", {
        "id": item["id"], "nombre": mapa.get("nombre"),
        "formato": item.get("formato", "uvtt"),
        "licencia": origen["licencia"],
        "columnas": len(mapa["filas"][0]), "filas": len(mapa["filas"]),
        "fondo": mapa.get("fondo"),
    }


def _buscar_catalogo_por_texto(texto: str) -> dict | None:
    q = norm(texto)
    if not q:
        return None
    candidatos = []
    for item in leer_catalogo_mapas():
        if item.get("ambito") != "zona":
            continue
        nom = norm(item.get("nombre", ""))
        ident = norm(item.get("id", "")).replace("-", " ")
        palabras_id = [p for p in ident.split() if len(p) > 2]
        if (nom and nom in q) or (ident and ident in q) or (len(palabras_id) >= 2 and all(p in q for p in palabras_id)):
            candidatos.append((len(nom or ident), item))
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0], reverse=True)
    return candidatos[0][1]


def _inferir_tipo_zona(texto: str) -> str:
    q = norm(texto)
    for palabras, tipo in (
        (("posada", "taberna", "habitacion", "casa", "salon", "gremio", "causa", "despacho", "interior", "tienda"), "taberna"),
        (("puente", "rio", "vado", "muelle"), "puente"),
        (("bosque", "colina", "camino", "sendero", "campo", "claro"), "bosque"),
        (("cueva", "mina", "caverna", "gruta"), "cueva"),
        (("cripta", "mazmorra", "sotano", "celda", "ruina", "tumba"), "mazmorra"),
    ):
        if any(p in q for p in palabras):
            return tipo
    return "calle"


def _celdas_transitables(mapa: dict, ocupadas: set[str]) -> list[str]:
    filas = mapa.get("filas") or []
    if not filas:
        return []
    alto, ancho = len(filas), len(filas[0])
    cx, cy = (ancho - 1) / 2.0, (alto - 1) / 2.0
    preferidas = []
    otras = []
    for f_idx, fila in enumerate(filas):
        for c_idx, ch in enumerate(fila):
            if ch == " " or ch.isdigit():
                continue
            celda = nombre_celda(c_idx, f_idx)
            if celda in ocupadas:
                continue
            sem = semantica_terreno(mapa, ch)
            if sem.get("bloquea_paso"):
                continue
            dist = abs(c_idx - cx) + abs(f_idx - cy)
            if ch == "." and not sem.get("dificil"):
                preferidas.append((dist, celda))
            else:
                otras.append((dist, celda))
    preferidas.sort()
    otras.sort()
    return [c for _, c in preferidas] + [c for _, c in otras]


def asegurar_mapa_escena(datos: dict, slug: str | None = None) -> list[tuple[dict, str]]:
    """Garantiza que una escena nueva o un movimiento conserve cuadrícula, casillas y lugar del mundo."""
    hechos: list[tuple[dict, str]] = []
    escena = datos.setdefault("escena", {})
    texto_escena = f"{escena.get('lugar', '')} {escena.get('titulo', '')}".strip()
    q_escena = norm(texto_escena)

    mundo = datos.get("mundo") or {}
    if mundo.get("lugares") and q_escena:
        coincidencias = []
        for l in mundo["lugares"]:
            nom_l = norm(l.get("nombre", ""))
            id_l = norm(l.get("id", "")).replace("-", " ")
            if (nom_l and nom_l in q_escena) or (id_l and id_l in q_escena):
                coincidencias.append((len(nom_l or id_l), l))
        if coincidencias:
            coincidencias.sort(key=lambda x: x[0], reverse=True)
            elegido = coincidencias[0][1]
            if mundo.get("actual") != elegido["id"]:
                ir_a(datos, elegido["nombre"])
                hechos.append((
                    {"tipo": "mundo", "accion": "aqui", "id": elegido["id"], "nombre": elegido["nombre"]},
                    f"Ahora están en: {elegido['nombre']}",
                ))

    if not escena.get("mapa"):
        nombre_mapa = escena.get("lugar") or escena.get("titulo") or "Zona"
        del_catalogo = _buscar_catalogo_por_texto(texto_escena)
        if del_catalogo is not None:
            _, info = cargar_mapa_catalogo(datos, del_catalogo["id"], slug=slug, nombre=nombre_mapa)
            hechos.append((
                {"tipo": "mapa", "accion": "cargar", **info},
                f"Mapa de zona cargado ({info['id']}, {info['columnas']}×{info['filas']} casillas).",
            ))
        else:
            tipo = _inferir_tipo_zona(texto_escena)
            luz = "penumbra" if "noche" in norm(escena.get("hora", "")) else "brillante"
            semilla = f"{slug or datos.get('slug', 'mesa')}-{escena.get('numero', 1)}-{nombre_mapa}"
            mapa = generar_zona(tipo, semilla=semilla, nombre=nombre_mapa, luz=luz)
            escena["mapa"] = mapa
            filas = mapa["filas"]
            hechos.append((
                {"tipo": "mapa", "accion": "generar", "generador": tipo, "semilla": semilla,
                 "nombre": nombre_mapa, "columnas": len(filas[0]), "filas": len(filas), "luz": luz},
                f"Mapa de zona generado ({tipo}, {len(filas[0])}×{len(filas)} casillas).",
            ))

    reubicar(datos)
    mapa = escena.get("mapa")
    if mapa:
        posiciones = escena.setdefault("posiciones", [])
        ocupadas = {p["celda"] for p in posiciones if p.get("celda")}
        libres = _celdas_transitables(mapa, ocupadas)
        for pj in datos.get("personajes", []):
            nombres_pj = {norm(pj.get("nombre", "")), norm(pj.get("id", ""))} - {""}
            pos = next((x for x in posiciones if norm(x.get("quien", "")) in nombres_pj), None)
            if pos is None:
                pos = {"quien": pj["nombre"], "donde": escena.get("lugar") or escena.get("titulo") or "En escena"}
                posiciones.append(pos)
            if not pos.get("celda") and libres:
                celda = libres.pop(0)
                pos["celda"] = celda
                hechos.append((
                    {"tipo": "posicion", "quien": pos["quien"], "donde": pos["donde"], "celda": celda},
                    f"{pos['quien']}: {pos['donde']} [{celda}]",
                ))
    return hechos

"""La zona en cuadrícula: terreno, visión, movimiento, luz y áreas.

Es lo que el narrador dibuja en texto, una fila por línea, con un carácter
por terreno y su leyenda. Cada casilla mide `celda` metros (1,5 por defecto,
la casilla de 5 pies de D&D); el espacio es «fuera del mapa» y los dígitos
quedan para las fichas. Las distancias cuentan casillas como en D&D 2024:
la diagonal vale una.

Las reglas de visión, cobertura, movimiento e iluminación salen de
`srd-2024_combat_cover`, `srd-2024_combat_movement-and-position` y
`srd-2024_exploration_vision-and-light`; son la única fuente de verdad y
el visor pinta lo que aquí se calcula.
"""

from __future__ import annotations

import heapq
import math
import re
from ..texto import norm

from .base import (
    BONO_COBERTURA,
    CELDA,
    COBERTURAS,
    COLUMNAS,
    FORMAS_AREA,
    LEYENDA_BASE,
    LUCES,
    MAX_FILAS,
    RUMBOS,
    _CELDA_RE,
    _ETIQUETAS_LEYENDA_RE,
    coordenada,
    distancia_casillas,
    metros,
    nombre_celda,
    validar_celda,
)


def leer_dibujo(dibujo: str) -> list[str]:
    """Texto del narrador → filas del mismo ancho (rellenas con espacio = fuera del mapa)."""
    lineas = str(dibujo or "").replace("\\n", "\n").replace("\t", "    ").split("\n")
    lineas = [l.rstrip() for l in lineas]
    while lineas and not lineas[0].strip():
        lineas.pop(0)
    while lineas and not lineas[-1].strip():
        lineas.pop()
    if not lineas:
        raise ValueError("el dibujo del mapa está vacío: una fila por línea, p. ej. «#####\\n#...#\\n#####»")
    ancho = max(len(l) for l in lineas)
    if ancho > len(COLUMNAS):
        raise ValueError(f"el mapa tiene {ancho} columnas; el máximo es {len(COLUMNAS)} (A–Z): agranda la casilla con --celda")
    if len(lineas) > MAX_FILAS:
        raise ValueError(f"el mapa tiene {len(lineas)} filas; el máximo es {MAX_FILAS}")
    return [l.ljust(ancho) for l in lineas]


def _parsear_etiquetas_terreno(texto: str) -> dict:
    """Extrae etiquetas semánticas entre corchetes, p. ej. «dificil, cobertura=media»."""
    prop: dict = {}
    for parte in (p.strip() for p in texto.split(",") if p.strip()):
        k, sep, v = parte.partition("=")
        clave, valor = norm(k), norm(v)
        if not sep:
            if clave in ("dificil", "terreno dificil"):
                prop["dificil"] = True
            elif clave in ("normal", "llano"):
                prop["dificil"] = False
            elif clave in ("bloquea", "muro", "solido"):
                prop["bloquea_paso"] = True
                prop["bloquea_vision"] = True
                prop["cobertura"] = "total"
            elif clave in ("bloquea-paso", "bloquea paso", "impasable"):
                prop["bloquea_paso"] = True
            elif clave in ("paso-libre", "paso libre"):
                prop["bloquea_paso"] = False
            elif clave in ("bloquea-vision", "bloquea vision", "opaco"):
                prop["bloquea_vision"] = True
            elif clave in ("vision-libre", "vision libre", "transparente"):
                prop["bloquea_vision"] = False
            elif clave in ("media", "tres-cuartos", "3/4", "total", "ninguna"):
                prop["cobertura"] = "tres-cuartos" if clave == "3/4" else clave
            else:
                raise ValueError(f"etiqueta de terreno desconocida: {parte!r}")
        elif clave in ("cobertura", "cob"):
            cob = "tres-cuartos" if valor in ("3/4", "tres cuartos", "tres-cuartos") else valor
            if cob not in COBERTURAS:
                raise ValueError(f"cobertura inválida {v!r} (usa: {', '.join(COBERTURAS)})")
            prop["cobertura"] = cob
        elif clave in ("dificil", "bloquea_paso", "bloquea-paso", "bloquea_vision", "bloquea-vision"):
            campo = clave.replace("-", "_")
            if valor not in ("si", "true", "1", "no", "false", "0"):
                raise ValueError(f"valor booleano inválido en {parte!r}")
            prop[campo] = valor in ("si", "true", "1")
        else:
            raise ValueError(f"propiedad de terreno desconocida: {parte!r}")
    return prop


def leer_leyenda(items: list[str] | None) -> tuple[dict[str, str], dict[str, dict]]:
    leyenda: dict[str, str] = {}
    terrenos: dict[str, dict] = {}
    for item in items or []:
        if len(item) >= 3 and item[1] == "=":
            caracter, signo, significado = item[0], "=", item[2:]
        else:
            caracter, signo, significado = item.partition("=")
        if not signo or len(caracter) != 1 or not significado.strip():
            raise ValueError(f"leyenda inválida {item!r}: usa «c=significado», p. ej. «T=mesa»")
        limpio = significado.strip()
        m = _ETIQUETAS_LEYENDA_RE.match(limpio)
        if m and m.group(1).strip():
            limpio = m.group(1).strip()
            terrenos[caracter] = _parsear_etiquetas_terreno(m.group(2))
        leyenda[caracter] = limpio
    return leyenda, terrenos


def inferir_terreno(caracter: str, significado: str) -> dict:
    """Semántica base por carácter y descripción, contrastada con el SRD 5.2.1."""
    s = norm(significado or "")
    if caracter == "#" or re.search(r"\b(muro|pared|roca|pena|acantilado)\b", s):
        return {"bloquea_paso": True, "bloquea_vision": True, "cobertura": "total", "dificil": False}
    if caracter == "+" or re.search(r"\b(puerta|porton|trampilla)\b", s):
        abierta = caracter == "/" or "abiert" in s
        return {
            "bloquea_paso": not abierta,
            "bloquea_vision": not abierta,
            "cobertura": "ninguna" if abierta else "total",
            "dificil": False,
        }
    if re.search(r"\b(pilar|columna)\b", s):
        return {"bloquea_paso": True, "bloquea_vision": False, "cobertura": "tres-cuartos", "dificil": False}
    if caracter == "=" or re.search(r"\b(ventana|reja|aspillera)\b", s):
        return {"bloquea_paso": True, "bloquea_vision": False, "cobertura": "tres-cuartos", "dificil": False}
    if re.search(r"\b(baranda|barandilla|mostrador|barra)\b", s):
        return {"bloquea_paso": True, "bloquea_vision": False, "cobertura": "media", "dificil": False}
    if re.search(r"\b(abismo|vacio|hoyo|pozo|precipicio|grieta)\b", s):
        return {"bloquea_paso": True, "bloquea_vision": False, "cobertura": "ninguna", "dificil": False}
    if re.search(r"\b(niebla|humo|cortina)\b", s) or "follaje denso" in s:
        return {"bloquea_paso": False, "bloquea_vision": True, "cobertura": "ninguna", "dificil": False}
    if re.search(r"\b(arbol|tronco)\b", s):
        return {"bloquea_paso": False, "bloquea_vision": False, "cobertura": "tres-cuartos", "dificil": True}
    if re.search(r"\b(mesa|silla|mueble|barril|caja|cama|estante|carro|banco|baul|cofre|altar|arbusto|seto|maleza|parapeto|trinchera)\b", s):
        return {"bloquea_paso": False, "bloquea_vision": False, "cobertura": "media", "dificil": True}
    if caracter in ("~", "^") or re.search(r"\b(agua|rio|lago|mar|charco|pantano|canal|barro|lodo|nieve|hielo|escombro|escalera|rampa|desnivel|escalon|fuego|hoguera|lava|brasa)\b", s):
        return {"bloquea_paso": "lava" in s, "bloquea_vision": False, "cobertura": "ninguna", "dificil": True}
    return {"bloquea_paso": False, "bloquea_vision": False, "cobertura": "ninguna", "dificil": False}


def semantica_terreno(mapa: dict, caracter: str) -> dict:
    """Propiedades efectivas de un carácter en el mapa (inferidas + sobrecargas explícitas)."""
    if caracter == " ":
        return {"bloquea_paso": True, "bloquea_vision": True, "cobertura": "total", "dificil": False}
    significado = (mapa.get("leyenda") or {}).get(caracter, LEYENDA_BASE.get(caracter, ""))
    base = inferir_terreno(caracter, significado)
    extra = (mapa.get("terrenos") or {}).get(caracter) or {}
    res = {**base, **{k: v for k, v in extra.items() if k in base and v is not None}}
    if res.get("cobertura") == "total":
        res["bloquea_vision"] = extra.get("bloquea_vision", True)
    return res


def terrenos_mapa(mapa: dict) -> dict[str, dict]:
    return {c: semantica_terreno(mapa, c) for c in (mapa.get("leyenda") or {})}


def _semanticas(mapa: dict) -> dict[str, dict]:
    """Semántica efectiva de cada carácter del mapa, inferida una sola vez.

    `semantica_terreno` es pura respecto de la leyenda y de las sobrecargas, pero
    inferirla cuesta normalizar el texto y recorrer sus reglas: en una rejilla de
    26×40 hay hasta 1.040 casillas y cada línea de visión, cada casilla de un área
    o cada nodo del A* la volvía a pedir. Aquí se calcula una vez por operación y
    se reutiliza; el resultado es el mismo carácter a carácter.
    """
    caracteres = set("".join(mapa.get("filas") or []))
    for c in mapa.get("leyenda") or {}:
        caracteres.add(c)
    for c in mapa.get("terrenos") or {}:
        caracteres.add(c)
    return {c: semantica_terreno(mapa, c) for c in caracteres}


def _resumen_terreno(sem: dict) -> str:
    partes = []
    if sem.get("bloquea_paso") and sem.get("bloquea_vision") and sem.get("cobertura") == "total":
        return "bloquea"
    if sem.get("bloquea_paso"):
        partes.append("impasable")
    if sem.get("bloquea_vision"):
        partes.append("opaco")
    if sem.get("dificil") and not sem.get("bloquea_paso"):
        partes.append("difícil")
    cob = sem.get("cobertura", "ninguna")
    if cob != "ninguna":
        etiqueta = {"media": "cob. media +2", "tres-cuartos": "cob. 3/4 +5", "total": "cob. total"}[cob]
        partes.append(etiqueta)
    return ", ".join(partes)


def nueva_zona(dibujo: str, leyenda: list[str] | dict | None = None, celda: float | None = None,
               nombre: str | None = None, anterior: dict | None = None, luz: str | None = None) -> dict:
    """Valida el dibujo y devuelve el mapa de zona listo para `escena.mapa`."""
    filas = leer_dibujo(dibujo)
    if isinstance(leyenda, dict):
        propia, terrenos_propios = dict(leyenda), {}
    else:
        propia, terrenos_propios = leer_leyenda(leyenda)
    usados = sorted({c for fila in filas for c in fila} - {" "})
    digitos = [c for c in usados if c.isdigit()]
    if digitos:
        raise ValueError(f"los dígitos ({''.join(digitos)}) quedan para las fichas: usa otro carácter en el dibujo")
    base = {**LEYENDA_BASE, **((anterior or {}).get("leyenda") or {}), **propia}
    faltan = [c for c in usados if c not in base]
    if faltan:
        raise ValueError(
            f"falta la leyenda de {', '.join(repr(c) for c in faltan)}: añade --leyenda 'c=significado' "
            f"(ya conocidos: {', '.join(f'{k} {v}' for k, v in LEYENDA_BASE.items())})"
        )
    tamano = float(celda if celda is not None else (anterior or {}).get("celda", CELDA))
    if not 0 < tamano <= 1000:
        raise ValueError("la casilla mide entre 0 y 1000 metros")
    mapa: dict = {"celda": tamano, "filas": filas, "leyenda": {c: base[c] for c in usados}}
    if nombre:
        mapa["nombre"] = nombre
    elif (anterior or {}).get("nombre"):
        mapa["nombre"] = anterior["nombre"]
    terrenos_ant = {c: dict(v) for c, v in ((anterior or {}).get("terrenos") or {}).items() if c in usados}
    for c, t in terrenos_propios.items():
        if c in usados:
            terrenos_ant[c] = {**terrenos_ant.get(c, {}), **t}
    if terrenos_ant:
        mapa["terrenos"] = terrenos_ant
    luz_ef = norm(luz) if luz else (anterior or {}).get("luz")
    if luz_ef:
        if luz_ef not in LUCES:
            raise ValueError(f"luz inválida {luz!r}: usa {', '.join(LUCES)}")
        mapa["luz"] = luz_ef
    if (anterior or {}).get("luces"):
        luces_validas = []
        for f in anterior["luces"]:
            try:
                f_copia = dict(f, celda=validar_celda(mapa, f["celda"]))
                luces_validas.append(f_copia)
            except ValueError:
                pass
        if luces_validas:
            mapa["luces"] = luces_validas
    return mapa


def poner_terreno(mapa: dict, caracter: str, *, cobertura: str | None = None, dificil: bool | None = None,
                  bloquea_paso: bool | None = None, bloquea_vision: bool | None = None) -> dict:
    """Ajusta las propiedades mecánicas de un carácter de la leyenda en el mapa activo."""
    if not mapa or not mapa.get("filas"):
        raise ValueError("no hay mapa de zona activo")
    c = str(caracter or "")
    if len(c) != 1 or c not in (mapa.get("leyenda") or {}):
        conocidos = ", ".join(sorted(mapa.get("leyenda") or {}))
        raise ValueError(f"el carácter {caracter!r} no está en la leyenda del mapa (hay: {conocidos})")
    terrenos = mapa.setdefault("terrenos", {})
    actual = dict(terrenos.get(c) or {})
    if cobertura is not None:
        cob = "tres-cuartos" if norm(cobertura) in ("3/4", "tres cuartos", "tres-cuartos") else norm(cobertura)
        if cob not in COBERTURAS:
            raise ValueError(f"cobertura inválida {cobertura!r} (usa: {', '.join(COBERTURAS)})")
        actual["cobertura"] = cob
    if dificil is not None:
        actual["dificil"] = bool(dificil)
    if bloquea_paso is not None:
        actual["bloquea_paso"] = bool(bloquea_paso)
    if bloquea_vision is not None:
        actual["bloquea_vision"] = bool(bloquea_vision)
    terrenos[c] = actual
    return semantica_terreno(mapa, c)


def _parsear_foco(mapa: dict, espec: str) -> dict:
    """«G4:6:6:farol» → {celda, brillante, penumbra, nombre}."""
    partes = [p.strip() for p in str(espec or "").split(":")]
    if len(partes) < 2 or not partes[0]:
        raise ValueError(f"foco inválido {espec!r}: usa «CELDA:BRILLANTE_M[:PENUMBRA_M[:NOMBRE]]», p. ej. «G4:6:6:farol»")
    celda = validar_celda(mapa, partes[0])
    try:
        brillante = float(partes[1].replace(",", "."))
        penumbra = float(partes[2].replace(",", ".")) if len(partes) >= 3 and partes[2] else brillante
    except ValueError:
        raise ValueError(f"radios de luz inválidos en {espec!r}: deben ser metros numéricos") from None
    if brillante < 0 or penumbra < 0 or (brillante == 0 and penumbra == 0):
        raise ValueError("el foco de luz necesita un radio positivo en metros")
    foco = {"celda": celda, "brillante": brillante, "penumbra": penumbra}
    if len(partes) >= 4 and partes[3]:
        foco["nombre"] = ":".join(partes[3:]).strip()
    return foco


def poner_luz(mapa: dict, luz: str | None = None, focos: list[str] | None = None, limpiar_focos: bool = False) -> dict:
    """Configura la luz ambiental de la zona (`brillante|penumbra|oscuridad`) y sus focos puntuales."""
    if not mapa or not mapa.get("filas"):
        raise ValueError("no hay mapa de zona activo")
    if luz is not None:
        nivel = norm(luz)
        if nivel not in LUCES:
            raise ValueError(f"luz inválida {luz!r} (usa: {', '.join(LUCES)})")
        mapa["luz"] = nivel
    if limpiar_focos:
        mapa.pop("luces", None)
    for f in focos or []:
        nuevo = _parsear_foco(mapa, f)
        lista = mapa.setdefault("luces", [])
        lista[:] = [x for x in lista if x.get("celda") != nuevo["celda"]]
        lista.append(nuevo)
    return {"luz": mapa.get("luz", "brillante"), "luces": list(mapa.get("luces") or [])}


def _clase(datos: dict, quien: str) -> str:
    clave = norm(quien)
    for p in datos.get("personajes", []):
        if clave in {norm(p.get("nombre", "")), norm(p.get("id", ""))}:
            return "personaje"
    for e in datos.get("enemigos", []):
        if clave == norm(e.get("nombre", "")):
            return "amenaza"
    return "otro"


def fichas(datos: dict) -> list[dict]:
    """Las posiciones con casilla, numeradas: personajes primero, luego amenazas y el resto."""
    posiciones = (datos.get("escena") or {}).get("posiciones") or []
    con_celda = [dict(p, clase=_clase(datos, p["quien"])) for p in posiciones if p.get("celda")]
    orden = {"personaje": 0, "amenaza": 1, "otro": 2}
    con_celda.sort(key=lambda p: orden[p["clase"]])
    for i, p in enumerate(con_celda, start=1):
        p["marca"] = str(i) if i <= 9 else "*"
    return con_celda


def resolver_punto(datos: dict | None, mapa: dict, ref: str) -> tuple[str, str | None]:
    """Acepta una casilla («F4») o el nombre de una ficha («Cris») y devuelve (celda, nombre_ficha)."""
    texto = str(ref or "").strip()
    if not texto:
        raise ValueError("falta indicar la casilla o el personaje")
    if _CELDA_RE.match(texto):
        celda = validar_celda(mapa, texto)
        ocupante = next((f["quien"] for f in fichas(datos or {}) if f["celda"] == celda), None)
        return celda, ocupante
    clave = norm(texto)
    lista = fichas(datos or {})
    exactos = [f for f in lista if clave == norm(f["quien"])]
    if len(exactos) == 1:
        return validar_celda(mapa, exactos[0]["celda"]), exactos[0]["quien"]
    prefijos = [f for f in lista if norm(f["quien"]).startswith(clave)]
    if len(prefijos) == 1:
        return validar_celda(mapa, prefijos[0]["celda"]), prefijos[0]["quien"]
    if prefijos:
        raise ValueError(f"{ref!r} es ambiguo en el mapa: {', '.join(f['quien'] for f in prefijos)}")
    raise ValueError(f"no hay casilla ni ficha {ref!r} en el mapa de zona")


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


_FUEGO_RE = re.compile(r"\b(fuego|hoguera|antorcha|farol|linterna|brasa|chimenea|lava)\b")


def _caracteres_de_fuego(mapa: dict) -> set[str]:
    """Caracteres cuya leyenda describe una fuente de luz.

    Antes se normalizaba y se comparaba la leyenda *de cada casilla* para decidir
    si era un foco; en una rejilla de 26x40 (1.040 casillas) eso son 1.040
    normalizaciones de texto y 1.040 expresiones regulares por cada cálculo de
    iluminación. Un foco se decide por carácter, no por casilla, así que basta
    mirar los caracteres que de verdad aparecen en el dibujo.
    """
    leyenda = mapa.get("leyenda") or {}
    return {c for c in set("".join(mapa.get("filas") or [])) if _FUEGO_RE.search(norm(leyenda.get(c, "")))}


def _focos_efectivos(mapa: dict, fuegos: set[str] | None = None) -> list[dict]:
    focos = [dict(f) for f in (mapa.get("luces") or [])]
    Conocidas = {f["celda"] for f in focos}
    if fuegos is None:
        fuegos = _caracteres_de_fuego(mapa)
    if not fuegos:
        return focos
    leyenda = mapa.get("leyenda") or {}
    for fi, fila in enumerate(mapa.get("filas") or []):
        for co, ch in enumerate(fila):
            if ch not in fuegos:
                continue
            celda = nombre_celda(co, fi)
            if celda in Conocidas:
                continue
            focos.append({"celda": celda, "brillante": 6.0, "penumbra": 6.0, "nombre": leyenda.get(ch, "luz")})
    return focos


def iluminacion_celda(mapa: dict, celda: str, focos: list[dict] | None = None) -> str:
    """Nivel de luz en una casilla (`brillante|penumbra|oscuridad`) según ambiente y focos con visión.

    `focos` es para quien ilumina todo el mapa de una vez: sin él, cada llamada
    vuelve a recorrer el dibujo para reencontrar los focos.
    """
    c_norm = validar_celda(mapa, celda)
    base = mapa.get("luz", "brillante")
    if base not in LUCES:
        base = "brillante"
    indice = LUCES.index(base)
    if indice == 2:
        return "brillante"
    celda_m = float(mapa.get("celda", CELDA))
    for foco in (_focos_efectivos(mapa) if focos is None else focos):
        f_celda = foco["celda"]
        dist_m = distancia_casillas(f_celda, c_norm) * celda_m
        r_brill = float(foco.get("brillante", 0))
        r_pen = float(foco.get("penumbra", 0))
        if dist_m > r_brill + r_pen + 1e-6:
            continue
        if f_celda != c_norm and not linea_entre(mapa, f_celda, c_norm)["visible"]:
            continue
        if dist_m <= r_brill + 1e-6:
            return "brillante"
        indice = max(indice, 1)
    return LUCES[indice]


def mapa_iluminacion(mapa: dict) -> dict[str, str]:
    """Diccionario `{celda: nivel_luz}` para todas las casillas del mapa."""
    res: dict[str, str] = {}
    filas = mapa.get("filas") or []
    base = mapa.get("luz", "brillante")
    if base not in LUCES or LUCES.index(base) == 2:
        # Con luz ambiente brillante no hace falta ni buscar los focos: todo está iluminado.
        for fi, fila in enumerate(filas):
            for co, ch in enumerate(fila):
                if ch != " ":
                    res[nombre_celda(co, fi)] = "brillante"
        return res
    focos = _focos_efectivos(mapa)
    for fi, fila in enumerate(filas):
        for co, ch in enumerate(fila):
            if ch != " ":
                c = nombre_celda(co, fi)
                res[c] = iluminacion_celda(mapa, c, focos)
    return res


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


def reubicar(datos: dict) -> list[str]:
    """Tras redibujar: quita la casilla a quien quedó fuera; devuelve sus nombres."""
    mapa = (datos.get("escena") or {}).get("mapa")
    perdidos = []
    for p in (datos.get("escena") or {}).get("posiciones") or []:
        if not p.get("celda"):
            continue
        try:
            if mapa is None:
                raise ValueError
            p["celda"] = validar_celda(mapa, p["celda"])
        except ValueError:
            p.pop("celda", None)
            perdidos.append(p["quien"])
    return perdidos


def zona_texto(datos: dict) -> str:
    """El mapa de zona tal como lo ve el narrador: cuadrícula, leyenda, fichas y distancias."""
    escena = datos.get("escena") or {}
    mapa = escena.get("mapa")
    if not mapa:
        return ""
    filas = mapa["filas"]
    ancho = len(filas[0])
    rejilla = [list(f) for f in filas]
    lista = fichas(datos)
    for f in lista:
        col, fila = coordenada(f["celda"])
        if fila < len(rejilla) and col < ancho:
            rejilla[fila][col] = f["marca"]
    nombre = mapa.get("nombre") or escena.get("lugar") or "la zona"
    luz_amb = mapa.get("luz")
    extra_luz = f"; luz: {luz_amb}" if luz_amb else ""
    lineas = [
        f"Mapa de la zona: {nombre} (casilla de {metros(mapa['celda'])}; columnas A–{COLUMNAS[ancho - 1]}, filas 1–{len(filas)}{extra_luz})",
        "     " + " ".join(COLUMNAS[:ancho]),
    ]
    lineas += [f"  {i + 1:>2} " + " ".join(fila).rstrip() for i, fila in enumerate(rejilla)]
    lineas.append("Leyenda: " + " · ".join(f"{c} {s}" for c, s in mapa["leyenda"].items()))
    sem_items = []
    for c in mapa["leyenda"]:
        res_sem = _resumen_terreno(semantica_terreno(mapa, c))
        if res_sem:
            sem_items.append(f"{c} [{res_sem}]")
    if sem_items:
        lineas.append("Terreno: " + " · ".join(sem_items))
    focos = _focos_efectivos(mapa)
    if focos:
        lineas.append(
            "Luces: "
            + " · ".join(
                f"{x['celda']} ({x.get('nombre', 'foco')}: {metros(x['brillante'])} brillante + {metros(x['penumbra'])} penumbra)"
                for x in focos
            )
        )
    if lista:
        etiqueta = {"personaje": "", "amenaza": ", amenaza", "otro": ""}
        lineas.append("Fichas: " + " · ".join(f"{f['marca']} {f['quien']} ({f['celda']}{etiqueta[f['clase']]})" for f in lista))
        juntas = {}
        for f in lista:
            juntas.setdefault(f["celda"], []).append(f["quien"])
        for celda, quienes in juntas.items():
            if len(quienes) > 1:
                lineas.append(f"Comparten {celda}: {', '.join(quienes)}")
        for f in [x for x in lista if x["clase"] == "personaje"]:
            otros = [x for x in lista if x is not f]
            if otros:
                lineas.append(
                    f"Desde {f['quien']}: "
                    + " · ".join(f"{o['quien']} {metros(distancia_casillas(f['celda'], o['celda']) * mapa['celda'])}" for o in otros)
                )
                detalles_tacticos = []
                for o in otros:
                    lin = linea_entre(mapa, f["celda"], o["celda"], datos=datos)
                    cam = camino_movimiento(mapa, f["celda"], o["celda"])
                    partes_o = []
                    if not lin["visible"]:
                        partes_o.append("sin visión")
                    elif lin["cobertura"] != "ninguna":
                        bono = lin["bono_cobertura"]
                        partes_o.append(f"cob. {lin['cobertura']}" + (f" +{bono}" if bono else ""))
                    if cam["alcanzable"] and cam["casillas_coste"] != lin["distancia_casillas"]:
                        partes_o.append(f"camino {metros(cam['metros_coste'])}")
                    elif not cam["alcanzable"]:
                        partes_o.append("paso bloqueado")
                    if partes_o:
                        detalles_tacticos.append(f"{o['quien']} ({', '.join(partes_o)})")
                if detalles_tacticos:
                    lineas.append(f"Táctica desde {f['quien']}: " + " · ".join(detalles_tacticos))
    sin = [p for p in escena.get("posiciones") or [] if not p.get("celda")]
    if sin:
        lineas.append("Sin casilla: " + " · ".join(f"{p['quien']} («{p.get('donde', '')}»)" for p in sin))
    return "\n".join(lineas)


# ---------- proyección para el visor ----------

# Cómo se pinta cada terreno en el visor. Vive aquí, junto a las reglas, para que el
# navegador no tenga su propia lista: si el narrador escribe «estalagmita de calcita»,
# el motor decide a la vez cómo se comporta y cómo se ve.
_CLASES_POR_CARACTER = {"#": "solido", "+": "puerta", "=": "ventana", "~": "agua", "^": "escalera"}
_CLASES_POR_PALABRA = (
    (re.compile(r"\b(muro|pared|roca|pena|acantilado)\b"), "solido"),
    (re.compile(r"\b(puerta|porton|trampilla)\b"), "puerta"),
    (re.compile(r"\b(ventana|reja|aspillera|parapeto|baranda|barandilla)\b"), "ventana"),
    (re.compile(r"\b(arbol|bosque|arbusto|hierba|seto|vegetacion|maleza|jardin|tronco|estalagmita)\b"), "planta"),
    (re.compile(r"\b(mesa|silla|mueble|barril|caja|cama|estante|mostrador|carro|banco|baul|cofre|altar|barra|puesto|fuente)\b"), "mueble"),
    (re.compile(r"\b(escalera|rampa|desnivel|escalon)\b"), "escalera"),
    (re.compile(r"\b(abismo|vacio|hoyo|pozo|precipicio|grieta)\b"), "vacio"),
    (re.compile(r"\b(fuego|hoguera|lava|brasa|chimenea|antorcha|farol)\b"), "fuego"),
    (re.compile(r"\b(suelo|piso|camino|calle|tierra|arena|empedrado|muelle|madera|plaza|pasillo|orilla)\b"), "suelo"),
)


def clase_pintado(caracter: str, significado: str = "") -> str:
    """La clase CSS con la que el visor pinta un terreno (`t-solido`, `t-agua`…)."""
    if caracter in _CLASES_POR_CARACTER:
        return _CLASES_POR_CARACTER[caracter]
    s = norm(significado or "")
    for patron, clase in _CLASES_POR_PALABRA:
        if patron.search(s):
            return clase
    return "otro"


def proyeccion_zona(datos: dict, *, origen: str | None = None, destino: str | None = None,
                    forma: str | None = None, tamano: float | None = None) -> dict:
    """Todo lo que el visor necesita para pintar la zona, resuelto por el motor.

    El navegador no vuelve a decidir qué es un muro, dónde llega la luz ni cuánto
    cuesta un paso: solo pinta lo que sale aquí. Sin zona activa devuelve las
    listas vacías, que es lo que el visor muestra cuando todavía no hay mapa.

    `origen` y `destino` son la medición que el jugador tiene seleccionada en
    pantalla (no estado de la partida), así que llegan en la consulta.
    """
    escena = datos.get("escena") or {}
    mapa = escena.get("mapa")
    lista_fichas = fichas(datos)
    vacio: dict = {
        "hay_mapa": False, "luz_base": "brillante", "focos": [], "terrenos": [],
        "luz": [], "celda": CELDA, "fichas": [], "origen": None,
        "linea": None, "camino": None, "area": None,
    }
    if not mapa or not (mapa.get("filas") or []):
        return vacio

    semanticas = _semanticas(mapa)
    luz_por_celda = mapa_iluminacion(mapa)
    luz_base = mapa.get("luz") if mapa.get("luz") in LUCES else "brillante"
    focos = [{"celda": f["celda"], "nombre": f.get("nombre", "foco"),
              "brillante": float(f.get("brillante", 0) or 0),
              "penumbra": float(f.get("penumbra", 0) or 0)}
             for f in _focos_efectivos(mapa)]

    # Un registro por carácter del dibujo, no por casilla: en una mazmorra de 26x40
    # son unas seis entradas en lugar de más de mil.
    usados = [c for c in dict.fromkeys("".join(mapa["filas"])) if c != " "]
    terrenos = []
    for c in usados:
        sem = semanticas[c]
        terrenos.append({
            "caracter": c,
            "significado": (mapa.get("leyenda") or {}).get(c, "?"),
            "clase": clase_pintado(c, (mapa.get("leyenda") or {}).get(c, "")),
            "bloquea_paso": bool(sem["bloquea_paso"]),
            "bloquea_vision": bool(sem["bloquea_vision"]),
            "cobertura": sem["cobertura"],
            "dificil": bool(sem["dificil"]),
            "resumen": _resumen_terreno(sem),
        })

    # La luz solo viaja donde no es la del ambiente: en una zona a plena luz no
    # hay ni una entrada que enviar.
    luz = [{"celda": c, "nivel": n} for c, n in luz_por_celda.items() if n != luz_base]

    color_por_quien = {}
    for p in datos.get("personajes", []):
        color_por_quien[norm(p.get("nombre", ""))] = p.get("color")
        color_por_quien[norm(p.get("id", ""))] = p.get("color")
    fichas_pintura = [dict(f, color=color_por_quien.get(norm(f["quien"]))) for f in lista_fichas]

    salida = {
        "hay_mapa": True,
        "luz_base": luz_base,
        "focos": focos,
        "terrenos": terrenos,
        "luz": luz,
        "fichas": fichas_pintura,
        "celda": float(mapa.get("celda", CELDA)),
        "linea": None,
        "camino": None,
        "area": None,
    }
    if not origen:
        return salida
    try:
        c_orig, quien_orig = resolver_punto(datos, mapa, origen)
    except ValueError:
        return salida

    # La distancia desde la casilla de origen la muestra la leyenda de fichas, así que
    # viaja con ellas aunque el jugador todavía no haya elegido destino.
    celda_m = salida["celda"]
    for f in fichas_pintura:
        try:
            f["distancia_casillas"] = distancia_casillas(c_orig, f["celda"])
            f["distancia_m"] = round(f["distancia_casillas"] * celda_m, 2)
        except (TypeError, ValueError):
            f["distancia_casillas"] = None
            f["distancia_m"] = None

    if not destino:
        salida["origen"] = {"celda": c_orig, "quien": quien_orig}
        return salida
    try:
        c_dest, _ = resolver_punto(datos, mapa, destino)
    except ValueError:
        salida["origen"] = {"celda": c_orig, "quien": quien_orig}
        return salida
    salida["origen"] = {"celda": c_orig, "quien": quien_orig}

    lin = linea_entre(mapa, c_orig, c_dest, datos, semanticas)
    salida["linea"] = {
        "origen": c_orig, "destino": c_dest, "quien_origen": quien_orig,
        "visible": lin["visible"], "cobertura": lin["cobertura"],
        "bono": lin["bono_cobertura"],
        "distancia_casillas": lin["distancia_casillas"],
        # El visor solo necesita saber qué casillas son obstáculo, no el motivo. Una
        # esquina («B3/A4») son dos casillas: se parten para poder marcarlas.
        "obstaculos": sorted({c for o in lin["obstaculos"] for c in o["celda"].split("/")}),
    }
    cam = camino_movimiento(mapa, c_orig, c_dest)
    salida["camino"] = {
        "alcanzable": cam["alcanzable"], "casillas_coste": cam["casillas_coste"],
        "metros_coste": cam["metros_coste"], "camino": cam["camino"],
    }
    tipo = norm(forma or "")
    if tipo and tipo != "ninguna" and tipo in FORMAS_AREA and tamano:
        res = area_efecto(mapa, tipo, float(tamano), c_orig, c_dest, None, datos)
        salida["area"] = {
            "forma": res["forma"], "casillas": res["casillas"],
            "sombra": res["bloqueadas"], "fichas": res["fichas"],
        }
    return salida

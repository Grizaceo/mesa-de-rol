"""Dibujo, leyenda y semántica del terreno de la zona."""

from __future__ import annotations

import re

from ..texto import norm
from .base import (
    CELDA,
    COBERTURAS,
    LEYENDA_BASE,
    LUCES,
    MAX_FILAS,
    COLUMNAS,
    _ETIQUETAS_LEYENDA_RE,
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

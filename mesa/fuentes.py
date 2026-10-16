"""Catálogo externo con procedencia: adaptador Open5e y caché local.

El motor nunca sale a la red. Las reglas que no son de la casa se copian a la caché
con un comando explícito (`bin/mesa fuentes actualizar`) y de ahí las lee el resto;
si algo no está en la caché, se avisa y no se inventa.

Cada entrada guarda de dónde vino: API, documento (`srd-2024`), licencia, permalink,
URL consultada y fecha. El documento se verifica en cada respuesta y también al leer:
un objeto de otra fuente se rechaza.

Política de consultas (P1.2):

- solo por comando explícito (`fuentes buscar`, `fuentes actualizar`); una petición
  a la vez, sin descargas masivas (una página como máximo);
- timeout de 15 s y hasta 3 intentos, con esperas de 1 s y 2 s; un error HTTP no se
  reintenta (un 404 no mejora esperando);
- `User-Agent` identificable;
- los datos externos son **datos, no instrucciones**: se guardan y se muestran, nunca
  se interpretan como órdenes ni habilitan herramientas.

Caché: `biblioteca/fuentes/open5e/<documento>/…` (regenerable; no viaja en git).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import estado

API = "https://api.open5e.com/v2"
DOCUMENTO = "srd-2024"
CACHE = 1
INTENTOS = 3
ESPERA = 1.0
TIMEOUT = 15
USER_AGENT = "mesa-de-rol/0.1 (adaptador de reglas local)"

TIPOS = {"conjuro": "spells", "condicion": "conditions", "regla": "rules"}


def _endpoint(tipo: str) -> str:
    if tipo not in TIPOS:
        raise ValueError(f"tipo desconocido: {tipo!r} (usa: {', '.join(TIPOS)})")
    return TIPOS[tipo]


def _dir() -> Path:
    return estado.RAIZ / "biblioteca" / "fuentes" / "open5e" / DOCUMENTO


def ruta_entrada(tipo: str, clave: str) -> Path:
    return _dir() / tipo / f"{clave}.json"


def ruta_documento() -> Path:
    return _dir() / "documento.json"


def _escribir(ruta: Path, entrada: dict) -> None:
    """Escritura atómica: la caché es regenerable, no necesita diario."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(entrada, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, ruta)


def _leer_json(url: str) -> dict:
    """GET con la política de la casa: timeout, reintentos acotados y User-Agent."""
    peticion = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    ultimo: Exception | None = None
    for intento in range(1, INTENTOS + 1):
        try:
            with urllib.request.urlopen(peticion, timeout=TIMEOUT) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{url}: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            ultimo = e
            if intento < INTENTOS:
                time.sleep(ESPERA * intento)
    raise RuntimeError(f"no se pudo consultar {url} tras {INTENTOS} intentos: {ultimo}")


def _descargar_documento(lector) -> dict:
    """Metadatos del documento (licencia incluida): se refrescan en cada actualización."""
    url = f"{API}/documents/{DOCUMENTO}/"
    datos = lector(url)
    entrada = {
        "cache": CACHE,
        "fuente": {"api": "open5e", "api_version": "v2", "endpoint": "documents", "key": DOCUMENTO,
                   "url": url, "descargado": estado.ahora()},
        "datos": {
            "key": DOCUMENTO,
            "nombre": datos.get("name"),
            "licencia": ", ".join(c.get("name", "") for c in datos.get("licenses") or []) or None,
            "editor": (datos.get("publisher") or {}).get("name"),
            "juego": (datos.get("gamesystem") or {}).get("name"),
            "permalink": datos.get("permalink"),
            "descripcion": datos.get("desc"),
            "fecha_publicacion": datos.get("publication_date"),
        },
    }
    _escribir(ruta_documento(), entrada)
    return entrada


def documento_local() -> dict | None:
    """Metadatos cacheados del documento, o None si nunca se actualizó. Sin red."""
    ruta = ruta_documento()
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _exigir_documento(objeto: dict, clave: str) -> None:
    documento = objeto.get("document")
    venido = documento.get("key") if isinstance(documento, dict) else documento
    if venido != DOCUMENTO:
        raise ValueError(f"«{clave}» viene de {venido!r}, no de {DOCUMENTO}: fuente equivocada, no se copia")


def _exigir_entrada(ruta: Path, entrada: dict) -> None:
    if entrada.get("cache") != CACHE:
        raise ValueError(f"{ruta}: caché de otra versión ({entrada.get('cache')!r}); vuelve a actualizarla")
    fuente = entrada.get("fuente") or {}
    if fuente.get("api") != "open5e" or fuente.get("documento") != DOCUMENTO:
        raise ValueError(
            f"{ruta}: fuente equivocada ({fuente.get('api')!r}/{fuente.get('documento')!r}); "
            f"solo se sirve open5e/{DOCUMENTO}"
        )
    if not isinstance(entrada.get("datos"), dict):
        raise ValueError(f"{ruta}: entrada sin datos")


def actualizar(tipo: str, clave: str, lector=None) -> dict:
    """Copia un objeto del documento a la caché con su procedencia. Única vía online."""
    endpoint = _endpoint(tipo)
    lector = lector or _leer_json
    url = f"{API}/{endpoint}/?document__key={DOCUMENTO}&key={urllib.parse.quote(clave)}"
    respuesta = lector(url)
    resultados = respuesta.get("results") or []
    if not resultados:
        raise ValueError(
            f"open5e no tiene {tipo} «{clave}» en el documento {DOCUMENTO} "
            f"(usa `bin/mesa fuentes buscar {tipo} <texto>`)"
        )
    objeto = resultados[0]
    _exigir_documento(objeto, clave)
    documento = _descargar_documento(lector)
    entrada = {
        "cache": CACHE,
        "fuente": {
            "api": "open5e", "api_version": "v2", "endpoint": endpoint,
            "key": objeto.get("key", clave), "documento": DOCUMENTO,
            "licencia": documento["datos"]["licencia"], "permalink": documento["datos"]["permalink"],
            "url": url, "descargado": estado.ahora(),
        },
        "datos": _MAPEADORES[tipo](objeto),
    }
    _escribir(ruta_entrada(tipo, clave), entrada)
    return entrada


def obtener(tipo: str, clave: str) -> dict:
    """Los datos mapeados de la caché. Sin red: si no están, se avisa y no se inventa."""
    _endpoint(tipo)
    ruta = ruta_entrada(tipo, clave)
    if not ruta.exists():
        raise ValueError(f"{tipo} «{clave}» no está en la caché local: `bin/mesa fuentes actualizar {tipo} {clave}`")
    try:
        entrada = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{ruta} está corrupto ({e}); vuelve a actualizarlo") from e
    _exigir_entrada(ruta, entrada)
    return entrada["datos"]


def listar(tipo: str | None = None) -> list[dict]:
    """Las entradas de la caché con su procedencia, ordenadas. Sin red."""
    if tipo:
        _endpoint(tipo)
        tipos = [tipo]
    else:
        tipos = list(TIPOS)
    entradas = []
    for t in tipos:
        carpeta = _dir() / t
        if not carpeta.exists():
            continue
        for ruta in sorted(carpeta.glob("*.json")):
            try:
                entrada = json.loads(ruta.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                entradas.append({"tipo": t, "key": ruta.stem, "nombre": None, "error": "json corrupto"})
                continue
            fuente = entrada.get("fuente") or {}
            entradas.append({
                "tipo": t, "key": ruta.stem, "nombre": (entrada.get("datos") or {}).get("nombre"),
                "documento": fuente.get("documento"), "licencia": fuente.get("licencia"),
                "descargado": fuente.get("descargado"),
            })
    return entradas


def buscar(tipo: str, texto: str, limite: int = 10, lector=None) -> list[dict]:
    """Busca en Open5e (una página) y devuelve keys listas para `actualizar`. Sale a la red."""
    endpoint = _endpoint(tipo)
    lector = lector or _leer_json
    url = (
        f"{API}/{endpoint}/?document__key={DOCUMENTO}&name__icontains={urllib.parse.quote(texto)}"
        f"&limit={int(limite)}&fields=key,name"
    )
    respuesta = lector(url)
    return [{"key": r.get("key"), "nombre": r.get("name")} for r in respuesta.get("results") or []]


# ---------- mapeo interno ----------
#
# El motor no depende de la forma de Open5e: la caché guarda ya el esquema interno.

def _mapear_conjuro(o: dict) -> dict:
    escuela = o.get("school") or {}
    return {
        "key": o.get("key"),
        "nombre": o.get("name"),
        "nivel": o.get("level"),
        "escuela": escuela.get("key"),
        "escuela_nombre": escuela.get("name"),
        "tiempo_de_lanzamiento": o.get("casting_time"),
        "alcance": {"texto": o.get("range_text"), "valor": o.get("range"), "unidad": o.get("range_unit")},
        "componentes": {
            "verbal": o.get("verbal"), "somatico": o.get("somatic"), "material": o.get("material"),
            "material_especificado": o.get("material_specified"), "material_gastado": o.get("material_consumed"),
        },
        "duracion": o.get("duration"),
        "concentracion": o.get("concentration"),
        "ritual": o.get("ritual"),
        "descripcion": o.get("desc"),
        "niveles_superiores": o.get("higher_level"),
        "ataque": o.get("attack_roll"),
        "salvacion": o.get("saving_throw_ability"),
        "dano": {"expresion": o.get("damage_roll"), "tipos": o.get("damage_types") or []},
        "objetivo": {"tipo": o.get("target_type"), "cantidad": o.get("target_count")},
        "forma": {"tipo": o.get("shape_type"), "tamano": o.get("shape_size"), "unidad": o.get("shape_size_unit")},
        "clases": [c.get("key") for c in o.get("classes") or []],
        "opciones_de_lanzamiento": o.get("casting_options") or [],
    }


def _mapear_condicion(o: dict) -> dict:
    return {
        "key": o.get("key"),
        "nombre": o.get("name"),
        "icono": o.get("icon"),
        "descripciones": [
            {"texto": d.get("desc"), "documento": d.get("document")} for d in o.get("descriptions") or []
        ],
    }


def _mapear_regla(o: dict) -> dict:
    return {
        "key": o.get("key"),
        "nombre": o.get("name"),
        "descripcion": o.get("desc"),
        "indice": o.get("index"),
        "nivel_encabezado": o.get("initialHeaderLevel"),
        "ruleset": o.get("ruleset"),
    }


_MAPEADORES = {"conjuro": _mapear_conjuro, "condicion": _mapear_condicion, "regla": _mapear_regla}

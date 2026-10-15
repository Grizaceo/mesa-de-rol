"""Imágenes de escena. Tres modos, de más simple a más caro:

  ninguna   tarjeta SVG generada aquí mismo (sin red, siempre disponible)
  elegir    una imagen ya existente: de biblioteca/, una ruta local o una URL
  generar   opcional: la pide a un proveedor (gemini u openrouter) con la clave del entorno

Generar envía el prompt de la escena a un servicio externo y gasta crédito de esa
clave; por eso nunca ocurre sin que alguien lo pida explícitamente.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import urllib.request
from html import escape
from pathlib import Path

from . import estado
from .texto import norm

EXTENSIONES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
TAMANO_MAXIMO = 15 * 1024 * 1024
MODELOS = {"gemini": "gemini-2.5-flash-image", "openrouter": "google/gemini-2.5-flash-image"}


def dir_biblioteca() -> Path:
    return estado.RAIZ / "biblioteca" / "imagenes"


def _indice_biblioteca() -> Path:
    return dir_biblioteca() / "indice.json"


def leer_biblioteca() -> list[dict]:
    ruta = _indice_biblioteca()
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []


def _dir_imagenes(slug: str) -> Path:
    ruta = estado.dir_partida(slug) / "imagenes"
    ruta.mkdir(exist_ok=True)
    return ruta


def _nombre_destino(datos: dict, sufijo: str, base: str = "") -> str:
    numero = datos.get("escena", {}).get("numero", 0)
    limpio = re.sub(r"[^a-z0-9]+", "-", norm(base or datos.get("escena", {}).get("titulo", "escena"))).strip("-")[:40]
    return f"escena-{numero:02d}-{limpio or 'imagen'}{sufijo}"


def _asignar(slug: str, datos: dict, archivo: str, modo: str, fuente: str, prompt: str | None = None) -> dict:
    escena = datos.setdefault("escena", {})
    escena["imagen"] = archivo
    escena["imagen_fuente"] = {"modo": modo, "origen": fuente, **({"prompt": prompt} if prompt else {})}
    estado.guardar(slug, datos)
    return estado.registrar(slug, {"tipo": "imagen", "archivo": archivo, "modo": modo, "origen": fuente})


def tarjeta_svg(slug: str) -> dict:
    """Modo 'ninguna': una tarjeta tipográfica con el título y el lugar de la escena."""
    datos = estado.cargar(slug)
    escena = datos.get("escena", {})
    acento = datos.get("tema", {}).get("acento", "#8a6d3b")
    titulo = escape(escena.get("titulo", datos.get("titulo", "")))
    lugar = escape(" · ".join(x for x in (escena.get("lugar"), escena.get("hora")) if x))
    numero = escena.get("numero", 0)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" role="img" aria-label="{titulo}">
  <defs>
    <linearGradient id="f" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{acento}" stop-opacity="0.55"/>
      <stop offset="1" stop-color="#14120f"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="675" fill="#14120f"/>
  <rect width="1200" height="675" fill="url(#f)"/>
  <rect x="36" y="36" width="1128" height="603" fill="none" stroke="#e8dcc4" stroke-opacity="0.35" stroke-width="2"/>
  <text x="80" y="140" fill="#e8dcc4" fill-opacity="0.7" font-family="Georgia, serif" font-size="34" letter-spacing="6">ESCENA {numero}</text>
  <text x="80" y="330" fill="#f4ecd8" font-family="Georgia, serif" font-size="78">{titulo}</text>
  <text x="80" y="410" fill="#e8dcc4" fill-opacity="0.85" font-family="Georgia, serif" font-size="36" font-style="italic">{lugar}</text>
</svg>
"""
    nombre = _nombre_destino(datos, ".svg", "tarjeta")
    (_dir_imagenes(slug) / nombre).write_text(svg, encoding="utf-8")
    return _asignar(slug, datos, nombre, "ninguna", "tarjeta generada localmente")


def buscar(consulta: str, limite: int = 8) -> list[dict]:
    """Busca en biblioteca/imagenes/indice.json por coincidencia de etiquetas y descripción."""
    palabras = {p for p in re.split(r"\W+", norm(consulta)) if len(p) > 2}
    puntuadas = []
    for item in leer_biblioteca():
        texto = norm(" ".join([item.get("descripcion", ""), *item.get("etiquetas", [])]))
        etiquetas = {norm(t) for t in item.get("etiquetas", [])}
        puntos = sum(3 if p in etiquetas else 1 for p in palabras if p in texto)
        if puntos:
            puntuadas.append((puntos, item))
    puntuadas.sort(key=lambda x: -x[0])
    return [item | {"puntos": p} for p, item in puntuadas[:limite]]


def agregar_biblioteca(ruta: str, etiquetas: list[str], descripcion: str, fuente: str, licencia: str) -> dict:
    origen = Path(ruta).expanduser()
    if origen.suffix.lower() not in EXTENSIONES or not origen.is_file():
        raise ValueError(f"no es una imagen válida: {ruta}")
    dir_biblioteca().mkdir(parents=True, exist_ok=True)
    destino = dir_biblioteca() / origen.name
    if destino.exists() and destino.resolve() != origen.resolve():
        raise FileExistsError(f"ya hay una imagen llamada {origen.name} en la biblioteca")
    if destino.resolve() != origen.resolve():
        shutil.copy2(origen, destino)
    indice = [i for i in leer_biblioteca() if i["archivo"] != origen.name]
    item = {
        "id": re.sub(r"[^a-z0-9]+", "-", norm(origen.stem)).strip("-"),
        "archivo": origen.name,
        "etiquetas": etiquetas,
        "descripcion": descripcion,
        "fuente": fuente,
        "licencia": licencia,
    }
    indice.append(item)
    _indice_biblioteca().write_text(json.dumps(indice, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return item


def _descargar(url: str) -> tuple[bytes, str]:
    peticion = urllib.request.Request(url, headers={"User-Agent": "mesa-de-rol/0.1"})
    with urllib.request.urlopen(peticion, timeout=30) as resp:
        tipo = resp.headers.get_content_type()
        if not tipo.startswith("image/"):
            raise ValueError(f"la URL no devuelve una imagen (Content-Type: {tipo})")
        cuerpo = resp.read(TAMANO_MAXIMO + 1)
    if len(cuerpo) > TAMANO_MAXIMO:
        raise ValueError("la imagen supera 15 MB")
    sufijo = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/svg+xml": ".svg"}.get(tipo, ".img")
    return cuerpo, sufijo


def elegir(slug: str, fuente: str) -> dict:
    """Modo 'elegir': id de la biblioteca, ruta local o URL http(s)."""
    datos = estado.cargar(slug)
    destino_dir = _dir_imagenes(slug)
    item = next((i for i in leer_biblioteca() if i["id"] == fuente or i["archivo"] == fuente), None)
    if item:
        origen = dir_biblioteca() / item["archivo"]
        nombre = _nombre_destino(datos, origen.suffix.lower(), origen.stem)
        shutil.copy2(origen, destino_dir / nombre)
        return _asignar(slug, datos, nombre, "elegir", f"biblioteca:{item['id']} ({item.get('licencia', 'licencia sin indicar')})")
    if re.match(r"https?://", fuente):
        cuerpo, sufijo = _descargar(fuente)
        nombre = _nombre_destino(datos, sufijo, Path(fuente.split("?")[0]).stem)
        (destino_dir / nombre).write_bytes(cuerpo)
        return _asignar(slug, datos, nombre, "elegir", fuente)
    origen = Path(fuente).expanduser()
    if not origen.is_file() or origen.suffix.lower() not in EXTENSIONES:
        raise ValueError(f"no encuentro la imagen {fuente!r} (ni en la biblioteca, ni como ruta, ni como URL)")
    if origen.stat().st_size > TAMANO_MAXIMO:
        raise ValueError("la imagen supera 15 MB")
    nombre = _nombre_destino(datos, origen.suffix.lower(), origen.stem)
    shutil.copy2(origen, destino_dir / nombre)
    return _asignar(slug, datos, nombre, "elegir", str(origen))


def construir_prompt(datos: dict) -> str:
    escena = datos.get("escena", {})
    ambientacion = datos.get("ambientacion", {})
    partes = [
        ambientacion.get("estilo_visual", "ilustración narrativa, luz natural"),
        f"Escena: {escena.get('titulo', '')}.",
        f"Lugar: {escena.get('lugar', '')}. Momento: {escena.get('hora', '')}. {escena.get('clima', '')}",
        escena.get("descripcion", ""),
        f"Época y lugar: {ambientacion.get('epoca', '')}, {ambientacion.get('lugar', '')}.",
        "Composición cinematográfica, sin texto, sin letras, sin marcas de agua.",
    ]
    return " ".join(p.strip() for p in partes if p and p.strip())


def _clave(nombres: tuple[str, ...]) -> str:
    for nombre in nombres:
        if os.environ.get(nombre):
            return os.environ[nombre]
    archivo = os.environ.get("MESA_ENV_FILE")
    if archivo and Path(archivo).expanduser().exists():
        for linea in Path(archivo).expanduser().read_text(encoding="utf-8").splitlines():
            clave, _, valor = linea.partition("=")
            if clave.strip() in nombres and valor.strip():
                return valor.strip().strip("'\"")
    raise RuntimeError(f"falta la clave {' o '.join(nombres)} (en el entorno o en $MESA_ENV_FILE)")


def _post_json(url: str, cuerpo: dict, cabeceras: dict) -> dict:
    peticion = urllib.request.Request(
        url, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json", **cabeceras}
    )
    with urllib.request.urlopen(peticion, timeout=120) as resp:
        return json.loads(resp.read())


def _generar_gemini(prompt: str, modelo: str) -> tuple[bytes, str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    resp = _post_json(
        url,
        {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}},
        {"x-goog-api-key": _clave(("GEMINI_API_KEY", "GOOGLE_API_KEY"))},
    )
    for candidato in resp.get("candidates", []):
        for parte in candidato.get("content", {}).get("parts", []):
            datos = parte.get("inlineData") or parte.get("inline_data")
            if datos:
                return base64.b64decode(datos["data"]), datos.get("mimeType", "image/png")
    raise RuntimeError(f"gemini no devolvió imagen: {json.dumps(resp)[:300]}")


def _generar_openrouter(prompt: str, modelo: str) -> tuple[bytes, str]:
    resp = _post_json(
        "https://openrouter.ai/api/v1/chat/completions",
        {"model": modelo, "messages": [{"role": "user", "content": prompt}], "modalities": ["image", "text"]},
        {"Authorization": f"Bearer {_clave(('OPENROUTER_API_KEY',))}"},
    )
    for eleccion in resp.get("choices", []):
        for img in eleccion.get("message", {}).get("images", []):
            url = img.get("image_url", {}).get("url", "")
            if url.startswith("data:"):
                cabecera, _, b64 = url.partition(",")
                return base64.b64decode(b64), cabecera[5:].split(";")[0]
    raise RuntimeError(f"openrouter no devolvió imagen: {json.dumps(resp)[:300]}")


def generar(slug: str, prompt: str | None = None, proveedor: str | None = None, modelo: str | None = None, simular: bool = False) -> dict:
    """Modo 'generar' (opcional). Con simular=True solo devuelve lo que se enviaría."""
    datos = estado.cargar(slug)
    proveedor = proveedor or os.environ.get("MESA_IMAGEN_PROVEEDOR", "gemini")
    if proveedor not in MODELOS:
        raise ValueError(f"proveedor desconocido: {proveedor} (usa: {', '.join(MODELOS)})")
    modelo = modelo or os.environ.get("MESA_IMAGEN_MODELO") or MODELOS[proveedor]
    texto = prompt or construir_prompt(datos)
    if simular:
        return {"proveedor": proveedor, "modelo": modelo, "prompt": texto, "simulado": True}
    contenido, tipo = (_generar_gemini if proveedor == "gemini" else _generar_openrouter)(texto, modelo)
    sufijo = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(tipo, ".png")
    nombre = _nombre_destino(datos, sufijo)
    (_dir_imagenes(slug) / nombre).write_bytes(contenido)
    return _asignar(slug, datos, nombre, "generar", f"{proveedor}:{modelo}", prompt=texto)

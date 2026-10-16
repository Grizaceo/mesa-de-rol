"""Estado de partida en disco.

Cada partida vive en `partidas/<slug>/`:
  partida.json   estado visible para los jugadores (el visor lo muestra entero)
  eventos.jsonl  bitácora append-only: tiradas, turnos, cambios
  biblia.md      ambientación y reglas propias de la historia
  director.md    notas solo para el director (el visor nunca las sirve)
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from . import distribucion
from .texto import norm, slug_valido


def _raiz_de_datos() -> Path:
    """Dónde viven los datos mutables: `$MESA_RAIZ`, el checkout o el directorio del usuario."""
    if os.environ.get("MESA_RAIZ"):
        return Path(os.environ["MESA_RAIZ"]).expanduser()
    checkout = distribucion.raiz_checkout()
    if checkout is not None:
        return checkout
    datos = os.environ.get("XDG_DATA_HOME")
    return (Path(datos).expanduser() if datos else Path.home() / ".local" / "share") / "mesa-de-rol"


RAIZ = _raiz_de_datos()
PLANTILLA = "_plantilla"


def dir_partidas() -> Path:
    return RAIZ / "partidas"


def dir_partida(slug: str) -> Path:
    if not slug_valido(slug) and slug != PLANTILLA:
        raise ValueError(f"nombre de partida inválido: {slug!r}")
    ruta = dir_partidas() / slug
    if not (ruta / "partida.json").exists():
        raise FileNotFoundError(f"no existe la partida {slug!r} (mira `mesa partidas`)")
    return ruta


def ahora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def listar_partidas() -> list[dict]:
    salida = []
    if not dir_partidas().exists():
        return salida
    for ruta in sorted(dir_partidas().iterdir()):
        archivo = ruta / "partida.json"
        if ruta.name == PLANTILLA or not archivo.exists():
            continue
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        salida.append(
            {
                "slug": ruta.name,
                "titulo": datos.get("titulo", ruta.name),
                "actualizado": datos.get("actualizado"),
            }
        )
    return salida


def _archivo_activa() -> Path:
    return RAIZ / ".mesa-activa"


def slug_activo(explicito: str | None = None) -> str:
    """Orden: argumento > $MESA_PARTIDA > .mesa-activa > la única partida que exista."""
    if explicito:
        return explicito
    if os.environ.get("MESA_PARTIDA"):
        return os.environ["MESA_PARTIDA"]
    archivo = _archivo_activa()
    if archivo.exists() and archivo.read_text(encoding="utf-8").strip():
        return archivo.read_text(encoding="utf-8").strip()
    partidas = listar_partidas()
    if len(partidas) == 1:
        return partidas[0]["slug"]
    raise ValueError("no hay partida activa: usa `mesa usar <slug>` o --partida")


def usar(slug: str) -> None:
    dir_partida(slug)
    _archivo_activa().write_text(slug + "\n", encoding="utf-8")


def cargar(slug: str) -> dict:
    return json.loads((dir_partida(slug) / "partida.json").read_text(encoding="utf-8"))


def guardar(slug: str, datos: dict) -> None:
    """Escritura atómica: el visor nunca lee un JSON a medias."""
    datos["version"] = int(datos.get("version", 0)) + 1
    datos["actualizado"] = ahora()
    ruta = dir_partida(slug) / "partida.json"
    tmp = ruta.with_name("partida.json.tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, ruta)


def _ruta_eventos(slug: str) -> Path:
    return dir_partida(slug) / "eventos.jsonl"


def leer_eventos(slug: str, desde: int = 0, limite: int | None = None) -> list[dict]:
    ruta = _ruta_eventos(slug)
    if not ruta.exists():
        return []
    eventos = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            evento = json.loads(linea)
        except json.JSONDecodeError:
            continue  # una línea a medio escribir: se leerá en el próximo sondeo
        if evento.get("seq", 0) > desde:
            eventos.append(evento)
    return eventos[-limite:] if limite else eventos


def narrador_actual(slug: str) -> str | None:
    """$MESA_NARRADOR manda; si no, el narrador de la sesión abierta con `mesa retomar`."""
    if os.environ.get("MESA_NARRADOR"):
        return os.environ["MESA_NARRADOR"]
    try:
        return cargar(slug).get("sesion", {}).get("narrador")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def registrar(slug: str, evento: dict) -> dict:
    ruta = _ruta_eventos(slug)
    previos = leer_eventos(slug)
    seq = (previos[-1]["seq"] if previos else 0) + 1
    completo = {"seq": seq, "ts": ahora(), **evento}
    narrador = narrador_actual(slug)
    if narrador and "narrador" not in completo:
        completo["narrador"] = narrador
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(completo, ensure_ascii=False) + "\n")
    return completo


def buscar(datos: dict, quien: str) -> tuple[str, dict]:
    """Encuentra un personaje o enemigo por id o nombre (sin tildes; acepta prefijo único).

    Un selector vacío o solo espacios es un error: sin esta guarda, `clave in nombres`
    daría positivo en cualquier ficha sin id y el primer personaje recibiría la acción.
    La coincidencia exacta gana al prefijo; si hay varias exactas o varias por prefijo,
    el error dice cuáles para elegir por id.
    """
    clave = norm(quien)
    if not clave:
        raise ValueError("el selector está vacío: dime el nombre o el id del personaje")
    exactos: list[tuple[str, dict]] = []
    por_prefijo: list[tuple[str, dict]] = []
    for tipo, lista in (("personaje", datos.get("personajes", [])), ("enemigo", datos.get("enemigos", []))):
        for ficha in lista:
            nombres = {norm(ficha.get("id", "")), norm(ficha.get("nombre", ""))}
            if clave in nombres:
                exactos.append((tipo, ficha))
            elif any(n.startswith(clave) for n in nombres if n):
                por_prefijo.append((tipo, ficha))
    if len(exactos) == 1:
        return exactos[0]
    candidatos = exactos or por_prefijo
    todos = [f["nombre"] for f in datos.get("personajes", []) + datos.get("enemigos", [])]
    if len(candidatos) == 1:
        return candidatos[0]
    if candidatos:
        raise ValueError(f"{quien!r} es ambiguo: {', '.join(f['nombre'] for _, f in candidatos)}")
    raise ValueError(f"no encuentro a {quien!r}; hay: {', '.join(todos) or 'nadie'}")


def nueva_partida(slug: str, titulo: str) -> Path:
    if not slug_valido(slug):
        raise ValueError("el slug va en minúsculas, con guiones: p. ej. 'la-isla-sin-nombre'")
    destino = dir_partidas() / slug
    if destino.exists():
        raise FileExistsError(f"ya existe {destino}")
    shutil.copytree(distribucion.plantilla(), destino)
    datos = json.loads((destino / "partida.json").read_text(encoding="utf-8"))
    datos.update({"slug": slug, "titulo": titulo, "creada": ahora(), "version": 0})
    (destino / "partida.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destino / "eventos.jsonl").write_text("", encoding="utf-8")
    for carpeta in ("imagenes", "guardados"):
        (destino / carpeta).mkdir(exist_ok=True)
    registrar(slug, {"tipo": "partida_creada", "titulo": titulo})
    return destino

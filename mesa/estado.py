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

from . import bloqueo, distribucion, esquemas
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


class Conflicto(RuntimeError):
    """El estado cambió desde que se cargó: no se escribe encima de otro sin avisar."""


def cargar(slug: str) -> dict:
    _recuperar_si_hace_falta(slug)
    datos = json.loads((dir_partida(slug) / "partida.json").read_text(encoding="utf-8"))
    esquemas.validar(datos, slug)
    return datos


# ---------- escritura: una transacción con diario ----------
#
# Guardar es snapshot (partida.json) y bitácora (eventos.jsonl) a la vez, en ese
# orden, con un diario (`.transaccion.json`) como punto de no retorno:
#
#   1. se escribe el diario con el snapshot nuevo y los eventos numerados;
#   2. se aplica: snapshot atómico y eventos al final del JSONL, sin duplicar seq;
#   3. se borra el diario.
#
# Si el proceso muere antes del paso 1, no se escribió nada; si muere entre 1 y 3,
# la próxima lectura o escritura reaplica el diario entero. Nunca queda medio turno.
# El candado (`bloqueo.candado`) serializa comandos completos y transacciones.
# Lo que se confirma ya está en disco: `_escribir_texto` fuerza el dato con fsync y el
# renombre con un fsync del directorio, así que un corte de luz no se lleva un cambio aceptado.
#
# Idempotencia general (`command_id` en el evento, con el resultado original): pendiente
# a propósito. Se diseña y habilita antes de los reintentos automáticos, conectores o web;
# hasta entonces cada transacción aceptada tiene un solo orden y la rechazada no muta.

CANDADO = ".candado"
DIARIO = ".transaccion.json"


def ruta_candado(slug: str) -> Path:
    return dir_partida(slug) / CANDADO


def ruta_diario(slug: str) -> Path:
    return dir_partida(slug) / DIARIO


def _version_en_disco(directorio: Path) -> int:
    return int(json.loads((directorio / "partida.json").read_text(encoding="utf-8")).get("version", 0))


def _escribir_texto(ruta: Path, texto: str) -> None:
    """Escritura atómica y durable: nadie ve un archivo a medias y el corte de luz no se lleva lo aceptado."""
    tmp = ruta.with_name(ruta.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)
    _sincronizar_directorio(ruta.parent)


def _sincronizar_directorio(directorio: Path) -> None:
    """Deja durable el nombre nuevo en el directorio; en sistemas que no dejan, se sigue igual."""
    try:
        fd = os.open(directorio, os.O_RDONLY)
    except OSError:  # pragma: no cover - sistemas sin open de directorios
        return
    try:
        os.fsync(fd)
    except OSError:  # pragma: no cover - sistemas que rechazan fsync en directorios
        pass
    finally:
        os.close(fd)


def _reparar_eventos(ruta: Path) -> int:
    """Devuelve el último seq y recorta una última línea a medio escribir, si la hay.

    Una línea rota en medio no se toca: sería perder eventos en silencio. Se avisa.
    """
    if not ruta.exists():
        return 0
    lineas = [linea for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
    ultimo = 0
    for posicion, linea in enumerate(lineas):
        try:
            ultimo = int(json.loads(linea).get("seq", 0))
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            if posicion != len(lineas) - 1:
                raise Conflicto(
                    f"{ruta.parent.name}: la bitácora tiene una línea rota en la {posicion + 1}; "
                    "revísala a mano antes de seguir (no se toca para no perder eventos)"
                ) from None
            _escribir_texto(ruta, "".join(f"{buena}\n" for buena in lineas[:posicion]))
            return ultimo
    return ultimo


def _unir_eventos(slug: str, eventos: list[dict]) -> None:
    ruta = _ruta_eventos(slug)
    ultimo = _reparar_eventos(ruta)
    nuevos = [e for e in eventos if e.get("seq", 0) > ultimo]
    if not nuevos:
        return
    with ruta.open("a", encoding="utf-8") as f:
        for evento in nuevos:
            f.write(json.dumps(evento, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _aplicar(slug: str, diario: dict) -> None:
    directorio = dir_partida(slug)
    eventos = diario.get("eventos") or []
    if eventos:
        # Primero la bitácora: si una línea rota en medio impide continuar, se avisa
        # antes de tocar el snapshot y la transacción sigue entera (nada aplicado).
        _reparar_eventos(_ruta_eventos(slug))
    if diario.get("datos") is not None:
        en_disco = _version_en_disco(directorio)
        if en_disco > diario["version"]:
            raise Conflicto(
                f"{slug}: el estado ya va en la versión {en_disco}, más nueva que la transacción "
                f"{diario['version']} del diario; revisa `{DIARIO}` antes de seguir"
            )
        if en_disco < diario["version"]:
            _escribir_texto(directorio / "partida.json", json.dumps(diario["datos"], ensure_ascii=False, indent=2) + "\n")
    _unir_eventos(slug, eventos)


def _recuperar(slug: str) -> None:
    """Termina una transacción que quedó a medias (reasigna y borra el diario)."""
    ruta = ruta_diario(slug)
    if not ruta.exists():
        return
    try:
        diario = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Conflicto(f"{slug}: el diario `{DIARIO}` quedó corrupto ({e}); revísalo a mano") from e
    _aplicar(slug, diario)
    ruta.unlink()


def _recuperar_si_hace_falta(slug: str) -> None:
    """En las lecturas: si hay diario pendiente, se termina bajo el candado."""
    try:
        ruta = ruta_diario(slug)
    except FileNotFoundError:
        return
    if not ruta.exists():
        return
    with bloqueo.candado(ruta_candado(slug)):
        if ruta.exists():
            _recuperar(slug)


def _completar_eventos(slug: str, eventos) -> list[dict]:
    if not eventos:
        return []
    narrador = narrador_actual(slug)
    seq = _reparar_eventos(_ruta_eventos(slug))
    completos = []
    for evento in eventos:
        seq += 1
        completo = {"seq": seq, "ts": ahora(), **evento}
        if narrador and "narrador" not in completo:
            completo["narrador"] = narrador
        completos.append(completo)
    return completos


def escribir(slug: str, datos: dict | None = None, eventos=()) -> list[dict]:
    """Un solo commit: el snapshot (si viene) y los eventos (si vienen), o nada.

    `datos` debe ser el estado cargado de esta partida: se comprueba la versión en
    disco y se sube una sola vez. Devuelve los eventos ya numerados, en orden.
    """
    with bloqueo.candado(ruta_candado(slug)):
        _recuperar(slug)
        directorio = dir_partida(slug)
        if datos is not None:
            esquemas.validar(datos, slug)
            en_disco = _version_en_disco(directorio)
            cargada = int(datos.get("version", 0))
            if cargada != en_disco:
                raise Conflicto(
                    f"{slug}: cargaste la versión {cargada} y en disco va la {en_disco}; "
                    "recarga el estado y repite el cambio (nadie pisó a nadie)"
                )
            datos["version"] = en_disco + 1
            datos["actualizado"] = ahora()
        completos = _completar_eventos(slug, eventos)
        if datos is None and not completos:
            return []
        diario = {
            "version": datos["version"] if datos is not None else None,
            "datos": datos,
            "eventos": completos,
        }
        try:
            # JSON estricto: un NaN o un infinito rompería al navegador que lee la partida.
            texto_diario = json.dumps(diario, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        except ValueError:
            raise ValueError(f"{slug}: hay un número no válido (NaN o infinito) en el cambio: no se guarda") from None
        _escribir_texto(directorio / DIARIO, texto_diario)
        _aplicar(slug, diario)
        ruta_diario(slug).unlink()
        return completos


def guardar(slug: str, datos: dict) -> None:
    """Guarda el snapshot, con la versión y la bitácora en la misma transacción."""
    escribir(slug, datos=datos)


def _ruta_eventos(slug: str) -> Path:
    return dir_partida(slug) / "eventos.jsonl"


def leer_eventos(slug: str, desde: int = 0, limite: int | None = None) -> list[dict]:
    _recuperar_si_hace_falta(slug)
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
    """Anota un evento en la bitácora, con su seq asignado dentro del candado."""
    return escribir(slug, eventos=[evento])[0]


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
    try:
        shutil.copytree(distribucion.plantilla(), destino)
    except FileExistsError:  # otro proceso creó la misma partida a la vez
        raise FileExistsError(f"ya existe {destino} (¿la creó otro proceso a la vez?)") from None
    datos = json.loads((destino / "partida.json").read_text(encoding="utf-8"))
    datos.update({"slug": slug, "titulo": titulo, "creada": ahora(), "version": 0})
    esquemas.validar(datos, slug)
    (destino / "partida.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destino / "eventos.jsonl").write_text("", encoding="utf-8")
    for carpeta in ("imagenes", "guardados"):
        (destino / carpeta).mkdir(exist_ok=True)
    registrar(slug, {"tipo": "partida_creada", "titulo": titulo})
    return destino

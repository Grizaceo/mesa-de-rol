"""Qué es programa (inmutable) y qué son datos (mutables).

Inmutables: `visor/`, `partidas/_plantilla/` y `adaptadores/`. Cuando se corre desde el
repositorio se usan los originales; el wheel lleva una copia en `mesa/recursos/`, que
`diferencias()` mantiene honesta (`bin/mesa recursos sync` la actualiza).

Mutables: `partidas/`, `biblioteca/`, `lecciones/` y `.mesa-activa`. Viven siempre bajo
`estado.RAIZ`: el repositorio si se corre desde el checkout, o `$MESA_RAIZ` (o el
directorio de datos del usuario) si el paquete viene instalado de un wheel.
"""

from __future__ import annotations

from pathlib import Path

PAQUETE = Path(__file__).resolve().parent
COPIAS = PAQUETE / "recursos"
INMUTABLES = ("visor", "partidas/_plantilla", "adaptadores")


def raiz_checkout() -> Path | None:
    """La raíz del repositorio, si este paquete es el del checkout; si no, None."""
    raiz = PAQUETE.parent
    if (raiz / "visor" / "index.html").is_file() and (raiz / "partidas" / "_plantilla" / "partida.json").is_file():
        return raiz
    return None


def inmutable(relativo: str) -> Path:
    """Ruta de un recurso del programa: del checkout si está, de la copia empaquetada si no."""
    raiz = raiz_checkout()
    if raiz is not None and (raiz / relativo).exists():
        return raiz / relativo
    return COPIAS / relativo


def visor() -> Path:
    return inmutable("visor")


def plantilla() -> Path:
    return inmutable("partidas/_plantilla")


def adaptadores() -> Path:
    return inmutable("adaptadores")


def _archivos(base: Path) -> dict[str, Path]:
    archivos: dict[str, Path] = {}
    for carpeta in INMUTABLES:
        raiz = base / carpeta
        if raiz.exists():
            archivos.update((str(ruta.relative_to(base)), ruta) for ruta in sorted(raiz.rglob("*")) if ruta.is_file())
    return archivos


def diferencias() -> list[str]:
    """Recursos de la copia empaquetada que no coinciden byte a byte con el repositorio."""
    raiz = raiz_checkout()
    if raiz is None:
        return []
    originales, copias = _archivos(raiz), _archivos(COPIAS)
    distintas = []
    for relativo in sorted(set(originales) | set(copias)):
        original, copia = originales.get(relativo), copias.get(relativo)
        if original is None or copia is None or original.read_bytes() != copia.read_bytes():
            distintas.append(relativo)
    return distintas


def sincronizar() -> list[str]:
    """Copia los recursos del repositorio a `mesa/recursos/`; devuelve lo que cambió."""
    raiz = raiz_checkout()
    if raiz is None:
        raise RuntimeError("este paquete vino de un wheel: no hay repositorio del que copiar")
    cambiadas = diferencias()
    for relativo in cambiadas:
        origen, destino = raiz / relativo, COPIAS / relativo
        if origen.is_file():
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(origen.read_bytes())
        elif destino.exists():
            destino.unlink()
    return cambiadas


def verificar() -> tuple[str, str]:
    """Estado de la copia empaquetada, para `mesa harness verificar`."""
    if raiz_checkout() is None:
        return "omitido", "instalado desde un wheel: los recursos vienen dentro del paquete"
    pendientes = diferencias()
    if pendientes:
        return "fallo", f"desincronizados: {', '.join(pendientes)} (corre `bin/mesa recursos sync`)"
    return "ok", "en sincronía con visor/, partidas/_plantilla/ y adaptadores/"

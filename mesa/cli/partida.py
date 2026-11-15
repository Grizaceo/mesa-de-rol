"""Partidas: listar, usar, crear, estado, retomar, pausar, contexto y guardar."""

from __future__ import annotations

import json

from .. import estado, informes, sesion
from .comunes import _cargar, _imprimir

def c_partidas(args) -> None:
    try:
        activa = estado.slug_activo(args.partida)
    except ValueError:
        activa = None
    for p in estado.listar_partidas():
        marca = "*" if p["slug"] == activa else " "
        print(f"{marca} {p['slug']:<32} {p['titulo']}  (actualizada {p.get('actualizado') or '-'})")


def c_usar(args) -> None:
    estado.usar(args.slug)
    print(f"Partida activa: {args.slug}")


def c_nueva(args) -> None:
    ruta = estado.nueva_partida(args.slug, args.titulo)
    estado.usar(args.slug)
    print(f"Creada {ruta.relative_to(estado.RAIZ)} y marcada como activa.")
    print("Siguiente: completa biblia.md y partida.json (personajes), y luego `mesa contexto --completo`.")


def c_estado(args) -> None:
    slug, datos = _cargar(args)
    if args.json:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
    elif args.breve:
        print("\n".join(informes.ficha_breve(p) for p in datos.get("personajes", [])))
    else:
        print(informes.resumen(datos))


def c_revisar(args) -> None:
    slug, datos = _cargar(args)
    avisos = informes.revisar(datos, eventos=estado.leer_eventos(slug))
    print("\n".join(f"⚠ {a}" for a in avisos) if avisos else "Sin avisos.")


def c_retomar(args) -> None:
    print(sesion.retomar(estado.slug_activo(args.partida), args.narrador))


def c_pausar(args) -> None:
    print(sesion.pausar(estado.slug_activo(args.partida), args.pendiente, commit=args.commit))

def c_contexto(args) -> None:
    print(informes.contexto(estado.slug_activo(args.partida), args.completo, args.eventos))

def c_guardar(args) -> None:
    texto, ruta = informes.guardado(estado.slug_activo(args.partida))
    print(texto)
    print(f"(guardado en {ruta})")


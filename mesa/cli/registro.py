"""Mundo visible, turno y notas: PNJ, pistas, documentos, tramas y bitácora."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from .. import capacidades, estado, informes, mapas
from ..texto import norm
from . import comunes
from .comunes import CAMBIOS, SOLO_LECTURA, _cargar, _cerrar, _imprimir

def c_pnj(args) -> None:
    slug, datos = _cargar(args)
    lista = datos.setdefault("pnj", [])
    pnj = next((n for n in lista if norm(n["nombre"]) == norm(args.nombre)), None)
    if pnj is None:
        pnj = {"nombre": args.nombre, "actitud": "indiferente", "notas": []}
        lista.append(pnj)
    for campo in ("rol", "actitud", "estado", "aspecto", "raza", "altura"):
        if getattr(args, campo, None):
            pnj[campo] = getattr(args, campo)
    if getattr(args, "conocido", False):
        pnj["conocido"] = True
    elif getattr(args, "desconocido", False):
        pnj["conocido"] = False
    if args.nota:
        pnj.setdefault("notas", []).append(args.nota)
    texto = f"PNJ {pnj['nombre']} ({pnj.get('actitud')}): {pnj.get('estado', '')} {args.nota or ''}".rstrip()
    _cerrar(args, slug, datos, {"tipo": "pnj", "nombre": pnj["nombre"], "actitud": pnj.get("actitud"), "nota": args.nota}, texto)


def c_pista(args) -> None:
    slug, datos = _cargar(args)
    datos.setdefault("pistas", []).append({"texto": args.texto, "fuente": args.fuente})
    _cerrar(args, slug, datos, {"tipo": "pista", "texto": args.texto}, f"Pista: {args.texto}")


def c_documento(args) -> None:
    slug, datos = _cargar(args)
    lista = datos.setdefault("documentos", [])
    if args.accion == "ver":
        if not args.titulo:
            print("\n".join(f"{d['id']} · {informes.NOMBRE_CLASE.get(d.get('clase'), 'Documento')} · {d['titulo']}" for d in lista) or "Sin documentos.")
            return
        clave = norm(args.titulo)
        doc = next((d for d in lista if norm(d["id"]) == clave or norm(d["titulo"]).startswith(clave)), None)
        if doc is None:
            raise ValueError(f"no hay documento {args.titulo!r} (mira `documento ver`)")
        print(informes.documento_chat(doc))
        return
    if not args.titulo:
        raise ValueError('uso: documento agregar "<título>" --texto "..." (o --archivo ruta)')
    texto = Path(args.archivo).expanduser().read_text(encoding="utf-8") if args.archivo else (args.texto or "")
    texto = texto.replace("\\n", "\n").strip()
    if not texto:
        raise ValueError("el documento necesita --texto o --archivo")
    numero = max((int(d["id"][1:]) for d in lista if d.get("id", "")[1:].isdigit()), default=0) + 1
    doc = {
        "id": f"D{numero}", "titulo": args.titulo, "clase": args.clase, "texto": texto, "fuente": args.fuente or "",
        "escena": datos.get("escena", {}).get("numero"), "desde": estado.ahora()[:10],
    }
    lista.append(doc)
    evento = {"tipo": "documento", "id": doc["id"], "titulo": doc["titulo"], "clase": doc["clase"]}
    _cerrar(args, slug, datos, evento, informes.documento_chat(doc))


def c_trama(args) -> None:
    slug, datos = _cargar(args)
    lista = datos.setdefault("tramas", [])
    trama = next((t for t in lista if norm(t["nombre"]) == norm(args.nombre)), None)
    if trama is None:
        trama = {"nombre": args.nombre, "estado": "activa"}
        lista.append(trama)
    if args.estado:
        trama["estado"] = args.estado
    if args.nota:
        trama["nota"] = args.nota
    _cerrar(args, slug, datos, {"tipo": "trama", **trama}, f"Trama {trama['nombre']} [{trama['estado']}]: {trama.get('nota', '')}")


def c_misterio(args) -> None:
    slug, datos = _cargar(args)
    lista = datos.setdefault("misterios", [])
    if args.resolver:
        lista[:] = [m for m in lista if norm(m) != norm(args.texto)]
        texto = f"Pregunta resuelta: {args.texto}"
    else:
        lista.append(args.texto)
        texto = f"Pregunta abierta: {args.texto}"
    _cerrar(args, slug, datos, {"tipo": "misterio", "texto": args.texto, "resuelto": args.resolver}, texto)


def c_recurso(args) -> None:
    slug, datos = _cargar(args)
    recursos = datos.setdefault("recursos", {})
    if args.sumar is not None:
        recursos[args.clave] = int(recursos.get(args.clave, 0)) + args.sumar
    elif args.valor is not None:
        recursos[args.clave] = int(args.valor) if args.valor.lstrip("-").isdigit() else args.valor
    else:
        recursos.pop(args.clave, None)
    valor = recursos.get(args.clave, "(quitado)")
    _cerrar(args, slug, datos, {"tipo": "recurso", "clave": args.clave, "valor": valor}, f"{args.clave}: {valor}")


def c_reloj(args) -> None:
    slug, datos = _cargar(args)
    reloj = datos.setdefault("reloj", {})
    if args.dia:
        reloj["dia"] = args.dia
    if args.hora:
        datos.setdefault("escena", {})["hora"] = args.hora
    plazos = reloj.setdefault("plazos", [])
    plazos += [p for p in args.plazo or [] if p not in plazos]
    plazos[:] = [p for p in plazos if norm(p) not in {norm(q) for q in args.quitar_plazo or []}]
    texto = f"Día {reloj.get('dia', '?')}, {datos.get('escena', {}).get('hora', '')}. Plazos: {'; '.join(plazos) or 'ninguno'}"
    _cerrar(args, slug, datos, {"tipo": "reloj", **reloj, "hora": datos.get("escena", {}).get("hora")}, texto)


def _leer_acciones(items: list[str] | None) -> dict[str, str]:
    acciones = {}
    for item in items or []:
        quien, signo, que = item.partition("=")
        if not signo or not quien.strip() or not que.strip():
            raise ValueError(f"acción inválida {item!r}: usa «Nombre=lo que declaró»")
        acciones[quien.strip()] = que.strip()
    return acciones


def _parsear_cambio(texto: str) -> argparse.Namespace:
    from .parser import construir
    partes = shlex.split(texto)
    if not partes or partes[0] not in CAMBIOS:
        raise ValueError(f"cambio no permitido: {texto!r} (valen: {', '.join(CAMBIOS)})")
    try:
        cambio = construir().parse_args(partes)
    except SystemExit:
        raise ValueError(f"cambio inválido: {texto!r}") from None
    motivo = capacidades.revisar(cambio, comunes._perfil)
    if motivo:
        raise ValueError(f"cambio no permitido: {motivo}")
    if getattr(cambio, "accion", None) in SOLO_LECTURA.get(cambio.comando, ()):
        raise ValueError(f"cambio no permitido: `{cambio.comando} {cambio.accion}` es una consulta de solo lectura")
    return cambio


def c_turno(args) -> None:
    """Registra el turno y, en el mismo paso, aplica los cambios de estado: todos o ninguno."""
    slug = estado.slug_activo(args.partida)
    acciones = _leer_acciones(args.accion)
    cambios = [_parsear_cambio(c) for c in args.cambio or []]
    datos = estado.cargar(slug)
    previos = estado.leer_eventos(slug)
    tenia_mapa_o_mundo = bool(
        (datos.get("escena") or {}).get("mapa")
        or datos.get("mundo")
        or any(e.get("tipo") == "mapa" for e in previos)
    )
    # El narrador no habla por un PJ que juega una persona: si registra lo que ese jugador no
    # escribió, el turno lo dice (no lo bloquea: el jugador decide si lo da por bueno).
    sin_declarar = informes.acciones_sin_declarar(slug, datos, acciones, previos)
    pausada = datos.pop("pausa", None) is not None
    comunes._lote = {"slug": slug, "datos": datos, "hechos": []}
    try:
        for cambio in cambios:
            cambio.funcion(cambio)
        if tenia_mapa_o_mundo or bool((datos.get("escena") or {}).get("mapa") or datos.get("mundo")):
            comunes._lote["hechos"].extend(mapas.asegurar_mapa_escena(datos, slug=slug))
        hechos = comunes._lote["hechos"]
    finally:
        comunes._lote = None
    evento_turno = {"tipo": "turno", "acciones": acciones, "resumen": args.resumen}
    if sin_declarar:
        evento_turno["sin_declarar"] = sin_declarar
    eventos = [evento for evento, _ in hechos] + [evento_turno]
    cambia_estado = bool(hechos) or pausada
    registrados = estado.escribir(slug, datos=datos if cambia_estado else None, eventos=eventos)
    cambios, evento = registrados[:-1], registrados[-1]
    todos = estado.leer_eventos(slug)
    numero = sum(1 for e in todos if e.get("tipo") == "turno")
    avisos = informes.revisar(datos, acciones, eventos=todos)
    if sin_declarar:
        avisos.insert(0, f"Sin declarar por su jugador: {', '.join(sin_declarar)}. Díselo en la respuesta: si no lo da por bueno, se corrige.")
    if args.json:
        print(json.dumps({"turno": evento, "cambios": cambios, "avisos": avisos}, ensure_ascii=False, indent=2))
        return
    lineas = [texto for _, texto in hechos] + [f"Turno {numero} registrado."]
    lineas += [f"⚠ {a}" for a in avisos]
    lineas += ["", "Para la DECISIÓN, lo que cada uno tiene a mano:"]
    lineas += [f"- {informes.ficha_breve(p)}" for p in datos.get("personajes", [])]
    zona = mapas.zona_texto(datos)
    if zona:
        lineas += ["", zona]
    print("\n".join(lineas))


def c_regla(args) -> None:
    slug, datos = _cargar(args)
    lista = datos.setdefault("reglas_casa", [])
    regla = {"id": f"R{len(lista) + 1}", "texto": args.texto, "desde": estado.ahora()[:10]}
    lista.append(regla)
    _cerrar(args, slug, datos, {"tipo": "regla", **regla}, f"Regla de la casa {regla['id']}: {args.texto}")


def c_nota(args) -> None:
    slug = estado.slug_activo(args.partida)
    _imprimir(args, estado.registrar(slug, {"tipo": "nota", "texto": args.texto}), "Nota registrada.")


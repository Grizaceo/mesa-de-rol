"""Escena, memoria de la historia y mapas de zona y del mundo."""

from __future__ import annotations

import json

from .. import estado, mapas, memoria
from ..texto import norm
from . import comunes
from .comunes import _cargar, _cerrar, _cerrar_mapa, _imprimir, _recargar

def c_escena(args) -> None:
    slug, datos = _cargar(args)
    escena = datos.setdefault("escena", {})
    if args.accion == "posicion" and (not args.quien or not (args.donde or args.celda or args.quitar)):
        raise ValueError('uso: escena posicion <quien> "<dónde, con metros>" [--celda C4] (o --quitar)')
    if args.cierre and args.accion != "nueva":
        raise ValueError("--cierre va con `escena nueva`: resume la escena que termina")
    aviso = ""
    if args.accion == "nueva":
        anterior = dict(escena)
        numero = int(anterior.get("numero") or 0)
        if numero >= 1 and not memoria.anotar_escena(datos, numero, args.cierre, anterior.get("titulo"), anterior.get("lugar")).get("resumen"):
            aviso = f"\n⚠ La escena {numero} se cerró sin resumen en la crónica: `memoria escena {numero} \"<qué pasó>\"`."
        escena.clear()
        if args.conservar_mapa and anterior.get("mapa"):
            escena.update({"mapa": anterior["mapa"], "posiciones": anterior.get("posiciones", [])})
        escena["numero"] = int(datos.get("escenas_jugadas", 0)) + 1
        datos["escenas_jugadas"] = escena["numero"]
        _recargar(datos, {"escena"})
    if args.accion in ("nueva", "editar"):
        for campo in ("titulo", "lugar", "hora", "clima", "descripcion"):
            if getattr(args, campo):
                escena[campo] = getattr(args, campo)
        texto = f"Escena {escena.get('numero')}: {escena.get('titulo', '')} — {escena.get('lugar', '')}{aviso}"
        evento = {"tipo": "escena", "accion": args.accion, **{k: escena.get(k) for k in ("numero", "titulo", "lugar", "hora")}}
        if args.cierre:
            evento["cierre"] = args.cierre
    else:
        celda = None
        if args.celda and not args.quitar:
            if not escena.get("mapa"):
                raise ValueError("no hay mapa de zona: dibújalo con `mapa zona --dibujo ...` o fija la posición solo con texto")
            celda = mapas.validar_celda(escena["mapa"], args.celda)
        donde = args.donde or f"casilla {celda}"
        posiciones = escena.setdefault("posiciones", [])
        posiciones[:] = [p for p in posiciones if norm(p["quien"]) != norm(args.quien)]
        if not args.quitar:
            posiciones.append({"quien": args.quien, "donde": donde, **({"celda": celda} if celda else {})})
        texto = f"{args.quien}: {'fuera de escena' if args.quitar else donde}{f' [{celda}]' if celda and args.donde else ''}"
        evento = {"tipo": "posicion", "quien": args.quien, "donde": None if args.quitar else donde, **({"celda": celda} if celda else {})}
    _cerrar(args, slug, datos, evento, texto)


def c_hecho(args) -> None:
    slug, datos = _cargar(args)
    if args.accion == "listar":
        print(memoria.listado(datos, args.todos))
        return
    evento, texto = memoria.aplicar(
        datos, args.accion, ident=getattr(args, "id", None), texto=getattr(args, "texto", None),
        categoria=getattr(args, "categoria", None), fijado=getattr(args, "fijar", False),
    )
    _cerrar(args, slug, datos, evento, texto)


def c_memoria(args) -> None:
    slug, datos = _cargar(args)
    if args.accion == "ver":
        print(memoria.ver(datos, args.todo))
        return
    if args.accion == "presupuesto":
        evento, texto = memoria.fijar_presupuesto(datos, args.caracteres)
    else:
        evento, texto = memoria.aplicar(datos, args.accion, texto=args.texto, numero=getattr(args, "numero", None))
    _cerrar(args, slug, datos, evento, texto)


def c_mapa(args) -> None:
    slug, datos = _cargar(args)
    escena = datos.setdefault("escena", {})
    if args.accion == "ver":
        print(mapas.zona_texto(datos) or "Sin mapa de zona: `mapa zona --dibujo \"#####\\n#...#\\n#####\"`.")
        return
    if args.accion == "catalogo":
        items = mapas.leer_catalogo_mapas(args.consulta or "")
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
            return
        if not items:
            print("Sin mapas en biblioteca/mapas para esa búsqueda.")
            return
        for x in items:
            print(f"{x['id']:<24} [{x.get('ambito', 'zona')} · {x.get('formato', '')} · {x.get('dimensiones', '')}] {x.get('nombre', '')} — {x.get('licencia', '')}")
            if x.get("descripcion"):
                print(f"  {x['descripcion']}")
        return
    if args.accion == "cargar":
        ambito, info = mapas.cargar_mapa_catalogo(datos, args.id, slug=slug, nombre=args.nombre)
        if ambito == "mundo":
            # El mundo no recoloca fichas: solo se elige entre el texto entero o la línea.
            _cerrar(args, slug, datos, {"tipo": "mundo", "accion": "cargar", **info},
                    mapas.mundo_texto(datos) if comunes._lote is None else f"Mapa del mundo cargado ({info['id']}).")
            return
        evento = {"tipo": "mapa", "accion": "cargar", **info}
        _cerrar_mapa(args, slug, datos, evento,
                     f"Mapa de zona cargado ({info['id']}, {info['columnas']}×{info['filas']} casillas).")
        return
    if args.accion == "importar":
        escena["mapa"] = mapas.importar_zona_archivo(
            args.archivo, slug=slug, nombre=args.nombre,
            celda=args.celda, luz=args.luz, licencia=args.licencia, fuente=args.fuente,
        )
        filas = escena["mapa"]["filas"]
        orig = escena["mapa"].get("origen") or {}
        evento = {"tipo": "mapa", "accion": "importar", "nombre": escena["mapa"].get("nombre"),
                  "columnas": len(filas[0]), "filas": len(filas), "fondo": escena["mapa"].get("fondo"), **orig}
        _cerrar_mapa(args, slug, datos, evento,
                     f"Mapa de zona importado ({len(filas[0])}×{len(filas)} casillas).")
        return
    if args.accion == "linea":
        res, texto = mapas.consultar_linea(datos, args.origen, args.destino)
        _imprimir(args, res, texto)
        return
    if args.accion == "area":
        res, texto = mapas.consultar_area(datos, args.forma, args.tamano, args.origen, hacia=args.hacia, ancho=args.ancho)
        _imprimir(args, res, texto)
        return
    if args.accion == "quitar":
        escena.pop("mapa", None)
        for p in escena.get("posiciones") or []:
            p.pop("celda", None)
        _cerrar(args, slug, datos, {"tipo": "mapa", "accion": "quitar"}, "Mapa de zona retirado.")
        return
    if args.accion == "terreno":
        dificil = True if args.dificil else (False if args.normal else None)
        bloq_paso = True if args.bloquea_paso else (False if args.paso_libre else None)
        bloq_vis = True if args.bloquea_vision else (False if args.vision_libre else None)
        sem = mapas.poner_terreno(
            escena.get("mapa"), args.caracter,
            cobertura=args.cobertura, dificil=dificil,
            bloquea_paso=bloq_paso, bloquea_vision=bloq_vis,
        )
        sig = (escena["mapa"].get("leyenda") or {}).get(args.caracter, args.caracter)
        res_txt = mapas._resumen_terreno(sem) or "suelo normal"
        texto = f"Terreno '{args.caracter}' ({sig}): {res_txt}"
        evento = {"tipo": "mapa", "accion": "terreno", "caracter": args.caracter, **sem}
        _cerrar(args, slug, datos, evento, texto)
        return
    if args.accion == "luz":
        res = mapas.poner_luz(escena.get("mapa"), args.nivel, args.foco, args.limpiar_focos)
        focos_txt = f" ({len(res['luces'])} focos)" if res["luces"] else ""
        texto = f"Luz de la zona: {res['luz']}{focos_txt}"
        evento = {"tipo": "mapa", "accion": "luz", **res}
        _cerrar(args, slug, datos, evento, texto)
        return
    anterior = escena.get("mapa")
    if args.accion == "generar":
        escena["mapa"] = mapas.generar_zona(
            args.tipo, semilla=args.semilla, ancho=args.ancho, alto=args.alto,
            densidad=args.densidad, celda=args.celda, nombre=args.nombre,
            luz=args.luz, anterior=anterior,
        )
        filas = escena["mapa"]["filas"]
        gen = escena["mapa"]["generador"]
        evento = {"tipo": "mapa", "accion": "generar", "nombre": escena["mapa"].get("nombre"), **gen}
        _cerrar_mapa(args, slug, datos, evento,
                     f"Mapa de zona generado ({gen['tipo']}, {len(filas[0])}×{len(filas)} casillas, semilla {gen['semilla']}).")
        return
    if args.dibujo is None and not anterior:
        raise ValueError('falta --dibujo: una fila por línea, p. ej. --dibujo "#####\\n#...#\\n#####"')
    dibujo = args.dibujo if args.dibujo is not None else "\n".join(anterior["filas"])
    escena["mapa"] = mapas.nueva_zona(dibujo, args.leyenda, args.celda, args.nombre, anterior=anterior, luz=args.luz)
    filas = escena["mapa"]["filas"]
    evento = {"tipo": "mapa", "accion": "zona", "nombre": escena["mapa"].get("nombre"),
              "columnas": len(filas[0]), "filas": len(filas)}
    _cerrar_mapa(args, slug, datos, evento, f"Mapa de zona dibujado ({len(filas[0])}×{len(filas)} casillas).")


def c_mundo(args) -> None:
    slug, datos = _cargar(args)
    if args.accion == "ver":
        print(mapas.mundo_texto(datos) or "Sin mapa del mundo: `mundo lugar \"<nombre>\" --x N --y N --tipo pueblo`.")
        return
    if args.accion == "viaje":
        res, texto = mapas.consultar_viaje(datos, args.de, args.a, ritmo=args.ritmo)
        _imprimir(args, res, texto)
        return
    if args.accion == "lugar":
        visitado = True if args.visitado else None
        lugar, nuevo = mapas.poner_lugar(datos, args.nombre, args.x, args.y, args.tipo, args.nota, en=args.en, visitado=visitado)
        en_txt = f" en {lugar['en']}" if lugar.get("en") else ""
        texto = f"{'Lugar nuevo' if nuevo else 'Lugar'} en el mapa del mundo: {lugar['nombre']} ({lugar.get('tipo')}{en_txt}, {mapas.cifra(lugar['x'])}·{mapas.cifra(lugar['y'])})"
        evento = {"tipo": "mundo", "accion": "lugar", "id": lugar["id"], "nombre": lugar["nombre"], "nuevo": nuevo}
    elif args.accion == "ruta":
        ruta = mapas.poner_ruta(datos, args.de, args.a, args.tipo, args.tiempo, args.distancia, args.quitar, trazo=args.trazo, ritmo=args.ritmo)
        det = mapas._detalle_ruta(ruta)
        extra = f" ({det})" if det and not args.quitar else ""
        texto = f"Ruta {'quitada' if args.quitar else 'en el mapa'}: {args.de} – {args.a}{extra}"
        evento = {"tipo": "mundo", "accion": "ruta", "de": ruta["de"], "a": ruta["a"], "quitada": bool(args.quitar)}
    elif args.accion == "region":
        reg = mapas.poner_region(datos, args.nombre, bioma=args.bioma, puntos=args.puntos, nota=args.nota, en=args.en, quitar=args.quitar)
        texto = f"Región {'quitada' if args.quitar else 'en el mapa'}: {reg['nombre']} ({reg.get('bioma')})"
        evento = {"tipo": "mundo", "accion": "region", "id": reg["id"], "nombre": reg["nombre"], "bioma": reg.get("bioma"), "quitada": bool(args.quitar)}
    elif args.accion == "trazo":
        trazo = mapas.poner_trazo(datos, args.nombre, tipo=args.tipo, puntos=args.puntos, nota=args.nota, en=args.en, quitar=args.quitar)
        texto = f"Trazo {'quitado' if args.quitar else 'en el mapa'}: {trazo['nombre']} ({trazo.get('tipo')}, {mapas.cifra(trazo.get('longitud', 0))} km)"
        evento = {"tipo": "mundo", "accion": "trazo", "id": trazo["id"], "nombre": trazo["nombre"], "tipo": trazo.get("tipo"), "quitado": bool(args.quitar)}
    elif args.accion == "generar":
        gen = mapas.generar_mundo(datos, semilla=args.semilla, bioma=args.bioma, lugares_n=args.lugares, en=args.en, nombre=args.nombre)
        texto = mapas.mundo_texto(datos) if comunes._lote is None else f"Mapa del mundo generado (semilla {gen['semilla']}, {gen['lugares']} lugares)."
        evento = {"tipo": "mundo", "accion": "generar", **gen}
    elif args.accion == "importar":
        res = mapas.importar_mundo_archivo(datos, args.archivo, nombre=args.nombre, licencia=args.licencia, fuente=args.fuente)
        texto = mapas.mundo_texto(datos) if comunes._lote is None else f"Mapa del mundo importado ({res['lugares']} lugares, {res['regiones']} regiones)."
        evento = {"tipo": "mundo", "accion": "importar", **res}
    elif args.accion == "aqui":
        lugar = mapas.ir_a(datos, args.nombre)
        texto = f"Ahora están en: {lugar['nombre']}"
        evento = {"tipo": "mundo", "accion": "aqui", "id": lugar["id"], "nombre": lugar["nombre"]}
    elif args.accion == "quitar":
        lugar = mapas.quitar_lugar(datos, args.nombre)
        texto = f"{lugar['nombre']} sale del mapa del mundo (y sus rutas)"
        evento = {"tipo": "mundo", "accion": "quitar", "id": lugar["id"], "nombre": lugar["nombre"]}
    else:
        m = mapas.ajustar_mundo(datos, args.nombre, args.unidad)
        texto = f"Mapa del mundo: {m.get('nombre') or 'sin nombre'} (coordenadas en {m['unidad']})"
        evento = {"tipo": "mundo", "accion": "ajustar", "nombre": m.get("nombre"), "unidad": m["unidad"]}
    _cerrar(args, slug, datos, evento, texto)


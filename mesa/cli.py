"""CLI `mesa`: la herramienta que usa el director (humano o IA) durante la partida.

Cada comando que tira dados o cambia el estado deja un evento en la bitácora,
y el visor (`mesa servir`) lo muestra en vivo.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import dados, estado, imagenes, informes, lecciones, reglas
from .texto import con_signo, norm


def _bono(texto: str) -> tuple[int, str]:
    valor, _, fuente = texto.partition(":")
    try:
        return int(valor), fuente.strip()
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"bono inválido {texto!r}: usa N o N:fuente (p. ej. 2:ayuda)") from e


def _imprimir(args, evento: dict, texto: str) -> None:
    print(json.dumps(evento, ensure_ascii=False, indent=2) if args.json else texto)


def _cargar(args) -> tuple[str, dict]:
    slug = estado.slug_activo(args.partida)
    return slug, estado.cargar(slug)


def _cerrar(args, slug: str, datos: dict, evento: dict, texto: str) -> None:
    estado.guardar(slug, datos)
    _imprimir(args, estado.registrar(slug, evento), texto)


# ---------- partidas ----------

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
    print(json.dumps(datos, ensure_ascii=False, indent=2) if args.json else informes.resumen(datos))


def c_contexto(args) -> None:
    print(informes.contexto(estado.slug_activo(args.partida), args.completo, args.eventos))


# ---------- dados ----------

def c_tirar(args) -> None:
    slug = estado.slug_activo(args.partida)
    r = dados.tirar(args.expr, critico=args.critico)
    evento = {"tipo": "tirada", "quien": args.quien, "etiqueta": args.etiqueta, **r}
    valores = " ".join(f"{t['dado']}:{t['valores']}" for t in r["dados"])
    texto = f"{args.etiqueta or 'Tirada'}: {args.expr}{' (crítico)' if args.critico else ''} → {valores}"
    texto += f" {con_signo(r['modificador'])}" if r["modificador"] else ""
    _imprimir(args, estado.registrar(slug, evento), f"{texto} = {r['total']}")


def c_prueba(args) -> None:
    slug, datos = _cargar(args)
    _, ficha = estado.buscar(datos, args.quien)
    evento = reglas.prueba(
        datos, ficha, args.atributo, cd=args.cd, ventaja=args.ventaja, desventaja=args.desventaja,
        bonos=args.bono, oficio=args.oficio, usar=args.usar, etiqueta=args.etiqueta or "",
    )
    _cerrar(args, slug, datos, evento, reglas.describir_prueba(evento))


def c_ataque(args) -> None:
    slug, datos = _cargar(args)
    _, atacante = estado.buscar(datos, args.quien)
    _, objetivo = estado.buscar(datos, args.objetivo)
    evento = reglas.ataque(
        datos, atacante, objetivo, arma=args.arma, ventaja=args.ventaja, desventaja=args.desventaja,
        bonos=args.bono, oficio=args.oficio, cobertura=args.cobertura, atributo=args.atributo,
        etiqueta=args.etiqueta or "",
    )
    _cerrar(args, slug, datos, evento, reglas.describir_prueba(evento))


def c_dano(args) -> None:
    slug, datos = _cargar(args)
    _, ficha = estado.buscar(datos, args.quien)
    expr = args.expr or reglas.buscar_arma(ficha, args.arma)["dano"]
    objetivo = estado.buscar(datos, args.objetivo)[1] if args.objetivo else None
    r = reglas.dano(datos, expr, objetivo, critico=args.critico)
    evento = {"tipo": "dano", "quien": ficha["nombre"], "etiqueta": args.etiqueta, "arma": args.arma, **r["tirada"], **{k: v for k, v in r.items() if k != "tirada"}}
    valores = " + ".join(str(v) for t in r["tirada"]["dados"] for v in t["valores"])
    texto = f"Daño de {ficha['nombre']}: {expr}{' (crítico)' if args.critico else ''} → {valores} = {r['bruto']}"
    if objetivo is not None:
        texto += f" − protección {r['proteccion']} = {r['final']} → {objetivo['nombre']} {r['vida']['despues']}/{r['vida']['maximo']}"
    _cerrar(args, slug, datos, evento, texto)


def c_suerte(args) -> None:
    slug = estado.slug_activo(args.partida)
    if not 0 <= args.probabilidad <= 100:
        raise ValueError("la probabilidad va de 0 a 100")
    valor = dados.tirar_dado(100)
    exito = valor <= args.probabilidad
    evento = {"tipo": "suerte", "etiqueta": args.etiqueta, "probabilidad": args.probabilidad, "valor": valor, "exito": exito}
    _imprimir(args, estado.registrar(slug, evento), f"{args.etiqueta}: d100 = {valor} contra {args.probabilidad}% → {'sí' if exito else 'no'}")


# ---------- fichas ----------

def c_vida(args) -> None:
    slug, datos = _cargar(args)
    _, ficha = estado.buscar(datos, args.quien)
    cambio = reglas.aplicar_vida(ficha, args.delta)
    evento = {"tipo": "vida", "quien": ficha["nombre"], "delta": args.delta, "motivo": args.motivo, **cambio}
    _cerrar(args, slug, datos, evento, f"{ficha['nombre']}: vida {cambio['antes']} → {cambio['despues']}/{cambio['maximo']}")


def c_condicion(args) -> None:
    slug, datos = _cargar(args)
    _, ficha = estado.buscar(datos, args.quien)
    lista = ficha.setdefault("condiciones", [])
    if args.accion == "agregar":
        cond = reglas.condicion_de_catalogo(args.nombre) or {"nombre": args.nombre.strip()}
        if args.efecto:
            cond["efecto"] = args.efecto
        if args.desventaja:
            cond["desventaja"] = [norm(x) for x in args.desventaja.split(",")]
        if args.ventaja_contra:
            cond["ventaja_contra"] = True
        if args.niveles:
            cond["niveles"] = args.niveles
        lista[:] = [c for c in lista if norm(c["nombre"]) != norm(cond["nombre"])] + [cond]
        texto = f"{ficha['nombre']} queda {cond['nombre']}: {cond.get('efecto', '')}"
    else:
        antes = len(lista)
        lista[:] = [c for c in lista if norm(c["nombre"]) != norm(args.nombre)]
        if len(lista) == antes:
            raise ValueError(f"{ficha['nombre']} no tiene la condición {args.nombre!r}")
        texto = f"{ficha['nombre']} ya no está {args.nombre}"
    _cerrar(args, slug, datos, {"tipo": "condicion", "quien": ficha["nombre"], "accion": args.accion, "nombre": args.nombre}, texto)


def c_habilidad(args) -> None:
    slug, datos = _cargar(args)
    _, ficha = estado.buscar(datos, args.quien)
    hab = reglas.buscar_habilidad(ficha, args.nombre)
    hab["disponible"] = bool(args.recargar)
    texto = f"{ficha['nombre']}: «{hab['nombre']}» {'disponible' if hab['disponible'] else 'gastada'}"
    _cerrar(args, slug, datos, {"tipo": "habilidad", "quien": ficha["nombre"], "nombre": hab["nombre"], "disponible": hab["disponible"]}, texto)


def c_enemigo(args) -> None:
    slug, datos = _cargar(args)
    lista = datos.setdefault("enemigos", [])
    if args.accion == "agregar":
        base = dict(reglas.PLANTILLAS_ENEMIGO.get(norm(args.plantilla or ""), {}))
        for campo in ("vida", "defensa", "ataque", "dano", "proteccion"):
            if getattr(args, campo) is not None:
                base[campo] = getattr(args, campo)
        if "vida" not in base:
            raise ValueError("indica --vida o una --plantilla (rata, perro, maton, guardia)")
        base.update({"nombre": args.nombre, "vida_max": base["vida"], "condiciones": []})
        base.setdefault("defensa", 10)
        lista.append(base)
        texto = f"Amenaza en escena: {args.nombre} (vida {base['vida']}, defensa {base['defensa']}, daño {base.get('dano', '-')})"
    elif args.accion == "quitar":
        _, ficha = estado.buscar({"enemigos": lista}, args.nombre)
        lista.remove(ficha)
        texto = f"{ficha['nombre']} sale de escena"
    else:
        lista.clear()
        texto = "Sin amenazas en escena"
    _cerrar(args, slug, datos, {"tipo": "enemigo", "accion": args.accion, "nombre": args.nombre}, texto)


def c_nivel(args) -> None:
    slug, datos = _cargar(args)
    _, ficha = estado.buscar(datos, args.quien)
    if args.atributo:
        attr, _ = reglas.resolver_atributo(args.atributo)
        maximo = int(datos.get("reglas", {}).get("atributo_maximo", 4))
        if ficha["atributos"][attr] >= maximo:
            raise ValueError(f"{reglas.NOMBRE_ATRIBUTO[attr]} ya está en el máximo ({con_signo(maximo)})")
    ficha["nivel"] = int(ficha.get("nivel", 1)) + 1
    ficha["vida_max"] = int(ficha["vida_max"]) + 2
    ficha["vida"] = min(ficha["vida_max"], int(ficha["vida"]) + 2)
    if args.atributo:
        ficha["atributos"][attr] += 1
        mejora = f"{reglas.NOMBRE_ATRIBUTO[attr]} {con_signo(ficha['atributos'][attr])}"
    else:
        nombre, _, texto_hab = args.habilidad.partition(":")
        ficha.setdefault("habilidades", []).append({"nombre": nombre.strip(), "texto": texto_hab.strip(), "disponible": True})
        mejora = f"nueva habilidad «{nombre.strip()}»"
    texto = f"{ficha['nombre']} sube a nivel {ficha['nivel']}: vida {ficha['vida']}/{ficha['vida_max']}, {mejora}"
    _cerrar(args, slug, datos, {"tipo": "nivel", "quien": ficha["nombre"], "nivel": ficha["nivel"], "mejora": mejora}, texto)


# ---------- mundo ----------

def c_escena(args) -> None:
    slug, datos = _cargar(args)
    escena = datos.setdefault("escena", {})
    if args.accion == "nueva":
        escena.clear()
        escena["numero"] = int(datos.get("escenas_jugadas", 0)) + 1
        datos["escenas_jugadas"] = escena["numero"]
        for p in datos.get("personajes", []):
            for h in p.get("habilidades", []):
                if h.get("recarga") == "escena":
                    h["disponible"] = True
    if args.accion in ("nueva", "editar"):
        for campo in ("titulo", "lugar", "hora", "clima", "descripcion"):
            if getattr(args, campo):
                escena[campo] = getattr(args, campo)
        texto = f"Escena {escena.get('numero')}: {escena.get('titulo', '')} — {escena.get('lugar', '')}"
        evento = {"tipo": "escena", "accion": args.accion, **{k: escena.get(k) for k in ("numero", "titulo", "lugar", "hora")}}
    else:
        posiciones = escena.setdefault("posiciones", [])
        posiciones[:] = [p for p in posiciones if norm(p["quien"]) != norm(args.quien)]
        if not args.quitar:
            posiciones.append({"quien": args.quien, "donde": args.donde})
        texto = f"{args.quien}: {'fuera de escena' if args.quitar else args.donde}"
        evento = {"tipo": "posicion", "quien": args.quien, "donde": None if args.quitar else args.donde}
    _cerrar(args, slug, datos, evento, texto)


def c_pnj(args) -> None:
    slug, datos = _cargar(args)
    lista = datos.setdefault("pnj", [])
    pnj = next((n for n in lista if norm(n["nombre"]) == norm(args.nombre)), None)
    if pnj is None:
        pnj = {"nombre": args.nombre, "actitud": "indiferente", "notas": []}
        lista.append(pnj)
    for campo in ("rol", "actitud", "estado"):
        if getattr(args, campo):
            pnj[campo] = getattr(args, campo)
    if args.nota:
        pnj.setdefault("notas", []).append(args.nota)
    texto = f"PNJ {pnj['nombre']} ({pnj.get('actitud')}): {pnj.get('estado', '')} {args.nota or ''}".rstrip()
    _cerrar(args, slug, datos, {"tipo": "pnj", "nombre": pnj["nombre"], "actitud": pnj.get("actitud"), "nota": args.nota}, texto)


def c_pista(args) -> None:
    slug, datos = _cargar(args)
    datos.setdefault("pistas", []).append({"texto": args.texto, "fuente": args.fuente})
    _cerrar(args, slug, datos, {"tipo": "pista", "texto": args.texto}, f"Pista: {args.texto}")


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


def c_turno(args) -> None:
    slug = estado.slug_activo(args.partida)
    acciones = {}
    for item in args.accion or []:
        quien, _, que = item.partition("=")
        acciones[quien.strip()] = que.strip()
    evento = estado.registrar(slug, {"tipo": "turno", "acciones": acciones, "resumen": args.resumen})
    _imprimir(args, evento, f"Turno {evento['seq']} registrado.")


def c_regla(args) -> None:
    slug, datos = _cargar(args)
    lista = datos.setdefault("reglas_casa", [])
    regla = {"id": f"R{len(lista) + 1}", "texto": args.texto, "desde": estado.ahora()[:10]}
    lista.append(regla)
    _cerrar(args, slug, datos, {"tipo": "regla", **regla}, f"Regla de la casa {regla['id']}: {args.texto}")


def c_nota(args) -> None:
    slug = estado.slug_activo(args.partida)
    _imprimir(args, estado.registrar(slug, {"tipo": "nota", "texto": args.texto}), "Nota registrada.")


# ---------- imágenes, guardado, lecciones ----------

def c_imagen(args) -> None:
    slug = estado.slug_activo(args.partida)
    if args.accion == "ninguna":
        e = imagenes.tarjeta_svg(slug)
        _imprimir(args, e, f"Tarjeta de escena: {e['archivo']}")
    elif args.accion == "elegir":
        e = imagenes.elegir(slug, args.fuente)
        _imprimir(args, e, f"Imagen elegida: {e['archivo']} ({e['origen']})")
    elif args.accion == "buscar":
        resultados = imagenes.buscar(args.consulta)
        if args.json:
            print(json.dumps(resultados, ensure_ascii=False, indent=2))
        for r in resultados if not args.json else []:
            print(f"{r['id']:<28} [{', '.join(r.get('etiquetas', []))}] {r.get('descripcion', '')} — {r.get('licencia', '')}")
        if not resultados and not args.json:
            print("Sin coincidencias en biblioteca/imagenes (añade con `mesa imagen biblioteca-agregar`).")
    elif args.accion == "generar":
        r = imagenes.generar(slug, args.prompt, args.proveedor, args.modelo, simular=args.simular)
        if r.get("simulado"):
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            _imprimir(args, r, f"Imagen generada: {r['archivo']} ({r['origen']})")
    else:
        item = imagenes.agregar_biblioteca(
            args.ruta, [t.strip() for t in (args.etiquetas or "").split(",") if t.strip()],
            args.descripcion or "", args.fuente or "", args.licencia or "",
        )
        print(f"En biblioteca: {item['id']} ({item['archivo']})")


def c_guardar(args) -> None:
    texto, ruta = informes.guardado(estado.slug_activo(args.partida))
    print(texto)
    print(f"(guardado en {ruta})")


def c_leccion(args) -> None:
    if args.accion == "agregar":
        item = lecciones.agregar(args.texto, args.alcance, args.categoria, args.evidencia, args.origen or "")
        print(f"{item['id']} añadida ({item['alcance']}/{item['categoria']}).")
    elif args.accion == "retirar":
        item = lecciones.retirar(args.id, args.motivo)
        print(f"{item['id']} retirada: {args.motivo}")
    else:
        items = [i for i in lecciones.leer() if args.todas or i["estado"] == "activa"]
        if args.alcance:
            items = [i for i in items if i["alcance"] == args.alcance]
        print(json.dumps(items, ensure_ascii=False, indent=2) if args.json else lecciones.como_markdown(items))


def c_retro(args) -> None:
    print(informes.retro(estado.slug_activo(args.partida)))


def c_servir(args) -> None:
    from . import servidor

    servidor.servir(args.host, args.puerto)


# ---------- parser ----------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mesa", description="Herramientas del director para la mesa de rol.")
    p.add_argument("-p", "--partida", help="slug de la partida (por defecto, la activa)")
    p.add_argument("--json", action="store_true", help="salida en JSON")
    sub = p.add_subparsers(dest="comando", required=True, metavar="COMANDO")

    def cmd(nombre, funcion, ayuda):
        s = sub.add_parser(nombre, help=ayuda, description=ayuda)
        s.set_defaults(funcion=funcion)
        return s

    cmd("partidas", c_partidas, "lista las partidas")
    s = cmd("usar", c_usar, "marca la partida activa"); s.add_argument("slug")
    s = cmd("nueva", c_nueva, "crea una partida desde la plantilla"); s.add_argument("slug"); s.add_argument("--titulo", required=True)
    cmd("estado", c_estado, "resumen del estado actual")
    s = cmd("contexto", c_contexto, "contexto del director: lecciones, reglas de la casa, estado y últimos eventos")
    s.add_argument("--completo", action="store_true", help="incluye biblia, notas del director y reglamento")
    s.add_argument("--eventos", type=int, default=15)

    def opciones_d20(s):
        s.add_argument("--ventaja", nargs="?", const=True, default=False, metavar="MOTIVO")
        s.add_argument("--desventaja", nargs="?", const=True, default=False, metavar="MOTIVO")
        s.add_argument("--bono", type=_bono, action="append", default=[], metavar="N[:FUENTE]")
        s.add_argument("--oficio", action="store_true", help="suma el bono de oficio de la partida")
        s.add_argument("--etiqueta", help="qué se intenta, en pocas palabras")

    s = cmd("tirar", c_tirar, "tira una expresión: 1d20+3, 2d6, d100, 1d8+1d4")
    s.add_argument("expr"); s.add_argument("--quien"); s.add_argument("--etiqueta"); s.add_argument("--critico", action="store_true")
    s = cmd("prueba", c_prueba, "prueba d20 de atributo o habilidad contra una dificultad")
    s.add_argument("quien"); s.add_argument("atributo", help="fuerza, agilidad, ingenio, corazón o una habilidad (sigilo, percepción...)")
    s.add_argument("--cd", "--dc", help="número o: muy-facil, facil, media, dificil, muy-dificil, casi-imposible")
    s.add_argument("--usar", metavar="HABILIDAD", help="gasta una habilidad de la ficha y suma su bono")
    opciones_d20(s)
    s = cmd("ataque", c_ataque, "ataque contra la Defensa de un objetivo; si acierta, aplica el daño")
    s.add_argument("quien"); s.add_argument("objetivo"); s.add_argument("--arma"); s.add_argument("--atributo")
    s.add_argument("--cobertura", choices=["media", "tres-cuartos"])
    opciones_d20(s)
    s = cmd("dano", c_dano, "tira daño de un arma o expresión y lo aplica al objetivo")
    s.add_argument("quien"); s.add_argument("--arma"); s.add_argument("--expr"); s.add_argument("--objetivo")
    s.add_argument("--critico", action="store_true"); s.add_argument("--etiqueta")
    s = cmd("suerte", c_suerte, "d100 contra un porcentaje, para lo que no depende de nadie")
    s.add_argument("probabilidad", type=int); s.add_argument("--etiqueta", required=True)

    s = cmd("vida", c_vida, "suma o resta vida: mesa vida Jualjin -3"); s.add_argument("quien"); s.add_argument("delta", type=int); s.add_argument("--motivo")
    s = cmd("condicion", c_condicion, "agrega o quita una condición (catálogo: guias/condiciones.md)")
    s.add_argument("quien"); s.add_argument("accion", choices=["agregar", "quitar"]); s.add_argument("nombre")
    s.add_argument("--efecto"); s.add_argument("--desventaja", help="atributos afectados, separados por coma, o 'todo'/'ataques'")
    s.add_argument("--ventaja-contra", action="store_true"); s.add_argument("--niveles", type=int)
    s = cmd("habilidad", c_habilidad, "marca una habilidad como gastada o recargada")
    s.add_argument("quien"); s.add_argument("nombre"); g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--usar", action="store_true"); g.add_argument("--recargar", action="store_true")
    s = cmd("enemigo", c_enemigo, "amenazas en escena")
    s.add_argument("accion", choices=["agregar", "quitar", "limpiar"]); s.add_argument("nombre", nargs="?", default="")
    s.add_argument("--plantilla", help="rata, perro, maton, guardia"); s.add_argument("--vida", type=int); s.add_argument("--defensa", type=int)
    s.add_argument("--ataque", type=int); s.add_argument("--dano"); s.add_argument("--proteccion", type=int)
    s = cmd("nivel", c_nivel, "sube de nivel tras un hito: +2 vida máx. y +1 atributo o una habilidad nueva")
    s.add_argument("quien"); g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--atributo"); g.add_argument("--habilidad", help="'Nombre: qué hace'")

    s = cmd("escena", c_escena, "nueva escena, editarla o fijar posiciones")
    s.add_argument("accion", choices=["nueva", "editar", "posicion"])
    s.add_argument("quien", nargs="?"); s.add_argument("donde", nargs="?")
    for campo in ("titulo", "lugar", "hora", "clima", "descripcion"):
        s.add_argument(f"--{campo}")
    s.add_argument("--quitar", action="store_true")
    s = cmd("pnj", c_pnj, "crea o actualiza un PNJ visible para los jugadores")
    s.add_argument("nombre"); s.add_argument("--rol"); s.add_argument("--actitud", choices=["amistosa", "indiferente", "hostil"])
    s.add_argument("--estado"); s.add_argument("--nota")
    s = cmd("pista", c_pista, "anota una pista descubierta"); s.add_argument("texto"); s.add_argument("--fuente")
    s = cmd("trama", c_trama, "abre, cambia o cierra una trama"); s.add_argument("nombre")
    s.add_argument("--estado", choices=["activa", "latente", "cerrada", "sin-abrir"]); s.add_argument("--nota")
    s = cmd("misterio", c_misterio, "pregunta abierta que los jugadores conocen"); s.add_argument("texto"); s.add_argument("--resolver", action="store_true")
    s = cmd("recurso", c_recurso, "fija o suma un recurso compartido (sin valor: lo quita)")
    s.add_argument("clave"); s.add_argument("valor", nargs="?"); s.add_argument("--sumar", type=int)
    s = cmd("reloj", c_reloj, "día, hora y plazos"); s.add_argument("--dia", type=int); s.add_argument("--hora")
    s.add_argument("--plazo", action="append"); s.add_argument("--quitar-plazo", action="append")
    s = cmd("turno", c_turno, "registra lo que declaró cada jugador y lo que pasó")
    s.add_argument("--accion", action="append", metavar="NOMBRE=TEXTO"); s.add_argument("--resumen", required=True)
    s = cmd("regla", c_regla, "añade una regla de la casa acordada en la mesa"); s.add_argument("texto")
    s = cmd("nota", c_nota, "nota libre en la bitácora"); s.add_argument("texto")

    s = cmd("imagen", c_imagen, "imagen de la escena: ninguna | elegir | buscar | generar | biblioteca-agregar")
    isub = s.add_subparsers(dest="accion", required=True)
    isub.add_parser("ninguna", help="tarjeta SVG local, sin red")
    e = isub.add_parser("elegir", help="id de biblioteca, ruta local o URL"); e.add_argument("fuente")
    e = isub.add_parser("buscar", help="busca en biblioteca/imagenes por etiquetas"); e.add_argument("consulta")
    e = isub.add_parser("generar", help="opcional: genera con un proveedor externo (gasta crédito)")
    e.add_argument("--prompt"); e.add_argument("--proveedor", choices=list(imagenes.MODELOS)); e.add_argument("--modelo")
    e.add_argument("--simular", action="store_true", help="muestra el prompt sin enviar nada")
    e = isub.add_parser("biblioteca-agregar", help="añade una imagen a la biblioteca compartida")
    e.add_argument("ruta"); e.add_argument("--etiquetas"); e.add_argument("--descripcion"); e.add_argument("--fuente"); e.add_argument("--licencia")

    cmd("guardar", c_guardar, "«guardar partida»: resumen copiable + archivo en guardados/")
    s = cmd("leccion", c_leccion, "lecciones aprendidas entre historias")
    lsub = s.add_subparsers(dest="accion", required=True)
    e = lsub.add_parser("agregar"); e.add_argument("texto"); e.add_argument("--alcance", required=True)
    e.add_argument("--categoria", required=True, choices=lecciones.CATEGORIAS); e.add_argument("--evidencia", required=True); e.add_argument("--origen")
    e = lsub.add_parser("listar"); e.add_argument("--alcance"); e.add_argument("--todas", action="store_true")
    e = lsub.add_parser("retirar"); e.add_argument("id"); e.add_argument("--motivo", required=True)
    cmd("retro", c_retro, "estadísticas de la partida y plantilla de retrospectiva")
    s = cmd("servir", c_servir, "abre el visor local"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--puerto", type=int, default=8765)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        args.funcion(args)
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0

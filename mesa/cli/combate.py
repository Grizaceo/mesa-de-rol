"""Dados, pruebas, combate y fichas."""

from __future__ import annotations

from .. import dados, esquemas, estado, reglas, reglas_2024, vista
from ..texto import con_signo, norm
from .comunes import _cargar, _cerrar, _imprimir, _recargar

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
        salvacion=getattr(args, "salvacion", False),
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
    arma_elegida = reglas.buscar_arma(ficha, args.arma) if not args.expr else None
    expr = args.expr or arma_elegida["dano"]
    tipo_dano = getattr(args, "tipo_dano", None) or (arma_elegida or {}).get("tipo_dano")
    objetivo = estado.buscar(datos, args.objetivo)[1] if args.objetivo else None
    r = reglas.dano(datos, expr, objetivo, critico=args.critico, tipo_dano=tipo_dano)
    evento = {"tipo": "dano", "quien": ficha["nombre"], "etiqueta": args.etiqueta, "arma": args.arma, **r["tirada"], **{k: v for k, v in r.items() if k != "tirada"}}
    valores = " + ".join(str(v) for t in r["tirada"]["dados"] for v in t["valores"])
    texto = f"Daño de {ficha['nombre']}: {expr}{' (crítico)' if args.critico else ''} → {valores} = {r['bruto']}"
    if objetivo is not None:
        if esquemas.version_de(datos) == esquemas.VERSION_2024:
            ajuste = f" [{r['ajuste_resistencia']}]" if r.get("ajuste_resistencia") else ""
            texto += f"{ajuste} → {r['final']} → {objetivo['nombre']} {r['vida']['despues']}/{r['vida']['maximo']}"
        else:
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
    if getattr(args, "temporal", False):
        cambio = reglas_2024.fijar_vida_temporal(ficha, args.delta)
        evento = {"tipo": "vida_temporal", "quien": ficha["nombre"], "cantidad": args.delta, "motivo": args.motivo, **cambio}
        _cerrar(args, slug, datos, evento, f"{ficha['nombre']}: PG temporales {cambio['antes']} → {cambio['despues']}")
        return
    if getattr(args, "revivir", False):
        ficha.pop("muerto", None)
        ficha.pop("salvaciones_muerte", None)
    cambio = reglas.aplicar_vida(ficha, args.delta, partida=datos)
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


def c_vendaje(args) -> None:
    slug, datos = _cargar(args)
    _, ficha = estado.buscar(datos, args.quien)
    if ficha.get("vendaje_usado"):
        raise ValueError(f"{ficha['nombre']} ya usó su vendaje: vuelve a tenerlo tras un descanso")
    en_pie = [e["nombre"] for e in datos.get("enemigos", []) if int(e.get("vida", 0)) > 0]
    if en_pie:
        raise ValueError(f"el vendaje es fuera de combate y hay amenazas en escena ({', '.join(en_pie)}); si terminó, `enemigo limpiar`")
    cambio = reglas.aplicar_vida(ficha, 3)
    ficha["vendaje_usado"] = True
    texto = f"Vendaje a {ficha['nombre']}: vida {cambio['antes']} → {cambio['despues']}/{cambio['maximo']}"
    _cerrar(args, slug, datos, {"tipo": "vendaje", "quien": ficha["nombre"], **cambio}, texto)


def c_descanso(args) -> None:
    slug, datos = _cargar(args)
    quienes = [estado.buscar(datos, q)[1] for q in args.quien] if args.quien else datos.get("personajes", [])
    if esquemas.version_de(datos) == esquemas.VERSION_2024:
        lineas = reglas_2024.descanso(datos, args.clase, quienes=quienes, dados_golpe=getattr(args, "dados_golpe", 0) or 0)
        texto = f"Descanso {args.clase}.\n" + "\n".join(f"  {l}" for l in lineas)
        _cerrar(args, slug, datos, {"tipo": "descanso", "clase": args.clase, "quien": [p["nombre"] for p in quienes], "cambios": lineas}, texto)
        return
    recargas = {"descanso"} if args.clase == "corto" else {"descanso", "escena", "combate", "dia"}
    lineas = []
    for p in quienes:
        cambios = []
        if args.clase == "largo":
            vida = reglas.aplicar_vida(p, int(p.get("vida_max", 0)))
            if vida["despues"] != vida["antes"]:
                cambios.append(f"vida {vida['antes']} → {vida['despues']}/{vida['maximo']}")
            for c in list(p.get("condiciones", [])):
                if norm(c["nombre"]) == "agotamiento":
                    c["niveles"] = int(c.get("niveles", 1)) - 1
                    if c["niveles"] <= 0:
                        p["condiciones"].remove(c)
                    cambios.append(f"agotamiento {c['niveles']}" if c["niveles"] > 0 else "sin agotamiento")
        if p.pop("vendaje_usado", None):
            cambios.append("vendaje disponible")
        cambios += [f"«{h}» disponible" for _, h in _recargar(datos, recargas, [p])]
        lineas.append(f"{p['nombre']}: {', '.join(cambios) or 'nada que recuperar'}")
    texto = f"Descanso {args.clase}.\n" + "\n".join(f"  {l}" for l in lineas)
    if args.clase == "largo":
        texto += "\n  (Dormir pide comida: si la gastan, `recurso Raciones --sumar -N`.)"
    _cerrar(args, slug, datos, {"tipo": "descanso", "clase": args.clase, "quien": [p["nombre"] for p in quienes], "cambios": lineas}, texto)


def c_enemigo(args) -> None:
    slug, datos = _cargar(args)
    lista = datos.setdefault("enemigos", [])
    if args.accion == "agregar":
        base = dict(reglas.PLANTILLAS_ENEMIGO.get(norm(args.plantilla or ""), {}))
        for campo in ("vida", "defensa", "ataque", "dano", "proteccion", "aspecto", "raza", "altura"):
            if getattr(args, campo, None) is not None:
                base[campo] = getattr(args, campo)
        if getattr(args, "conocido", False):
            base["conocido"] = True
        elif getattr(args, "desconocido", False):
            base["conocido"] = False
        if "vida" not in base:
            raise ValueError("indica --vida o una --plantilla (rata, perro, maton, guardia)")
        base.update({"nombre": args.nombre, "vida_max": base["vida"], "condiciones": []})
        base.setdefault("defensa", 10)
        lista.append(base)
        texto = f"Amenaza en escena: {args.nombre} (vida {base['vida']}, defensa {base['defensa']}, daño {base.get('dano', '-')})"
        alias = vista.politica(datos)["alias"].get(args.nombre)
        if alias:
            texto += f" · en el visor se ve como «{alias}» hasta `enemigo revelar`"
    elif args.accion == "revelar":
        ocultas = datos.get("identidades_ocultas") or {}
        ficha = next((e for e in lista if norm(e.get("nombre", "")) == norm(args.nombre)), None)
        real = ficha["nombre"] if ficha else next((k for k in ocultas if norm(k) == norm(args.nombre)), None)
        if real is None:
            raise ValueError(f"no hay amenaza ni identidad oculta llamada {args.nombre!r}")
        if ficha is not None:
            ficha["conocido"] = True
            if args.stats:
                ficha["revelar_stats"] = True
        ocultas.pop(real, None)
        if not ocultas:
            datos.pop("identidades_ocultas", None)
        texto = f"{real}: identidad revelada" + (" y estadísticas a la vista" if args.stats else "")
    elif args.accion == "quitar":
        _, ficha = estado.buscar({"enemigos": lista}, args.nombre)
        _guardar_identidades(datos, [ficha])
        lista.remove(ficha)
        texto = f"{ficha['nombre']} sale de escena"
    else:
        _guardar_identidades(datos, list(lista))
        lista.clear()
        texto = "Sin amenazas en escena"
    evento = {"tipo": "enemigo", "accion": args.accion, "nombre": args.nombre}
    if args.accion in ("quitar", "limpiar") and not lista:
        # Sin amenazas, el combate terminó: vuelven las habilidades «por combate».
        recargadas = [f"{p}: «{h}»" for p, h in _recargar(datos, {"combate"})]
        if recargadas:
            evento["recargadas"] = recargadas
            texto += f". Fin del combate: se recargan {'; '.join(recargadas)}"
    _cerrar(args, slug, datos, evento, texto)


def _guardar_identidades(datos: dict, fichas: list[dict]) -> None:
    """Quien sale de escena sin haberse revelado sigue oculto en la bitácora vieja del visor."""
    alias = vista.politica(datos)["alias"]
    ocultas = {f["nombre"]: alias[f["nombre"]] for f in fichas if f.get("nombre") in alias}
    if ocultas:
        datos.setdefault("identidades_ocultas", {}).update(ocultas)


def c_piloto(args) -> None:
    """Regla de la casa: el narrador lleva a un PJ mientras su jugador falta, o se lo devuelve."""
    slug, datos = _cargar(args)
    _, ficha = estado.buscar({"personajes": datos.get("personajes", [])}, args.quien)
    if args.lleva == "narrador":
        ficha["piloto"] = "narrador"
        texto = f"{ficha['nombre']}: lo lleva el narrador (regla de la casa) hasta que vuelva su jugador"
    else:
        ficha.pop("piloto", None)
        texto = f"{ficha['nombre']}: vuelve a jugarlo su jugador"
    _cerrar(args, slug, datos, {"tipo": "piloto", "quien": ficha["nombre"], "piloto": args.lleva}, texto)


def c_nivel(args) -> None:
    slug, datos = _cargar(args)
    reglas.exigir_legacy(datos)  # subir nivel es mecánica d20-simple: en 2024 no hay regla aún
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


def c_iniciativa(args) -> None:
    slug, datos = _cargar(args)
    orden = reglas_2024.tirar_iniciativa(datos)
    lineas = ["Orden de iniciativa:"] + [
        f"  {i}. {x['quien']}: {x['total']} (d20={x['elegido']}, mod {con_signo(x['modificador'])}, {x['modo']})"
        for i, x in enumerate(orden, start=1)
    ]
    _cerrar(args, slug, datos, {"tipo": "iniciativa", "orden": orden}, "\n".join(lineas))


def c_conjuro(args) -> None:
    slug, datos = _cargar(args)
    _, lanzador = estado.buscar(datos, args.quien)
    objetivos = [estado.buscar(datos, q)[1] for q in (args.objetivo or [])]
    ev = reglas_2024.lanzar_conjuro(datos, lanzador, args.conjuro, nivel_slot=args.nivel_slot, objetivos=objetivos)
    if ev.get("requiere_resolucion_manual"):
        texto = (
            f"{ev['quien']} lanza «{ev['conjuro']}» (espacio niv. {ev.get('nivel_slot', '?')}, CD {ev.get('cd', '?')}): "
            f"requiere resolución manual — {ev['referencia']}"
        )
    else:
        partes_obj = [
            f"{r['objetivo']}: salvación {r['salvacion']['total']} ({'éxito' if r['salvacion']['exito'] else 'fallo'}) → "
            f"{r['dano_final']} de daño ({r['vida']['despues']}/{r['vida']['maximo']})"
            for r in ev.get("resultados_objetivos", [])
        ]
        texto = f"{ev['quien']} lanza «{ev['conjuro']}» (CD {ev['cd']}): " + ("; ".join(partes_obj) or "resuelto")
    _cerrar(args, slug, datos, ev, texto)


def c_adjudicar(args) -> None:
    slug, datos = _cargar(args)
    ev = reglas_2024.adjudicar(
        datos, regla=args.regla, decision=args.decision, autor=args.autor, motivo=args.motivo or "",
    )
    texto = f"Adjudicación manual ({ev['autor']}) · {ev['regla']}: {ev['decision']}"
    _cerrar(args, slug, datos, ev, texto)


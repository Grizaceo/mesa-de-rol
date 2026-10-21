"""CLI `mesa`: la herramienta que usa el director (humano o IA) durante la partida.

Cada comando que tira dados o cambia el estado deja un evento en la bitácora,
y el visor (`mesa servir`) lo muestra en vivo.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from contextlib import nullcontext
from pathlib import Path

from . import (
    bloqueo, capacidades, chat, dados, distribucion, esquemas, estado, fuentes, harness, imagenes, informes, lecciones,
    mapas, memoria, migraciones, reglas, reglas_2024, sesion, vista,
)
from .texto import con_signo, norm

# Comandos que escriben estado de la partida: `main` les toma el candado del archivo
# (bloqueo.py) antes de cargar, para que dos procesos no se pisen a media transacción.
# Los de solo lectura no lo toman: el visor puede leer mientras alguien escribe.
ESCRIBEN = frozenset({
    "retomar", "pausar", "tirar", "suerte", "prueba", "ataque", "dano",
    "vida", "condicion", "habilidad", "vendaje", "descanso", "enemigo", "nivel", "piloto",
    "iniciativa", "conjuro", "adjudicar",
    "escena", "pnj", "pista", "documento", "trama", "misterio", "recurso", "reloj",
    "turno", "regla", "nota", "imagen", "hecho", "memoria", "mapa", "mundo",
})

# Subacciones de solo lectura de comandos que en general escriben: no toman el candado.
SOLO_LECTURA = {
    "documento": {"ver"}, "imagen": {"buscar", "biblioteca-agregar"},
    "hecho": {"listar"}, "memoria": {"ver"},
    "mapa": {"ver", "linea", "area", "catalogo"},
    "mundo": {"ver", "viaje"},
}

# Comandos que `turno --cambio` puede aplicar junto con el turno: todos cargan el estado con
# _cargar y lo cierran con _cerrar, así que dentro de un lote comparten una sola carga y un
# solo guardado.
CAMBIOS = (
    "vida", "condicion", "habilidad", "vendaje", "descanso", "enemigo", "nivel",
    "iniciativa", "conjuro", "adjudicar", "escena", "pnj",
    "pista", "documento", "trama", "misterio", "recurso", "reloj", "regla", "hecho", "memoria", "mapa", "mundo",
)

# Lote en curso de `turno --cambio`: {"slug", "datos", "hechos": [(evento, texto)]}.
_lote: dict | None = None

# Perfil de capacidades de esta ejecución: la CLI completa o el MCP de juego (ver capacidades.py).
_perfil = capacidades.CLI


def _bono(texto: str) -> tuple[int, str]:
    valor, _, fuente = texto.partition(":")
    try:
        return int(valor), fuente.strip()
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"bono inválido {texto!r}: usa N o N:fuente (p. ej. 2:ayuda)") from e


def _imprimir(args, evento: dict, texto: str) -> None:
    print(json.dumps(evento, ensure_ascii=False, indent=2) if args.json else texto)


def _cargar(args) -> tuple[str, dict]:
    if _lote is not None:
        return _lote["slug"], _lote["datos"]
    slug = estado.slug_activo(args.partida)
    return slug, estado.cargar(slug)


def _cerrar(args, slug: str, datos: dict, evento: dict, texto: str) -> None:
    if _lote is not None:
        _lote["hechos"].append((evento, texto))
        return
    # Snapshot y bitácora en una sola transacción: un corte no deja medio cambio.
    (evento,) = estado.escribir(slug, datos=datos, eventos=[evento])
    _imprimir(args, evento, texto)


def _cerrar_mapa(args, slug: str, datos: dict, evento: dict, resumen: str) -> None:
    """Cierra una acción que deja un mapa de zona nuevo.

    Recoloca las fichas en la rejilla nueva y avisa de las que se quedaron fuera. Suelto,
    el narrador recibe el mapa entero en texto; dentro de `turno` ya se imprime al final,
    así que basta la línea de `resumen`. El evento lo arma cada acción porque cada una
    publica sus propios campos.
    """
    perdidos = mapas.reubicar(datos)
    texto = mapas.zona_texto(datos) if _lote is None else resumen
    if perdidos:
        texto += f"\n⚠ Quedaron sin casilla (fuera del mapa nuevo): {', '.join(perdidos)}."
    _cerrar(args, slug, datos, evento, texto)


def _candado_de_escritura(args):
    """Toma el candado de la partida para el comando completo, si el comando escribe."""
    if args.comando not in ESCRIBEN or getattr(args, "accion", None) in SOLO_LECTURA.get(args.comando, ()):
        return nullcontext()
    try:
        ruta = estado.ruta_candado(estado.slug_activo(args.partida))
    except (ValueError, FileNotFoundError):
        # Sin partida activa (p. ej. `nueva`) o con un slug que no existe: el comando
        # fallará con su propio error; no hay estado que proteger.
        return nullcontext()
    return bloqueo.candado(ruta)


def _recargar(datos: dict, recargas: set[str], quienes: list[dict] | None = None) -> list[tuple[str, str]]:
    """Recarga las habilidades gastadas con esas recargas; devuelve (personaje, habilidad)."""
    recargadas = []
    for p in datos.get("personajes", []) if quienes is None else quienes:
        for h in p.get("habilidades", []):
            if h.get("recarga") in recargas and h.get("disponible") is False:
                h["disponible"] = True
                recargadas.append((p["nombre"], h["nombre"]))
    return recargadas


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


def c_harness(args) -> None:
    if args.accion == "lista":
        raiz = estado.RAIZ
        for h in harness.HARNESSES:
            faltan = [a for a in h["archivos"] if not (raiz / a).exists()]
            marca = "✗ faltan " + ", ".join(faltan) if faltan else "✓"
            print(f"{h['nombre']:<16} {marca}")
            print(f"  instrucciones: {h['instrucciones']}")
            print(f"  herramientas:  CLI bin/mesa · MCP {h['mcp']}")
            print(f"  comandos:      {h['comandos']}")
    elif args.accion == "sync":
        cambiados = harness.sync()
        print("Adaptadores regenerados: " + ", ".join(cambiados) if cambiados else "Adaptadores ya estaban en sincronía.")
    elif args.accion == "verificar":
        resultados = harness.verificar()
        for nombre, estado_, detalle in resultados:
            print(f"{ {'ok': '✓', 'fallo': '✗', 'omitido': '–'}[estado_] } {nombre}: {detalle}")
        if any(e == "fallo" for _, e, _ in resultados):
            raise RuntimeError("hay comprobaciones fallidas")
    elif args.accion == "instrucciones":
        print(harness.instrucciones(args.id))
    else:
        print(f"Skill instalada en {harness.instalar_skill_hermes(args.forzar)}")


def c_recursos(args) -> None:
    """La copia empaquetada de visor/, partidas/_plantilla/ y adaptadores/ (la usa el wheel)."""
    if args.accion == "sync":
        cambiadas = distribucion.sincronizar()
        print("Recursos sincronizados: " + ", ".join(cambiadas) if cambiadas else "Los recursos ya estaban en sincronía.")
    else:
        estado_, detalle = distribucion.verificar()
        print(f"{ {'ok': '✓', 'fallo': '✗', 'omitido': '–'}[estado_] } recursos empaquetados: {detalle}")
        if estado_ == "fallo":
            raise RuntimeError("la copia empaquetada está desincronizada")


def c_fuentes(args) -> None:
    """Catálogo externo con procedencia: la red solo en `buscar` y `actualizar`."""
    if args.accion == "listar":
        documento = fuentes.documento_local()
        if documento:
            d = documento["datos"]
            descargado = (documento["fuente"].get("descargado") or "")[:16].replace("T", " ")
            print(f"Documento: {d['nombre']} ({d['key']}) · {d['licencia']} · descargado {descargado}")
        entradas = fuentes.listar(args.tipo)
        if not entradas:
            print("La caché está vacía: `bin/mesa fuentes buscar <tipo> <texto>` y luego `actualizar`.")
            return
        for e in entradas:
            print(f"{e['tipo']:<10} {e['key']:<40} {e['nombre'] or ''} · {e['licencia'] or '?'} · {e['descargado'] or '?'}")
    elif args.accion == "buscar":
        resultados = fuentes.buscar(args.tipo, args.texto)
        if not resultados:
            print(f"Sin resultados para «{args.texto}» en {fuentes.DOCUMENTO}.")
            return
        for r in resultados:
            print(f"{r['key']}  {r['nombre']}")
    elif args.accion == "actualizar":
        entrada = fuentes.actualizar(args.tipo, args.clave)
        fuente = entrada["fuente"]
        destino = fuentes.ruta_entrada(args.tipo, args.clave).relative_to(estado.RAIZ)
        print(f"{entrada['datos']['nombre']} ({args.clave}) → {destino}")
        print(f"Fuente: open5e/{fuente['documento']} · licencia {fuente['licencia']} · descargado {fuente['descargado'][:16].replace('T', ' ')}")
    else:
        print(json.dumps(fuentes.obtener(args.tipo, args.clave), ensure_ascii=False, indent=2))


def c_contexto(args) -> None:
    print(informes.contexto(estado.slug_activo(args.partida), args.completo, args.eventos))


def c_migrar(args) -> None:
    """Diagnóstico dry-run (P1.4) o migración no destructiva en copia (P1.5) a D&D 2024."""
    slug, datos = _cargar(args)
    fichas = migraciones.cargar_fichas_2024(args.fichas, args.atributos)
    accion = "diagnosticar" if args.dry_run else (args.accion or "diagnosticar")
    if accion == "diagnosticar":
        informe = migraciones.diagnosticar(datos, slug, fichas_2024=fichas or None)
        _imprimir(args, informe, migraciones.formatear_diagnostico(informe))
        return
    destino = args.destino or args.hacia
    if not destino:
        raise ValueError("indica el slug de la copia de destino: `mesa migrar copiar <slug-destino> --fichas ...`")
    raiz_destino = Path(args.raiz_destino).expanduser() if args.raiz_destino else None
    res = migraciones.migrar_copia(slug, destino, fichas, raiz_destino=raiz_destino)
    texto = (
        f"Copia migrada a D&D 2024: {res['destino']} → {res['ruta']}\n"
        f"Resumen y rollback: {res['resumen_archivo']}\n"
        f"(La partida original «{slug}» sigue intacta.)"
    )
    _imprimir(args, res, texto)


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


# ---------- mundo ----------

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
                    mapas.mundo_texto(datos) if _lote is None else f"Mapa del mundo cargado ({info['id']}).")
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
        texto = mapas.mundo_texto(datos) if _lote is None else f"Mapa del mundo generado (semilla {gen['semilla']}, {gen['lugares']} lugares)."
        evento = {"tipo": "mundo", "accion": "generar", **gen}
    elif args.accion == "importar":
        res = mapas.importar_mundo_archivo(datos, args.archivo, nombre=args.nombre, licencia=args.licencia, fuente=args.fuente)
        texto = mapas.mundo_texto(datos) if _lote is None else f"Mapa del mundo importado ({res['lugares']} lugares, {res['regiones']} regiones)."
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
    partes = shlex.split(texto)
    if not partes or partes[0] not in CAMBIOS:
        raise ValueError(f"cambio no permitido: {texto!r} (valen: {', '.join(CAMBIOS)})")
    try:
        cambio = _parser().parse_args(partes)
    except SystemExit:
        raise ValueError(f"cambio inválido: {texto!r}") from None
    motivo = capacidades.revisar(cambio, _perfil)
    if motivo:
        raise ValueError(f"cambio no permitido: {motivo}")
    if getattr(cambio, "accion", None) in SOLO_LECTURA.get(cambio.comando, ()):
        raise ValueError(f"cambio no permitido: `{cambio.comando} {cambio.accion}` es una consulta de solo lectura")
    return cambio


def c_turno(args) -> None:
    """Registra el turno y, en el mismo paso, aplica los cambios de estado: todos o ninguno."""
    global _lote
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
    _lote = {"slug": slug, "datos": datos, "hechos": []}
    try:
        for cambio in cambios:
            cambio.funcion(cambio)
        if tenia_mapa_o_mundo or bool((datos.get("escena") or {}).get("mapa") or datos.get("mundo")):
            _lote["hechos"].extend(mapas.asegurar_mapa_escena(datos, slug=slug))
        hechos = _lote["hechos"]
    finally:
        _lote = None
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


# ---------- imágenes, guardado, lecciones ----------

def c_imagen(args) -> None:
    slug = estado.slug_activo(args.partida)
    if args.accion == "ninguna":
        e = imagenes.tarjeta_svg(slug)
        _imprimir(args, e, f"Tarjeta de escena: {e['archivo']}")
    elif args.accion == "elegir":
        if _perfil == capacidades.JUEGO and not capacidades.de_biblioteca(args.fuente):
            raise ValueError(
                "desde el MCP solo se eligen imágenes de la biblioteca curada (id o archivo); "
                "las rutas y las URLs van por la CLI"
            )
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
        item = lecciones.agregar(args.texto, args.alcance, args.categoria, args.evidencia, args.origen or "", args.fase)
        print(f"{item['id']} añadida ({item['alcance']}/{item['categoria']}).")
    elif args.accion == "retirar":
        item = lecciones.retirar(args.id, args.motivo)
        print(f"{item['id']} retirada: {args.motivo}")
    elif args.accion == "incorporar":
        item = lecciones.incorporar(args.id, args.donde)
        print(f"{item['id']} incorporada en {args.donde}: ya no se repite en `retomar`.")
    elif args.accion == "fase":
        item = lecciones.fijar_fase(args.id, args.fase)
        print(f"{item['id']}: fase {item.get('fase', 'siempre')}.")
    else:
        items = [i for i in lecciones.leer() if args.todas or i["estado"] == "activa"]
        if args.alcance:
            items = [i for i in items if i["alcance"] == args.alcance]
        print(json.dumps(items, ensure_ascii=False, indent=2) if args.json else lecciones.como_markdown(items))


def c_retro(args) -> None:
    print(informes.retro(estado.slug_activo(args.partida)))


def c_servir(args) -> None:
    import secrets
    from . import servidor

    comando = shlex.split(args.agente_cmd) if args.agente_cmd else None
    agente = None if getattr(args, "sin_agente", False) else (args.agente or ("agente" if comando else "hermes"))
    tailscale = False if getattr(args, "sin_tailscale", False) else (True if args.tailscale else None)
    clave_sala = getattr(args, "clave_sala", None) or (secrets.token_urlsafe(16) if getattr(args, "sala", False) else None)
    servidor.servir(args.host, args.puerto, agente=agente, comando=comando if agente else None,
                    tailscale=tailscale, usuarios=args.tailscale_usuario, clave_sala=clave_sala)


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
    s = cmd("estado", c_estado, "resumen del estado actual")
    s.add_argument("--breve", action="store_true", help="una línea por personaje: lo que tiene a mano ahora")
    cmd("revisar", c_revisar, "avisos de consistencia: enemigos en 0, habilidades de combate gastadas, posiciones, narrador")
    s = cmd("retomar", c_retomar, "empieza o retoma la sesión: registra al narrador y muestra dónde quedó la historia")
    s.add_argument("--narrador", help="harness/modelo, p. ej. 'codex/gpt-5.5' o 'claude-code/opus'")
    s = cmd("pausar", c_pausar, "deja el traspaso para el próximo narrador, en cualquier harness")
    s.add_argument("--pendiente", required=True, help="qué acaba de pasar y qué se espera de cada jugador")
    s.add_argument("--commit", action="store_true", help="commitea partidas/, lecciones/ y biblioteca/ en git")
    s = cmd("harness", c_harness, "adaptadores por harness: lista | sync | verificar | instrucciones <id> | instalar-hermes")
    hsub = s.add_subparsers(dest="accion", required=True)
    hsub.add_parser("lista", help="qué lee cada harness y si sus archivos están")
    hsub.add_parser("sync", help="regenera CLAUDE.md, GEMINI.md, configuraciones MCP y comandos")
    hsub.add_parser("verificar", help="comprueba adaptadores, servidor MCP y el escáner de Hermes")
    e = hsub.add_parser("instrucciones", help="cómo arrancar en un harness concreto")
    e.add_argument("id", choices=[h["id"] for h in harness.HARNESSES])
    e = hsub.add_parser("instalar-hermes", help="instala la skill opcional en ~/.hermes/skills (fuera del repo)")
    e.add_argument("--forzar", action="store_true")
    s = cmd("recursos", c_recursos, "recursos empaquetados del wheel: sync | verificar")
    rsub = s.add_subparsers(dest="accion", required=True)
    rsub.add_parser("sync", help="regenera mesa/recursos/ desde visor/, partidas/_plantilla/ y adaptadores/")
    rsub.add_parser("verificar", help="comprueba que la copia empaquetada coincide con el repositorio")
    s = cmd("fuentes", c_fuentes, "catálogo externo con procedencia (Open5e, documento srd-2024): listar | buscar | actualizar | ver")
    fsub = s.add_subparsers(dest="accion", required=True)
    e = fsub.add_parser("listar", help="lo que hay en la caché local, con licencia y fecha")
    e.add_argument("tipo", nargs="?", choices=sorted(fuentes.TIPOS))
    e = fsub.add_parser("buscar", help="busca en Open5e (sale a la red) y muestra keys para actualizar")
    e.add_argument("tipo", choices=sorted(fuentes.TIPOS)); e.add_argument("texto")
    e = fsub.add_parser("actualizar", help="copia un objeto a la caché con su procedencia (sale a la red)")
    e.add_argument("tipo", choices=sorted(fuentes.TIPOS)); e.add_argument("clave")
    e = fsub.add_parser("ver", help="los datos cacheados, sin red")
    e.add_argument("tipo", choices=sorted(fuentes.TIPOS)); e.add_argument("clave")
    s = cmd("contexto", c_contexto, "contexto del director: lecciones, reglas de la casa, estado y últimos eventos")
    s.add_argument("--completo", action="store_true", help="incluye biblia, notas del director y reglamento")
    s.add_argument("--eventos", type=int, default=15)
    s = cmd("migrar", c_migrar, "diagnóstico dry-run o migración en copia validada de d20-simple a dnd-2024")
    s.add_argument("accion", nargs="?", choices=["diagnosticar", "copiar"], default="diagnosticar")
    s.add_argument("destino", nargs="?", help="con `copiar`: slug de la copia nueva (p. ej. neva-2024)")
    s.add_argument("--hacia", help="alternativa a <destino> para el slug de la copia")
    s.add_argument("--dry-run", action="store_true", help="solo diagnostica campos faltantes y acciones humanas sin escribir")
    s.add_argument("--fichas", help="archivo JSON (o JSON inline) con las fichas 2024 acordadas por personaje")
    s.add_argument("--atributos", action="append", metavar="QUIEN=fue:N,des:N,...",
                   help="6 puntuaciones 2024 acordadas para un personaje (repetible)")
    s.add_argument("--raiz-destino", help="raíz alternativa (scratch) donde crear partidas/<destino>")

    def opciones_d20(s):
        s.add_argument("--ventaja", nargs="?", const=True, default=False, metavar="MOTIVO")
        s.add_argument("--desventaja", nargs="?", const=True, default=False, metavar="MOTIVO")
        s.add_argument("--bono", type=_bono, action="append", default=[], metavar="N[:FUENTE]")
        s.add_argument("--oficio", action="store_true", help="suma el bono de oficio de la partida")
        s.add_argument("--etiqueta", help="qué se intenta, en pocas palabras")

    s = cmd("tirar", c_tirar, "tira una expresión: 1d20+3, 2d6, d100, 1d8+1d4")
    s.add_argument("expr"); s.add_argument("--quien"); s.add_argument("--etiqueta"); s.add_argument("--critico", action="store_true")
    s = cmd("prueba", c_prueba, "prueba d20 de atributo o habilidad (o salvación) contra una dificultad")
    s.add_argument("quien"); s.add_argument("atributo", help="característica o habilidad (sigilo, percepción...)")
    s.add_argument("--cd", "--dc", help="número o: muy-facil (5), sencilla (10), exigente (15), dificil (20), muy-dificil (25), casi-imposible (30)")
    s.add_argument("--usar", metavar="HABILIDAD", help="gasta una habilidad de la ficha y suma su bono")
    s.add_argument("--salvacion", action="store_true", help="en D&D 2024: tirada de salvación de característica")
    opciones_d20(s)
    s = cmd("ataque", c_ataque, "ataque contra la Defensa de un objetivo; si acierta, aplica el daño")
    s.add_argument("quien"); s.add_argument("objetivo"); s.add_argument("--arma"); s.add_argument("--atributo")
    s.add_argument("--cobertura", choices=["media", "tres-cuartos"])
    opciones_d20(s)
    s = cmd("dano", c_dano, "tira daño de un arma o expresión y lo aplica al objetivo")
    s.add_argument("quien"); s.add_argument("--arma"); s.add_argument("--expr"); s.add_argument("--objetivo")
    s.add_argument("--tipo-dano", help="en D&D 2024: cortante, perforante, contundente, fuego, veneno...")
    s.add_argument("--critico", action="store_true"); s.add_argument("--etiqueta")
    s = cmd("suerte", c_suerte, "d100 contra un porcentaje, para lo que no depende de nadie")
    s.add_argument("probabilidad", type=int); s.add_argument("--etiqueta", required=True)

    s = cmd("vida", c_vida, "suma o resta vida: mesa vida Jualjin -3"); s.add_argument("quien"); s.add_argument("delta", type=int); s.add_argument("--motivo")
    s.add_argument("--temporal", action="store_true", help="en D&D 2024: fija PG temporales (no se acumulan)")
    s.add_argument("--revivir", action="store_true", help="en D&D 2024: un conjuro lo devuelve a la vida (quita «muerto» antes de curar)")
    s = cmd("condicion", c_condicion, "agrega o quita una condición (catálogo: guias/condiciones.md)")
    s.add_argument("quien"); s.add_argument("accion", choices=["agregar", "quitar"]); s.add_argument("nombre")
    s.add_argument("--efecto"); s.add_argument("--desventaja", help="atributos afectados, separados por coma, o 'todo'/'ataques'")
    s.add_argument("--ventaja-contra", action="store_true"); s.add_argument("--niveles", type=int)
    s = cmd("vendaje", c_vendaje, "vendaje fuera de combate: +3 de vida, una vez por personaje entre descansos")
    s.add_argument("quien")
    s = cmd("descanso", c_descanso, "descanso corto (recarga lo «por descanso») o largo (toda la vida, −1 agotamiento, recarga todo)")
    s.add_argument("clase", choices=["corto", "largo"]); s.add_argument("--quien", action="append", help="solo estos personajes (por defecto, todos)")
    s.add_argument("--dados-golpe", type=int, default=0, help="en D&D 2024: Dados de Golpe a gastar en un descanso corto")
    s = cmd("habilidad", c_habilidad, "marca una habilidad como gastada o recargada")
    s.add_argument("quien"); s.add_argument("nombre"); g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--usar", action="store_true"); g.add_argument("--recargar", action="store_true")
    s = cmd("enemigo", c_enemigo, "amenazas en escena")
    s.add_argument("accion", choices=["agregar", "quitar", "limpiar", "revelar"]); s.add_argument("nombre", nargs="?", default="")
    s.add_argument("--stats", action="store_true", help="con revelar: también se ven su vida, CA y ataque")
    s.add_argument("--plantilla", help="rata, perro, maton, guardia"); s.add_argument("--vida", type=int); s.add_argument("--defensa", type=int)
    s.add_argument("--ataque", type=int); s.add_argument("--dano"); s.add_argument("--proteccion", type=int)
    s.add_argument("--aspecto", help="lo que se ve a simple vista (vestimenta, arma, complexión)")
    s.add_argument("--raza", help="raza o especie visible"); s.add_argument("--altura", help="altura aproximada visible")
    s.add_argument("--conocido", action="store_true"); s.add_argument("--desconocido", action="store_true")
    s = cmd("piloto", c_piloto, "regla de la casa: el narrador lleva a un PJ ausente (narrador) o se lo devuelve a su jugador (jugador)")
    s.add_argument("quien"); s.add_argument("lleva", choices=["narrador", "jugador"])
    s = cmd("nivel", c_nivel, "sube de nivel tras un hito: +2 vida máx. y +1 atributo o una habilidad nueva")
    s.add_argument("quien"); g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--atributo"); g.add_argument("--habilidad", help="'Nombre: qué hace'")
    cmd("iniciativa", c_iniciativa, "tira iniciativa D&D 2024 (1d20 + mod Destreza) para los combatientes en escena")
    s = cmd("conjuro", c_conjuro, "lanza un conjuro D&D 2024 (o devuelve requiere_resolucion_manual con referencia SRD)")
    s.add_argument("quien"); s.add_argument("conjuro")
    s.add_argument("--nivel-slot", type=int, help="nivel del espacio de conjuro a gastar")
    s.add_argument("--objetivo", action="append", help="objetivo del conjuro (repetible)")
    s = cmd("adjudicar", c_adjudicar, "registra una adjudicación manual de la mesa con referencia SRD y autor")
    s.add_argument("regla"); s.add_argument("decision")
    s.add_argument("--autor", default="director+jugador"); s.add_argument("--motivo", default="")

    s = cmd("escena", c_escena, "nueva escena, editarla o fijar posiciones")
    s.add_argument("accion", choices=["nueva", "editar", "posicion"])
    s.add_argument("quien", nargs="?"); s.add_argument("donde", nargs="?")
    for campo in ("titulo", "lugar", "hora", "clima", "descripcion"):
        s.add_argument(f"--{campo}")
    s.add_argument("--quitar", action="store_true")
    s.add_argument("--celda", help="casilla en el mapa de zona, p. ej. C4 (columna, fila)")
    s.add_argument("--cierre", help="con `nueva`: resumen de la escena que termina, para la crónica")
    s.add_argument("--conservar-mapa", action="store_true", help="con `nueva`: mantiene el mapa de zona y las posiciones")
    s = cmd("hecho", c_hecho, "hechos clave de la memoria: agregar | editar | fijar | soltar | archivar | restaurar | listar")
    hsub = s.add_subparsers(dest="accion", required=True)
    e = hsub.add_parser("agregar", help="anota un hecho clave (público: el jugador lo ve y lo corrige)")
    e.add_argument("texto"); e.add_argument("--categoria", choices=memoria.CATEGORIAS, default="otro")
    e.add_argument("--fijar", action="store_true", help="entra siempre al contexto, aunque no quepa en el presupuesto")
    e = hsub.add_parser("editar", help="corrige el texto o la categoría"); e.add_argument("id"); e.add_argument("texto", nargs="?")
    e.add_argument("--categoria", choices=memoria.CATEGORIAS)
    for accion, ayuda in (("fijar", "entra siempre al contexto"), ("soltar", "entra si cabe en el presupuesto"),
                          ("archivar", "sale del contexto, sigue a la vista"), ("restaurar", "vuelve de archivado")):
        hsub.add_parser(accion, help=ayuda).add_argument("id")
    e = hsub.add_parser("listar", help="los hechos y si entran al contexto"); e.add_argument("--todos", action="store_true")
    s = cmd("memoria", c_memoria, "memoria de la historia: hasta-ahora | escena | presupuesto | ver")
    msub = s.add_subparsers(dest="accion", required=True)
    msub.add_parser("hasta-ahora", help="reescribe el resumen corrido de la historia").add_argument("texto")
    e = msub.add_parser("escena", help="escribe o corrige la línea de crónica de una escena")
    e.add_argument("numero", type=int); e.add_argument("texto")
    msub.add_parser("presupuesto", help="caracteres de hechos no fijados en el contexto").add_argument("caracteres", type=int)
    msub.add_parser("ver", help="lo que entra al contexto del director").add_argument("--todo", action="store_true")
    s = cmd("mapa", c_mapa, "mapa de zona en cuadrícula: catalogo | cargar | importar | generar | zona | terreno | luz | linea | area | quitar | ver")
    asub = s.add_subparsers(dest="accion", required=True)
    e = asub.add_parser("catalogo", help="lista los mapas pre-hechos de biblioteca/mapas/ con su licencia")
    e.add_argument("consulta", nargs="?", default="", help="filtro opcional por nombre o etiqueta")
    e = asub.add_parser("cargar", help="carga un mapa pre-hecho de biblioteca/mapas/ por su id")
    e.add_argument("id"); e.add_argument("--nombre")
    e = asub.add_parser("importar", help="importa un archivo local .dd2vtt/.uvtt o Watabou JSON (solo CLI)")
    e.add_argument("archivo"); e.add_argument("--nombre"); e.add_argument("--celda", type=float)
    e.add_argument("--luz", choices=mapas.LUCES); e.add_argument("--licencia"); e.add_argument("--fuente")
    e = asub.add_parser("generar", help=f"genera un mapa de zona reproducible ({', '.join(mapas.TIPOS_ZONA)})")
    e.add_argument("tipo", help="mazmorra, taberna (o interior), calle (o plaza), bosque (o claro), cueva, puente")
    e.add_argument("--semilla", help="semilla para reproducir el mismo mapa")
    e.add_argument("--ancho", type=int, help="columnas (5–26)")
    e.add_argument("--alto", type=int, help="filas (5–40)")
    e.add_argument("--densidad", choices=mapas.DENSIDADES, default="normal")
    e.add_argument("--celda", type=float, help=f"metros por casilla (por defecto {mapas.cifra(mapas.CELDA)})")
    e.add_argument("--nombre"); e.add_argument("--luz", choices=mapas.LUCES)
    e = asub.add_parser("zona", help="dibuja (o redibuja) la zona: una fila de texto por línea")
    e.add_argument("--dibujo", help="filas separadas por \\n; espacio = fuera del mapa; dígitos reservados para fichas")
    e.add_argument("--leyenda", action="append", metavar="C=SIGNIFICADO", help=f"repetible; ya conocidos: {', '.join(f'{k} {v}' for k, v in mapas.LEYENDA_BASE.items())}")
    e.add_argument("--celda", type=float, help=f"metros por casilla (por defecto {mapas.cifra(mapas.CELDA)})")
    e.add_argument("--nombre"); e.add_argument("--luz", choices=mapas.LUCES, help="iluminación base de la zona")
    e = asub.add_parser("terreno", help="ajusta semántica de un carácter de la leyenda (cobertura, terreno difícil, paso/visión)")
    e.add_argument("caracter")
    e.add_argument("--cobertura", choices=mapas.COBERTURAS)
    e.add_argument("--dificil", action="store_true"); e.add_argument("--normal", action="store_true")
    e.add_argument("--bloquea-paso", action="store_true"); e.add_argument("--paso-libre", action="store_true")
    e.add_argument("--bloquea-vision", action="store_true"); e.add_argument("--vision-libre", action="store_true")
    e = asub.add_parser("luz", help="iluminación ambiental y focos puntuales")
    e.add_argument("nivel", nargs="?", choices=mapas.LUCES, help="brillante, penumbra u oscuridad")
    e.add_argument("--foco", action="append", metavar="CELDA:BRILLANTE:PENUMBRA[:NOMBRE]", help="p. ej. G4:6:6:farol")
    e.add_argument("--limpiar-focos", action="store_true")
    e = asub.add_parser("linea", help="consulta línea de visión, cobertura (SRD) y camino entre dos casillas o fichas")
    e.add_argument("origen"); e.add_argument("destino")
    e = asub.add_parser("area", help="casillas y fichas dentro de una plantilla de área (cono, esfera, linea, cubo)")
    e.add_argument("forma", choices=mapas.FORMAS_AREA); e.add_argument("tamano", type=float, help="metros de radio/largo/lado")
    e.add_argument("--origen", required=True, help="casilla o ficha de origen")
    e.add_argument("--hacia", help="casilla, ficha o rumbo (N, NE, E, SE, S, SO, O, NO)")
    e.add_argument("--ancho", type=float, help="ancho en metros para `linea` (por defecto 1 casilla)")
    asub.add_parser("quitar", help="retira el mapa de zona"); asub.add_parser("ver", help="el mapa como lo lee el narrador")
    s = cmd("mundo", c_mundo, "mapa del mundo: lugar | ruta | region | trazo | viaje | generar | aqui | quitar | ajustar | ver")
    wsub = s.add_subparsers(dest="accion", required=True)
    e = wsub.add_parser("lugar", help="crea o actualiza un lugar que los personajes conocen")
    e.add_argument("nombre"); e.add_argument("--x", type=float); e.add_argument("--y", type=float)
    e.add_argument("--tipo", help="ciudad, pueblo, edificio, bosque, montaña, río, puerto, ruina..."); e.add_argument("--nota")
    e.add_argument("--en", help="lugar padre donde está anidado (p. ej. Valdris)")
    e.add_argument("--visitado", action="store_true", help="marca el lugar como ya visitado")
    e = wsub.add_parser("ruta", help="une dos lugares (o la quita con --quitar)"); e.add_argument("de"); e.add_argument("a")
    e.add_argument("--tipo", help="camino, río, sendero..."); e.add_argument("--tiempo", help="p. ej. '30 min a pie'")
    e.add_argument("--distancia", help="p. ej. '2 km'"); e.add_argument("--trazo", help="polilínea 'x1,y1 x2,y2 ...'")
    e.add_argument("--ritmo", choices=tuple(mapas.RITMOS_VIAJE), help="calcula el tiempo según el ritmo del SRD")
    e.add_argument("--quitar", action="store_true")
    e = wsub.add_parser("region", help="polígono con bioma (bosque, llanura, montana, pantano, desierto, costa, agua, urbano, helado)")
    e.add_argument("nombre"); e.add_argument("--bioma", choices=mapas.BIOMAS)
    e.add_argument("--puntos", help="vértices 'x1,y1 x2,y2 x3,y3 ...'"); e.add_argument("--nota")
    e.add_argument("--en", help="lugar padre opcional"); e.add_argument("--quitar", action="store_true")
    e = wsub.add_parser("trazo", help="río, camino, costa o frontera como polilínea")
    e.add_argument("nombre"); e.add_argument("--tipo", choices=mapas.TIPOS_TRAZO)
    e.add_argument("--puntos", help="puntos 'x1,y1 x2,y2 ...'"); e.add_argument("--nota")
    e.add_argument("--en", help="lugar padre opcional"); e.add_argument("--quitar", action="store_true")
    e = wsub.add_parser("viaje", help="consulta distancia y tiempo de viaje según el ritmo del SRD (sin mutar)")
    e.add_argument("de"); e.add_argument("a"); e.add_argument("--ritmo", choices=tuple(mapas.RITMOS_VIAJE))
    e = wsub.add_parser("generar", help="genera de forma reproducible una comarca o el mapa interior de un pueblo (--en)")
    e.add_argument("--semilla", help="semilla reproducible"); e.add_argument("--bioma", choices=mapas.BIOMAS, default="bosque")
    e.add_argument("--lugares", type=int, default=4, help="cantidad de lugares (2–12)")
    e.add_argument("--en", help="lugar padre para generar su mapa interior"); e.add_argument("--nombre")
    e = wsub.add_parser("importar", help="importa un archivo JSON/GeoJSON de Azgaar en el mapa del mundo (solo CLI)")
    e.add_argument("archivo"); e.add_argument("--nombre"); e.add_argument("--licencia"); e.add_argument("--fuente")
    wsub.add_parser("aqui", help="dónde están ahora").add_argument("nombre")
    wsub.add_parser("quitar", help="saca un lugar del mapa (y sus rutas)").add_argument("nombre")
    e = wsub.add_parser("ajustar", help="nombre del mapa y unidad de las coordenadas"); e.add_argument("--nombre"); e.add_argument("--unidad")
    wsub.add_parser("ver", help="el mapa del mundo como lo lee el narrador")
    s = cmd("pnj", c_pnj, "crea o actualiza un PNJ visible para los jugadores")
    s.add_argument("nombre"); s.add_argument("--rol"); s.add_argument("--actitud", choices=["amistosa", "indiferente", "hostil"])
    s.add_argument("--estado"); s.add_argument("--nota")
    s.add_argument("--aspecto", help="rasgos físicos visibles a simple vista")
    s.add_argument("--raza", help="raza o especie visible"); s.add_argument("--altura", help="altura aproximada visible")
    s.add_argument("--conocido", action="store_true"); s.add_argument("--desconocido", action="store_true")
    s = cmd("pista", c_pista, "anota una pista descubierta"); s.add_argument("texto"); s.add_argument("--fuente")
    s = cmd("documento", c_documento, "documento del mundo (carta, telegrama, periódico...): se entrega en el chat y queda en el visor")
    s.add_argument("accion", choices=["agregar", "ver"]); s.add_argument("titulo", nargs="?", help="título (o id al ver)")
    s.add_argument("--clase", choices=informes.CLASES_DOCUMENTO, default="nota"); s.add_argument("--texto", help="texto; \\n separa líneas")
    s.add_argument("--archivo", help="lee el texto de un archivo"); s.add_argument("--fuente", help="dónde se encontró o quién lo dio")
    s = cmd("trama", c_trama, "abre, cambia o cierra una trama"); s.add_argument("nombre")
    s.add_argument("--estado", choices=["activa", "latente", "cerrada", "sin-abrir"]); s.add_argument("--nota")
    s = cmd("misterio", c_misterio, "pregunta abierta que los jugadores conocen"); s.add_argument("texto"); s.add_argument("--resolver", action="store_true")
    s = cmd("recurso", c_recurso, "fija o suma un recurso compartido (sin valor: lo quita)")
    s.add_argument("clave"); s.add_argument("valor", nargs="?"); s.add_argument("--sumar", type=int)
    s = cmd("reloj", c_reloj, "día, hora y plazos"); s.add_argument("--dia", type=int); s.add_argument("--hora")
    s.add_argument("--plazo", action="append"); s.add_argument("--quitar-plazo", action="append")
    s = cmd("turno", c_turno, "registra lo que declaró cada jugador y lo que pasó, y aplica los cambios de estado en el mismo paso")
    s.add_argument("--accion", action="append", metavar="NOMBRE=TEXTO"); s.add_argument("--resumen", required=True)
    s.add_argument("--cambio", action="append", metavar="'COMANDO ARGS'",
                   help=f"cambio de estado con la sintaxis de la CLI, p. ej. 'pista \"Huellas frescas\" --fuente Ana'; se aplican todos o ninguno ({', '.join(CAMBIOS)})")
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
    e.add_argument("--fase", choices=lecciones.FASES, help="sesion-cero: solo antes de la primera escena")
    e = lsub.add_parser("listar"); e.add_argument("--alcance"); e.add_argument("--todas", action="store_true")
    e = lsub.add_parser("retirar"); e.add_argument("id"); e.add_argument("--motivo", required=True)
    e = lsub.add_parser("incorporar", help="la lección ya está en AGENTS.md (u otro texto que el director lee siempre)")
    e.add_argument("id"); e.add_argument("--donde", required=True)
    e = lsub.add_parser("fase", help="limita la lección a una fase: sesion-cero | siempre"); e.add_argument("id")
    e.add_argument("fase", choices=lecciones.FASES + ("siempre",))
    cmd("retro", c_retro, "estadísticas de la partida y plantilla de retrospectiva")
    s = cmd("servir", c_servir, "abre el visor local con el chat del narrador activo por defecto")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--puerto", type=int, default=8765)
    s.add_argument("--agente", choices=sorted(chat.AGENTES), default="hermes", help="narrador del chat por ACP: hermes (por defecto), devin o gemini")
    s.add_argument("--sin-agente", action="store_true", help="abre el visor en modo solo lectura (sin chat de narrador)")
    s.add_argument("--agente-cmd", metavar="'COMANDO ACP'", help="otro agente ACP por stdio, p. ej. 'hermes -p otro acp'")
    s.add_argument("--tailscale", action="store_true", help="exige habilitar escritura por `tailscale serve` al dueño del nodo")
    s.add_argument("--sin-tailscale", action="store_true", help="desactiva la escritura por Tailscale aunque el nodo esté conectado")
    s.add_argument("--tailscale-usuario", action="append", metavar="LOGIN", help="con --tailscale: quién puede escribir (repetible)")
    s.add_argument("--sala", action="store_true", help="habilita sala online con código de invitación autogenerado")
    s.add_argument("--clave-sala", metavar="CLAVE", help="habilita sala online con la clave indicada")
    return p


def main(
    argv: list[str] | None = None,
    prohibidos: frozenset[str] = frozenset(),
    perfil: str = capacidades.CLI,
) -> int:
    """Ejecuta un comando. `perfil=capacidades.JUEGO` aplica la política del MCP de juego."""
    global _perfil
    anterior, _perfil = _perfil, perfil
    try:
        args = _parser().parse_args(argv)
        if args.comando in prohibidos:
            print(f"error: `{args.comando}` no se puede usar desde aquí", file=sys.stderr)
            return 1
        motivo = capacidades.revisar(args, _perfil)
        if motivo:
            print(f"error: {motivo}", file=sys.stderr)
            return 1
        try:
            with _candado_de_escritura(args):
                args.funcion(args)
        except (ValueError, FileNotFoundError, FileExistsError, RuntimeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except OSError as e:  # red caída, permisos, disco: un error legible, no un traceback
            print(f"error de sistema o de red: {e}", file=sys.stderr)
            return 1
        return 0
    finally:
        _perfil = anterior

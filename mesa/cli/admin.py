"""Administración del repo: harness, recursos, fuentes, migración, imágenes y visor."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from .. import capacidades, distribucion, estado, fuentes, harness, imagenes, informes, lecciones, migraciones
from . import comunes
from .comunes import _cargar, _imprimir

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

def c_imagen(args) -> None:
    slug = estado.slug_activo(args.partida)
    if args.accion == "ninguna":
        e = imagenes.tarjeta_svg(slug)
        _imprimir(args, e, f"Tarjeta de escena: {e['archivo']}")
    elif args.accion == "elegir":
        if comunes._perfil == capacidades.JUEGO and not capacidades.de_biblioteca(args.fuente):
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
    from .. import servidor

    comando = shlex.split(args.agente_cmd) if args.agente_cmd else None
    agente = None if getattr(args, "sin_agente", False) else (args.agente or ("agente" if comando else "hermes"))
    tailscale = False if getattr(args, "sin_tailscale", False) else (True if args.tailscale else None)
    clave_sala = getattr(args, "clave_sala", None) or (secrets.token_urlsafe(16) if getattr(args, "sala", False) else None)
    servidor.servir(args.host, args.puerto, agente=agente, comando=comando if agente else None,
                    tailscale=tailscale, usuarios=args.tailscale_usuario, clave_sala=clave_sala)


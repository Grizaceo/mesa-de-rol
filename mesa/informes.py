"""Textos que genera la mesa: estado, contexto del director, avisos, guardado y retrospectiva."""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime

from . import estado, lecciones
from .reglas import NOMBRE_ATRIBUTO
from .texto import con_signo, norm

CLASES_DOCUMENTO = ("carta", "telegrama", "periodico", "nota", "cartel", "informe", "otro")
NOMBRE_CLASE = {
    "carta": "Carta", "telegrama": "Telegrama", "periodico": "Periódico", "nota": "Nota",
    "cartel": "Cartel", "informe": "Informe", "otro": "Documento",
}
_RECARGA = {"escena": "una por escena", "combate": "una por combate", "descanso": "una por descanso", "dia": "una por día"}
_VUELVE = {
    "escena": "vuelve en la próxima escena", "combate": "vuelve al terminar el combate",
    "descanso": "vuelve tras un descanso", "dia": "vuelve mañana",
}


def _ficha(p: dict) -> list[str]:
    atributos = " · ".join(f"{NOMBRE_ATRIBUTO[k]} {con_signo(v)}" for k, v in p.get("atributos", {}).items())
    lineas = [
        f"**{p['nombre']}** ({p.get('rol', '')}, nivel {p.get('nivel', 1)}): vida {p['vida']}/{p['vida_max']}, "
        f"defensa {p.get('defensa')}, protección {p.get('proteccion', 0)}",
        f"  - {atributos}",
    ]
    if p.get("habilidades"):
        estados = [f"{h['nombre']} ({'disponible' if h.get('disponible', True) else 'gastada'})" for h in p["habilidades"]]
        lineas.append(f"  - Habilidades: {'; '.join(estados)}")
    if p.get("rasgos"):
        lineas.append(f"  - Rasgos: {' · '.join(r['nombre'] + ': ' + r['texto'] for r in p['rasgos'])}")
    if p.get("equipo"):
        lineas.append(
            "  - Equipo: " + "; ".join(e["nombre"] + (f" ({e['dano']})" if e.get("dano") else "") for e in p["equipo"])
        )
    if p.get("condiciones"):
        lineas.append(f"  - Condiciones: {'; '.join(c['nombre'] + ': ' + c.get('efecto', '') for c in p['condiciones'])}")
    return lineas


def _efecto_breve(c: dict) -> str:
    afectados = [norm(a) for a in c.get("desventaja", [])]
    if "todo" in afectados:
        return "desventaja en todo"
    frases = [" y ".join(NOMBRE_ATRIBUTO[a] for a in afectados if a in NOMBRE_ATRIBUTO)]
    frases = ["en " + frases[0]] if frases[0] else []
    if "ataques" in afectados:
        frases.append("al atacar")
    if frases:
        return "desventaja " + " y ".join(frases)
    if c.get("penalizador_por_nivel"):
        return f"{con_signo(-int(c['penalizador_por_nivel']) * int(c.get('niveles', 1)))} a toda prueba d20"
    return c.get("efecto", "").split(". ")[0].rstrip(".")


def ficha_breve(p: dict) -> str:
    """Una línea con lo que el personaje tiene a mano ahora: para la DECISIÓN de cada turno."""
    partes = [f"{p['nombre']} ({p.get('vida')}/{p.get('vida_max')})"]
    for h in p.get("habilidades", []):
        if h.get("disponible", True):
            extra = ", ".join(x for x in (con_signo(int(h["bono"])) if h.get("bono") else "", _RECARGA.get(h.get("recarga"), "")) if x)
            partes.append(f"«{h['nombre']}» disponible" + (f" ({extra})" if extra else ""))
        else:
            partes.append(f"«{h['nombre']}» gastada" + (f" ({_VUELVE[h['recarga']]})" if h.get("recarga") in _VUELVE else ""))
    partes += [f"{c['nombre']}: {_efecto_breve(c)}" for c in p.get("condiciones", [])]
    oficio = p.get("oficio") or {}
    if oficio.get("aplica"):
        partes.append(f"Oficio {con_signo(int(oficio.get('bono', 2)))}: {oficio['aplica']}")
    if p.get("vendaje_usado"):
        partes.append("vendaje ya usado")
    return " · ".join(partes)


def revisar(datos: dict, acciones: dict | None = None) -> list[str]:
    """Avisos de consistencia: lo que el narrador suele olvidar. Avisan, nunca bloquean."""
    avisos = []
    personajes = datos.get("personajes", [])
    if acciones is not None:
        claves = [norm(k) for k in acciones]
        for p in personajes:
            nombres = {norm(p.get("nombre", "")), norm(p.get("id", ""))} - {""}
            if int(p.get("vida", 0)) > 0 and not any(c.startswith(n) or n.startswith(c) for c in claves for n in nombres):
                avisos.append(f"Sin acción de {p['nombre']} en este turno: si no fue a propósito, pregúntale antes de avanzar la escena.")
    enemigos = datos.get("enemigos", [])
    for e in enemigos:
        if int(e.get("vida", 0)) <= 0:
            avisos.append(f"{e['nombre']} está en 0 de vida y sigue en escena: `enemigo quitar \"{e['nombre']}\"` si ya no cuenta.")
    if not any(int(e.get("vida", 0)) > 0 for e in enemigos):
        for p in personajes:
            for h in p.get("habilidades", []):
                if h.get("recarga") == "combate" and h.get("disponible") is False:
                    avisos.append(f"«{h['nombre']}» de {p['nombre']} sigue gastada sin amenazas en pie: si el combate terminó, `enemigo limpiar` la recarga.")
    posiciones = {norm(x.get("quien", "")) for x in datos.get("escena", {}).get("posiciones") or []}
    if posiciones:
        for p in personajes:
            if not {norm(p.get("nombre", "")), norm(p.get("id", ""))} & posiciones:
                avisos.append(f"{p['nombre']} no tiene posición en la escena: `escena posicion {p['nombre']} \"<dónde, con metros>\"`.")
    narrador = os.environ.get("MESA_NARRADOR") or (datos.get("sesion") or {}).get("narrador")
    if not narrador or narrador == "sin identificar":
        avisos.append('No hay narrador identificado: `bin/mesa retomar --narrador "<harness>/<modelo>"`.')
    return avisos


def documento_chat(doc: dict) -> str:
    """El documento como bloque citado, listo para pegar en el chat."""
    lineas = [f"> **{NOMBRE_CLASE.get(doc.get('clase'), 'Documento')} · {doc['titulo']}**", ">"]
    lineas += [f"> {l}" if l.strip() else ">" for l in doc["texto"].splitlines()]
    if doc.get("fuente"):
        lineas += [">", f"> _{doc['fuente']}_"]
    lineas.append(f"\n({doc['id']}: queda también en el visor, pestaña Documentos)")
    return "\n".join(lineas)


def anteriormente(slug: str, n: int = 3) -> str:
    """Borrador de «Anteriormente…» con los últimos resúmenes de turno, para abrir la sesión."""
    turnos = [e for e in estado.leer_eventos(slug) if e.get("tipo") == "turno"]
    if not turnos:
        return ""
    primero = len(turnos) - len(turnos[-n:]) + 1
    lineas = ["## Anteriormente (borrador: ábrelo con tu voz, en 4 líneas como máximo)"]
    lineas += [f"- Turno {i}: {e.get('resumen', '')}" for i, e in enumerate(turnos[-n:], start=primero)]
    return "\n".join(lineas) + "\n"


def resumen(datos: dict) -> str:
    escena = datos.get("escena", {})
    reloj = datos.get("reloj", {})
    lineas = [
        f"# {datos.get('titulo', '')}",
        f"Escena {escena.get('numero', '?')}: **{escena.get('titulo', '')}** — {escena.get('lugar', '')}, {escena.get('hora', '')}",
    ]
    if reloj.get("plazos"):
        lineas.append("Plazos: " + "; ".join(reloj["plazos"]))
    if escena.get("descripcion"):
        lineas.append(f"> {escena['descripcion']}")
    if escena.get("posiciones"):
        lineas.append("Posiciones: " + "; ".join(f"{x['quien']}: {x['donde']}" for x in escena["posiciones"]))
    lineas += ["", "## Personajes"]
    for p in datos.get("personajes", []):
        lineas += _ficha(p)
    if datos.get("enemigos"):
        lineas += ["", "## Amenazas en escena"]
        lineas += [
            f"- {e['nombre']}: vida {e['vida']}/{e['vida_max']}, defensa {e['defensa']}, ataque {con_signo(e.get('ataque', 0))}, "
            f"daño {e.get('dano', '-')}, protección {e.get('proteccion', 0)}"
            for e in datos["enemigos"]
        ]
    if datos.get("recursos"):
        lineas += ["", "## Recursos compartidos"] + [f"- {k}: {v}" for k, v in datos["recursos"].items()]
    if datos.get("pnj"):
        lineas += ["", "## PNJ conocidos"]
        for n in datos["pnj"]:
            nota = n["notas"][-1] if n.get("notas") else ""
            lineas.append(f"- **{n['nombre']}** ({n.get('rol', '')}; {n.get('actitud', 'indiferente')}): {n.get('estado', '')} {nota}".rstrip())
    if datos.get("pistas"):
        lineas += ["", "## Pistas"] + [f"- {x['texto']}" for x in datos["pistas"]]
    if datos.get("documentos"):
        lineas += ["", "## Documentos"] + [
            f"- {d['id']} · {NOMBRE_CLASE.get(d.get('clase'), 'Documento')} · «{d['titulo']}»" for d in datos["documentos"]
        ]
    if datos.get("tramas"):
        lineas += ["", "## Tramas"] + [f"- {t['nombre']} [{t['estado']}]: {t.get('nota', '')}" for t in datos["tramas"]]
    if datos.get("misterios"):
        lineas += ["", "## Preguntas abiertas"] + [f"- {m}" for m in datos["misterios"]]
    return "\n".join(lineas) + "\n"


def _linea_evento(e: dict) -> str:
    t = e.get("tipo")
    if t in ("prueba", "ataque"):
        que = e.get("habilidad") or NOMBRE_ATRIBUTO.get(e.get("atributo") or "", "") or e.get("arma", "")
        return f"[{e['seq']}] {e['quien']} · {que} · {e.get('etiqueta', '')}: {e['total']} vs {e.get('cd')} → {e['resultado']}"
    if t == "turno":
        acciones = "; ".join(f"{k}: {v}" for k, v in e.get("acciones", {}).items())
        return f"[{e['seq']}] TURNO — {acciones} ⇒ {e.get('resumen', '')}"
    if t in ("tirada", "dano"):
        return f"[{e['seq']}] {t} {e.get('expr', '')} = {e.get('total', e.get('final', ''))} {e.get('etiqueta', '')}"
    return f"[{e['seq']}] {t}: " + ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("seq", "ts", "tipo"))[:200]


def contexto(slug: str, completo: bool = False, n_eventos: int = 15) -> str:
    """Lo que el director lee al empezar o retomar: lecciones, reglas de la casa, estado y lo último ocurrido."""
    datos = estado.cargar(slug)
    base = estado.dir_partida(slug)
    partes = [f"# Contexto del director — {datos.get('titulo')} ({slug})", ""]
    if datos.get("pausa"):
        p = datos["pausa"]
        partes += [
            "## Retomar aquí (traspaso de la sesión anterior)",
            f"> {p['pendiente']}",
            f"_(pausó {p.get('narrador') or 'sin identificar'} el {p['cuando'][:16].replace('T', ' ')})_",
            "",
            "Continúa exactamente desde ahí: sin resumir de más y sin avanzar sin la acción de cada jugador.",
            "",
        ]
    partes += [
        "Lee también: `AGENTS.md` (tu contrato), `reglas/d20-simple.md`, "
        f"`{base.relative_to(estado.RAIZ)}/biblia.md` y `{base.relative_to(estado.RAIZ)}/director.md` (secreto).",
        "",
        "## Lecciones aplicables (de historias anteriores)",
        lecciones.como_markdown(lecciones.aplicables(datos)),
        "## Reglas de la casa vigentes",
    ]
    partes += [f"- **{r['id']}**: {r['texto']}" for r in datos.get("reglas_casa", [])] or ["- (ninguna)"]
    partes += ["", resumen(datos), "## Últimos eventos"]
    partes += [_linea_evento(e) for e in estado.leer_eventos(slug, limite=n_eventos)] or ["(sin eventos)"]
    if completo:
        for nombre in ("biblia.md", "director.md"):
            ruta = base / nombre
            if ruta.exists():
                partes += ["", f"---\n# {nombre}\n", ruta.read_text(encoding="utf-8")]
        reglas = estado.RAIZ / "reglas" / f"{datos.get('reglamento', 'd20-simple')}.md"
        if reglas.exists():
            partes += ["", "---\n", reglas.read_text(encoding="utf-8")]
    return "\n".join(partes) + "\n"


def guardado(slug: str) -> tuple[str, str]:
    """'Guardar partida': resumen copiable y archivo en guardados/."""
    datos = estado.cargar(slug)
    turnos = [e for e in estado.leer_eventos(slug) if e.get("tipo") == "turno"]
    decisiones = [f"- {e.get('resumen', '')}" for e in turnos[-12:]]
    texto = (
        f"# Partida guardada — {datos.get('titulo')}\n"
        f"_{datetime.now().strftime('%Y-%m-%d %H:%M')} · versión de estado {datos.get('version')}_\n\n"
        + resumen(datos)
        + ("\n## Decisiones recientes\n" + "\n".join(decisiones) + "\n" if decisiones else "")
        + "\n## Reglas de la casa\n"
        + "\n".join(f"- {r['id']}: {r['texto']}" for r in datos.get("reglas_casa", []))
        + "\n"
    )
    nombre = datetime.now().strftime("%Y-%m-%d_%H%M") + ".md"
    ruta = estado.dir_partida(slug) / "guardados" / nombre
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return texto, str(ruta.relative_to(estado.RAIZ))


def retro(slug: str) -> str:
    """Estadísticas de la bitácora y plantilla para escribir retro.md y proponer lecciones."""
    eventos = estado.leer_eventos(slug)
    tiradas = [e for e in eventos if e.get("tipo") in ("prueba", "ataque")]
    por_resultado = Counter(e["resultado"] for e in tiradas)
    por_quien = Counter(e["quien"] for e in tiradas)
    modos = Counter(e["modo"] for e in tiradas)
    turnos = sum(1 for e in eventos if e.get("tipo") == "turno")
    reglas = [e for e in eventos if e.get("tipo") == "regla"]
    lineas = [
        f"# Retro — {slug}",
        "",
        "## Números",
        f"- Turnos registrados: {turnos}",
        f"- Pruebas y ataques: {len(tiradas)} · éxitos {por_resultado['exito']} · fallos {por_resultado['fallo']} · "
        f"críticos {por_resultado['critico']} · unos naturales {por_resultado['uno_natural']}",
        f"- Por personaje: {', '.join(f'{k} {v}' for k, v in por_quien.items()) or '-'}",
        f"- Con ventaja {modos['ventaja']} · con desventaja {modos['desventaja']}",
        f"- Reglas de la casa añadidas durante el juego: {len(reglas)}",
        "",
        "## Qué funcionó (con evidencia: turno o tirada)",
        "- ",
        "",
        "## Qué corrigieron o pidieron los jugadores",
        "- ",
        "",
        "## Lecciones propuestas (confirmar con los jugadores antes de `mesa leccion agregar`)",
        "- [alcance] [categoría] lección — evidencia",
    ]
    return "\n".join(lineas) + "\n"

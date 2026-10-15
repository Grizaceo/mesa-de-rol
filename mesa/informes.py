"""Textos que genera la mesa: estado, contexto del director, guardado y retrospectiva."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from . import estado, lecciones
from .reglas import NOMBRE_ATRIBUTO
from .texto import con_signo


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

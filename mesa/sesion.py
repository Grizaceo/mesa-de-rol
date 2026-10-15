"""Sesiones: el traspaso entre narradores, sea cual sea su harness.

Todo vive en partida.json, no en la memoria del harness:
  sesion  quién narra ahora (harness/modelo) y desde cuándo; se cierra al pausar
  pausa   qué quedó pendiente al parar; se borra al registrar el siguiente turno
"""

from __future__ import annotations

import os
import subprocess

from . import estado, informes


def retomar(slug: str, narrador: str | None = None) -> str:
    datos = estado.cargar(slug)
    anterior = (datos.get("sesion") or {}).get("narrador") or (datos.get("pausa") or {}).get("narrador")
    # Nunca se hereda el narrador anterior: la bitácora compara narradores y no debe mentir.
    actual = narrador or os.environ.get("MESA_NARRADOR") or "sin identificar"
    datos["sesion"] = {"narrador": actual, "desde": estado.ahora()}
    estado.guardar(slug, datos)
    estado.registrar(slug, {"tipo": "sesion_retomada", "narrador": actual, "narrador_anterior": anterior})

    lineas = [f"# Retomar — {datos.get('titulo')} ({slug})", ""]
    lineas.append(f"Narra ahora: **{actual}**" + (f" (antes: {anterior})" if anterior and anterior != actual else ""))
    if actual == "sin identificar":
        lineas.append('⚠ Identifícate: `bin/mesa retomar --narrador "<harness>/<modelo>"` (o $MESA_NARRADOR).')
    anteriormente = informes.anteriormente(slug)
    lineas += ([""] + [anteriormente] if anteriormente else []) + ["", informes.contexto(slug)]
    return "\n".join(lineas)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(estado.RAIZ), *args], capture_output=True, text=True)


def pausar(slug: str, pendiente: str, commit: bool = False) -> str:
    datos = estado.cargar(slug)
    avisos = informes.revisar(datos)
    narrador = estado.narrador_actual(slug)
    datos["pausa"] = {"pendiente": pendiente, "cuando": estado.ahora(), "narrador": narrador}
    datos.pop("sesion", None)  # la sesión termina aquí; el próximo narrador se identifica al retomar
    estado.guardar(slug, datos)
    estado.registrar(slug, {"tipo": "sesion_pausada", "pendiente": pendiente, **({"narrador": narrador} if narrador else {})})
    salida = [f"⚠ {a}" for a in avisos]
    salida.append("Partida en pausa. Al retomar, en cualquier harness: `bin/mesa retomar --narrador \"<harness>/<modelo>\"`.")
    if commit:
        salida.append(_commit(slug, pendiente, narrador))
    return "\n".join(salida)


def _commit(slug: str, pendiente: str, narrador: str | None) -> str:
    if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        return "No es un repo git: nada que commitear."
    rutas = [p for p in (f"partidas/{slug}", "lecciones", "biblioteca") if (estado.RAIZ / p).exists()]
    _git("add", "--", *rutas)
    if _git("diff", "--cached", "--quiet", "--", *rutas).returncode == 0:
        return "Sin cambios que commitear."
    resumen = pendiente if len(pendiente) <= 60 else pendiente[:57] + "..."
    mensaje = f"pausa({slug}): {resumen}\n\nNarrador: {narrador or 'sin identificar'}"
    r = _git("commit", "-m", mensaje, "--", *rutas)
    if r.returncode != 0:
        return f"git commit falló: {r.stderr.strip() or r.stdout.strip()}"
    hash_ = _git("rev-parse", "--short", "HEAD").stdout.strip()
    return f"Commit {hash_}. Para seguir en un harness remoto (Devin, Codex cloud...), haz `git push`."

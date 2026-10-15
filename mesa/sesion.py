"""Sesiones: el traspaso entre narradores, sea cual sea su harness.

Todo vive en partida.json, no en la memoria del harness:
  sesion  quién narra ahora (harness/modelo) y desde cuándo
  pausa   qué quedó pendiente al parar; se borra al registrar el siguiente turno
"""

from __future__ import annotations

import subprocess

from . import estado, informes


def retomar(slug: str, narrador: str | None = None) -> str:
    datos = estado.cargar(slug)
    anterior = datos.get("sesion", {}).get("narrador")
    datos["sesion"] = {"narrador": narrador or anterior or "sin identificar", "desde": estado.ahora()}
    estado.guardar(slug, datos)
    estado.registrar(slug, {"tipo": "sesion_retomada", "narrador": datos["sesion"]["narrador"], "narrador_anterior": anterior})

    lineas = [f"# Retomar — {datos.get('titulo')} ({slug})", ""]
    lineas.append(f"Narra ahora: **{datos['sesion']['narrador']}**" + (f" (antes: {anterior})" if anterior and anterior != datos["sesion"]["narrador"] else ""))
    lineas += ["", informes.contexto(slug)]
    return "\n".join(lineas)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(estado.RAIZ), *args], capture_output=True, text=True)


def pausar(slug: str, pendiente: str, commit: bool = False) -> str:
    datos = estado.cargar(slug)
    narrador = datos.get("sesion", {}).get("narrador")
    datos["pausa"] = {"pendiente": pendiente, "cuando": estado.ahora(), "narrador": narrador}
    estado.guardar(slug, datos)
    estado.registrar(slug, {"tipo": "sesion_pausada", "pendiente": pendiente})
    salida = [f"Partida en pausa. Al retomar, en cualquier harness: `bin/mesa retomar --narrador \"<harness>/<modelo>\"`."]
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

"""Crear, configurar y borrar campañas desde el visor."""

from __future__ import annotations

import re
import time
from pathlib import Path

from .. import bloqueo, chat, distribucion, esquemas, estado, memoria, reglas_2024
from ..texto import con_signo, norm, slug_valido
from .http import MARCA_BIBLIA, MAX_CAMPANAS_SALA, Prohibido, _huella, _numero, _texto

class CampanaMixin:
    def _cambiar_memoria(self, slug: str, cuerpo: dict) -> dict:
        accion = cuerpo.get("accion")
        if not isinstance(accion, str):
            raise ValueError("falta «accion»")
        for campo in ("id", "texto", "categoria"):
            if cuerpo.get(campo) is not None and not isinstance(cuerpo[campo], str):
                raise ValueError(f"«{campo}» tiene que ser texto")
        numero = cuerpo.get("numero")
        if numero is not None and (not isinstance(numero, int) or isinstance(numero, bool)):
            raise ValueError("«numero» tiene que ser un entero")
        with bloqueo.candado(estado.ruta_candado(slug)):
            datos = estado.cargar(slug)
            evento, texto = memoria.aplicar(
                datos, accion, ident=cuerpo.get("id"), texto=cuerpo.get("texto"), categoria=cuerpo.get("categoria"),
                fijado=cuerpo.get("fijado") is True, numero=numero, autor="jugador",
            )
            (evento,) = estado.escribir(slug, datos=datos, eventos=[{**evento, "via": "visor"}])
        return {"ok": True, "texto": texto, "evento": evento, "memoria": datos["memoria"]}

    def _crear_partida(self, base: str, titulo: str) -> str:
        """Una partida nueva con un slug libre; si otro la crea a la vez, se prueba el siguiente."""
        base_slug = re.sub(r"[^a-z0-9]+", "-", norm(base)).strip("-")[:48].strip("-") or "campana"
        for n in range(1, 200):
            slug = base_slug if n == 1 else f"{base_slug}-{n}"
            if (estado.dir_partidas() / slug).exists():
                continue
            try:
                estado.nueva_partida(slug, titulo)
            except FileExistsError:
                continue
            return slug
        raise ValueError("ya hay demasiadas campañas con ese nombre: elige otro título")

    @staticmethod
    def _sumar_personajes(datos: dict, pjs_txt: str, reemplazar: bool) -> list[str]:
        """Añade los PJ nuevos de la lista; los que ya existen no se tocan (salvo la ficha de muestra de una partida nueva)."""
        if esquemas.version_de(datos) != esquemas.VERSION_2024:
            return ["en una partida d20-simple los personajes los crea el narrador: no se añadió ninguno"]
        existentes = [] if reemplazar else list(datos.get("personajes") or [])
        claves = {norm(p.get(c, "")) for p in existentes for c in ("nombre", "id")} - {""}
        nuevos, avisos = [], []
        for item in [x.strip() for x in re.split(r"[\n,;]+", pjs_txt) if x.strip()][:6]:
            m = re.match(r"^([^(–\-:]+?)(?:\s*[\(–\-:]\s*([^)]+)\)?\s*)?$", item)
            nombre_pj = (m.group(1) if m else item).strip()[:40]
            rol_pj = (m.group(2) if m and m.group(2) else "Aventurero").strip()[:80]
            if not nombre_pj:
                continue
            if norm(nombre_pj) in claves:
                if not reemplazar:
                    avisos.append(f"{nombre_pj} ya está en la partida: su ficha no se tocó")
                continue
            claves.add(norm(nombre_pj))
            nuevos.append(reglas_2024.ficha_inicial(
                nombre_pj, rol_pj, len(existentes) + len(nuevos), monedas=reglas_2024.monedas_de(datos.get("ambientacion") or {}),
            ))
        if nuevos:
            datos["personajes"] = existentes + nuevos
        return avisos

    @staticmethod
    def _biblia_rehacible(ruta: Path) -> bool:
        """Solo se escribe una biblia que no existe, que es la de la plantilla o que generó el visor y nadie editó."""
        if not ruta.exists():
            return True
        actual = ruta.read_text(encoding="utf-8")
        plantilla = distribucion.plantilla() / "biblia.md"
        if plantilla.exists() and actual == plantilla.read_text(encoding="utf-8"):
            return True
        marca = MARCA_BIBLIA.match(actual)
        return bool(marca) and _huella(actual[marca.end():]) == marca.group(1)

    def _eliminar_campana(self, slug: str, confirmar: str) -> dict:
        """La campaña va a `partidas/.papelera/` (se recupera moviéndola de vuelta), nunca se borra en el acto.

        Hay que escribir su nombre corto; la partida activa del narrador no se elimina, y la sala
        solo elimina campañas que creó la sala.
        """
        if confirmar != slug:
            raise ValueError(f"para eliminarla, escribe su nombre corto exacto: {slug}")
        try:
            activa = estado.slug_activo()
        except ValueError:
            activa = None
        if slug == activa:
            raise ValueError("es la partida activa del narrador: cambia antes de partida (`bin/mesa usar <otra>`)")
        if not self._es_anfitrion() and estado.cargar(slug).get("creada_por") != "sala":
            raise Prohibido("desde la sala solo se eliminan campañas creadas por la sala; las demás, el anfitrión")
        papelera = estado.dir_partidas() / ".papelera"
        papelera.mkdir(exist_ok=True)
        destino = papelera / f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}"
        with bloqueo.candado(estado.ruta_candado(slug)):
            estado.dir_partida(slug).rename(destino)
        return {"ok": True, "eliminada": slug, "papelera": str(destino.relative_to(estado.RAIZ))}

    def _configurar_campana(self, consulta: dict, cuerpo: dict) -> dict:
        modo = _texto(cuerpo, "modo", 20).lower() or "configurar"
        if modo not in ("nueva", "configurar", "eliminar"):
            raise ValueError(f"modo de campaña desconocido: {modo!r} (valen: nueva, configurar, eliminar)")
        if modo == "eliminar":
            return self._eliminar_campana(self._slug(consulta), _texto(cuerpo, "confirmar", 64))
        titulo = _texto(cuerpo, "titulo", 100)
        if modo == "nueva":
            if not titulo:
                raise ValueError("falta el título de la campaña")
            if not self._es_anfitrion():  # la sala también crea campañas, con un tope para que nadie llene el disco
                with self.server.presencia_lock:
                    if self.server.campanas_sala >= MAX_CAMPANAS_SALA:
                        raise ValueError(f"la sala ya creó {MAX_CAMPANAS_SALA} campañas en esta sesión: la siguiente la crea el anfitrión")
                    self.server.campanas_sala += 1
            slug = self._crear_partida(_texto(cuerpo, "slug", 100) or titulo, titulo)
        else:
            slug = self._slug(consulta)

        epoca = _texto(cuerpo, "epoca", 200)
        lugar = _texto(cuerpo, "lugar", 200)
        estilo_visual = _texto(cuerpo, "estilo_visual", 300)
        tono_raw = cuerpo.get("tono")
        if isinstance(tono_raw, list):
            tonos = [str(x).strip()[:40] for x in tono_raw if str(x).strip()][:10]
        else:
            tonos = [x.strip()[:40] for x in re.split(r"[,;]+", _texto(cuerpo, "tono", 400)) if x.strip()][:10]
        idea = _texto(cuerpo, "idea", 1500)
        pjs_txt = _texto(cuerpo, "personajes", 500)
        avisos: list[str] = []

        with bloqueo.candado(estado.ruta_candado(slug)):
            datos = estado.cargar(slug)
            if titulo:
                datos["titulo"] = titulo
            if modo == "nueva" and not self._es_anfitrion():
                datos["creada_por"] = "sala"  # la sala puede eliminar lo que ella creó
            amb = datos.setdefault("ambientacion", {})
            if epoca or modo == "nueva":
                amb["epoca"] = epoca
            if lugar or modo == "nueva":
                amb["lugar"] = lugar
            if estilo_visual or modo == "nueva":
                amb["estilo_visual"] = estilo_visual
            if tonos or modo == "nueva":
                amb["tono"] = tonos
            # Las monedas siguen a la ambientación en el acto (oro y cobre solo en fantasía) y las fichas con ellas.
            nuevas = reglas_2024.monedas_de({k: v for k, v in amb.items() if k != "monedas"})
            if amb.get("monedas") != nuevas and esquemas.version_de(datos) == esquemas.VERSION_2024:
                amb["monedas"] = nuevas
                for p in datos.get("personajes") or []:
                    previas = p.get("monedas") if isinstance(p.get("monedas"), dict) else {}
                    p["monedas"] = {m: int(previas.get(m, 0) or 0) for m in nuevas}
            if pjs_txt:
                avisos += self._sumar_personajes(datos, pjs_txt, reemplazar=modo == "nueva")

            biblia_ruta = estado.dir_partida(slug) / "biblia.md"
            rehacer_biblia = self._biblia_rehacible(biblia_ruta)
            lineas_biblia = [
                f"# Biblia — {datos.get('titulo', slug)}",
                "",
                "## 1. Estilo y tono",
                f"- **Reglamento:** `{datos.get('reglamento', 'dnd-2024')}`",
                f"- **Tono:** {', '.join(amb.get('tono') or []) or 'Aventura'}",
                f"- **Estilo visual:** {amb.get('estilo_visual') or 'Por definir en mesa'}",
                "",
                "## 2. Mundo y ambientación",
                f"- **Época:** {amb.get('epoca') or 'Por definir'}",
                f"- **Lugar inicial:** {amb.get('lugar') or 'Por definir'}",
            ]
            if idea:
                lineas_biblia += ["", "## 3. Propuesta de campaña de los jugadores", idea]
            lineas_biblia += [
                "",
                "## 4. Personajes jugadores",
                *[f"- **{p['nombre']}** ({p.get('rol') or 'Nivel 1'})" for p in datos.get("personajes", [])],
                "",
            ]
            origen = consulta.get("p", [""])[0] or ""
            autor = self._autor(cuerpo.get("autor")) if self._es_anfitrion() else (
                (self._pj_reclamado(origen) if slug_valido(origen) else None) or "invitado de la sala"
            )
            (evento,) = estado.escribir(
                slug,
                datos=datos,
                eventos=[{"tipo": "ambientacion", "titulo": datos.get("titulo", slug), "idea": idea, "autor": autor, "via": "visor"}],
            )
            # Después del commit: si la partida no se guardó, la biblia tampoco cambia.
            if rehacer_biblia:
                cuerpo_biblia = "\n".join(lineas_biblia)
                estado._escribir_texto(biblia_ruta, f"<!-- generada por el visor · {_huella(cuerpo_biblia)} -->\n{cuerpo_biblia}")
            else:
                avisos.append("biblia.md ya estaba escrita a mano: no se tocó; la ambientación queda en la partida")

        iniciado = False
        if cuerpo.get("iniciar_chat") and getattr(self.server, "narrador", None) is not None:
            partes_prompt = [f"Queremos arrancar la campaña «{datos.get('titulo', slug)}»."]
            if amb.get("epoca") or amb.get("lugar"):
                partes_prompt.append(f"Ambientación: {', '.join(x for x in (amb.get('epoca'), amb.get('lugar')) if x)}.")
            if amb.get("tono"):
                partes_prompt.append(f"Tono: {', '.join(amb['tono'])}.")
            if amb.get("estilo_visual"):
                partes_prompt.append(f"Estilo visual: {amb['estilo_visual']}.")
            if pjs_txt:
                partes_prompt.append(f"Personajes iniciales: {pjs_txt}.")
            if idea:
                partes_prompt.append(f"Lo que queremos jugar: {idea}")
            partes_prompt.append(
                "Por favor configura la Escena 1 (con su mapa táctico y posiciones de nuestros personajes), "
                "ajusta nuestras fichas D&D 2024 si hace falta y ábrenos la primera escena."
            )
            try:
                self._narrador().enviar(slug, " ".join(partes_prompt), "Mesa")
                iniciado = True
            except chat.Ocupado:
                iniciado = False

        return {"ok": True, "slug": slug, "titulo": datos.get("titulo", slug), "evento": evento, "iniciado": iniciado, "avisos": avisos}

    @staticmethod
    def _aplicar_trasfondo(datos: dict, ficha: dict, cuerpo: dict, es_2024: bool) -> dict:
        """El jugador cuenta de dónde viene su PJ y qué le sube (SRD 5.2.1: +2/+1 o +1/+1/+1, tope 20)
        y, como regla de la casa opcional, qué le baja (−1). Rehacerlo deshace el trasfondo anterior."""
        if not es_2024:
            raise ValueError("el trasfondo con características es de D&D 2024; en d20-simple escríbelo en la biblia")
        def mapa(campo):
            valor = cuerpo.get(campo) or {}
            if not isinstance(valor, dict):
                raise ValueError(f"«{campo}» tiene que ser {{característica: número}}")
            return {reglas_2024.resolver_atributo(k)[0]: _numero(valor, k, minimo=-2, maximo=2) for k in valor}
        sube, baja = mapa("sube"), mapa("baja")
        if any(v < 0 for v in sube.values()) or sorted(sube.values()) not in ([], [1, 2], [1, 1, 1]):
            raise ValueError("el trasfondo sube +2 y +1, o +1 a tres características")
        if any(v not in (-1,) for v in baja.values()) or len(baja) > 1:
            raise ValueError("como regla de la casa, el trasfondo baja como mucho una característica en 1")
        habilidades = [str(h).strip()[:40] for h in (cuerpo.get("habilidades") or []) if str(h).strip()][:2]
        attrs = ficha.setdefault("atributos", {})
        previo = ficha.get("trasfondo") or {}
        for k, v in {**(previo.get("sube") or {}), **(previo.get("baja") or {})}.items():
            attrs[k] = int(attrs.get(k, 10)) - int(v)
        for k, v in list(sube.items()) + list(baja.items()):
            attrs[k] = int(attrs.get(k, 10)) + int(v)
            if not 1 <= attrs[k] <= 20:
                raise ValueError(f"{esquemas.NOMBRES_2024[k]} quedaría en {attrs[k]}: el tope es 20")
        comp = ficha.setdefault("competencias", {})
        comp["habilidades"] = [h for h in comp.get("habilidades") or [] if h not in (previo.get("habilidades") or [])] + [
            h for h in habilidades if h not in (comp.get("habilidades") or [])]
        nombre = _texto(cuerpo, "nombre", 60) or "Trasfondo"
        ficha["trasfondo"] = {"nombre": nombre, "historia": _texto(cuerpo, "historia", 1500), "sube": sube, "baja": baja, "habilidades": habilidades}
        cambios = ", ".join(f"{esquemas.NOMBRES_2024[k]} {con_signo(v)}" for k, v in {**sube, **baja}.items()) or "sin cambios de características"
        return {"tipo": "nota", "texto": f"{ficha['nombre']} · trasfondo «{nombre}»: {cambios}" + (f"; habilidades: {', '.join(habilidades)}" if habilidades else "")}

"""Chat del visor: el jugador escribe en la página y el narrador (un agente ACP) responde ahí.

Cada partida guarda su conversación en `partidas/<slug>/chat.jsonl` (público: es lo que el
jugador ya leyó) y la sesión del agente en `partidas/<slug>/.narrador.json` (no se sirve).
Un turno de chat:

1. se anota el mensaje del jugador;
2. el agente lo recibe por ACP (en una sesión nueva, con un preámbulo que lo manda a
   `retomar`, o en la que ya tenía);
3. mientras responde, el texto llega a trozos y lo que registra en la mesa (tiradas, cambios,
   documentos, hechos) entra como «partes» del mensaje, en el orden en que pasó, para que el
   visor lo pinte como tarjetas dentro del chat;
4. al terminar, el mensaje del narrador queda en el archivo.

Lo que el agente piensa o lo que leen sus herramientas **no** se muestra: puede haber
secretos de `director.md`. Solo se ve su respuesta y un aviso genérico de qué está haciendo.

Permisos: las herramientas de la mesa y la lectura pasan solas; editar archivos solo dentro de
la partida; cualquier otra cosa espera a que el jugador la apruebe en el chat.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

from . import estado, vista
from .acp import ClienteACP, ErrorACP, elegir_opcion

AGENTES = {
    "hermes": ["hermes", "-p", "narrador", "acp"],
    "devin": ["devin", "acp"],
    # Codex y Claude Code hablan ACP con los adaptadores de Zed (versión fijada: nada recién publicado).
    "codex": ["npx", "-y", "@zed-industries/codex-acp@0.16.0"],
    "claude": ["npx", "-y", "@zed-industries/claude-code-acp@0.16.2"],
    "gemini": ["gemini", "--experimental-acp"],
}
ESPERA_PERMISO = 300
MAX_MENSAJE = 4000
ARCHIVO_CHAT = "chat.jsonl"
ARCHIVO_SESION = ".narrador.json"
TIPOS_LECTURA = {"read", "search", "think"}


class Ocupado(RuntimeError):
    """El narrador ya está respondiendo en esta partida."""


def ruta_chat(slug: str) -> Path:
    return estado.dir_partida(slug) / ARCHIVO_CHAT


def leer_chat(slug: str, desde: int = 0) -> list[dict]:
    ruta = ruta_chat(slug)
    if not ruta.exists():
        return []
    mensajes = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            m = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if m.get("seq", 0) > desde:
            mensajes.append(m)
    return mensajes


def _ultimo_evento(slug: str) -> int:
    eventos = estado.leer_eventos(slug)
    return eventos[-1]["seq"] if eventos else 0


def nombre_narrador(agente: str, modelo: str | None) -> str:
    """«hermes» + «nvidia:moonshotai/kimi-k3» → «hermes/kimi-k3» (harness/modelo, como pide el contrato)."""
    if not modelo:
        return agente
    return f"{agente}/{re.split(r'[:/]', modelo)[-1]}"


def preambulo(slug: str, narrador: str) -> str:
    carpeta = estado.dir_partida(slug)
    return (
        "[Mesa de rol · chat del visor]\n"
        f"Eres el director de juego de la partida `{slug}` y sigues el AGENTS.md del repo. "
        "Lo que escribes aparece en el chat del visor, que el jugador lee en el navegador; las tiradas, "
        "los cambios, los documentos y los hechos que registras con las herramientas `mesa` aparecen solos "
        "como tarjetas dentro del chat, así que no hace falta copiarlos enteros (sí el RESULTADO, en una línea).\n"
        f"Solo esta vez, antes de responder: herramienta `retomar` con narrador=\"{narrador}\" (la partida ya está "
        f"activa: no pases otra), y lee `{carpeta / 'biblia.md'}` y `{carpeta / 'director.md'}` con tu herramienta de "
        "archivos (director.md es secreto: jamás lo cites ni lo resumas en el chat). No busques otros archivos: "
        "`retomar` ya trae la memoria, el estado, los mapas y los últimos eventos.\n"
        "En cada turno: tira con las herramientas cuando haga falta, registra con `turno` (incluyendo siempre "
        "`escena posicion <quien> \"<dónde>\" --celda <C4>` si se mueve, y `mapa cargar`/`mapa generar` + "
        "`mundo aqui` si cambia de lugar o de escena) y responde.\n"
        "Nunca hables por un PJ que juega una persona (todos salvo los que tengan `piloto: narrador`): ni sus "
        "palabras, ni sus decisiones, ni lo que piensa o siente. Narra el mundo y los PNJ; si falta la acción de "
        "alguien, congela la escena y pregúntale. Cada mensaje llega con el nombre del PJ que habla entre corchetes; "
        "si `turno` avisa «sin declarar», díselo a ese jugador para que decida si lo da por bueno.\n"
        "Responde ahora a este mensaje del jugador:\n\n"
    )


# Verbos con los que un narrador pone voz, decisión o sentimiento a un personaje.
_VERBOS_DE_VOZ = (
    r"(?:dice|dijo|responde|respondi[oó]|contesta|contest[oó]|grita|grit[oó]|susurra|susurr[oó]|murmura|murmur[oó]|"
    r"exclama|exclam[oó]|pregunta|pregunt[oó]|decide|decidi[oó]|piensa|pens[oó]|siente|sinti[oó])"
)


def voces_de_pj(texto: str, nombres: list[str]) -> list[str]:
    """PJ a los que el texto parece poner palabras, decisiones o sentimientos (heurística: solo avisa).

    Detecta «**Kael:** …», «—…—, dice Kael» y «Kael decide/piensa/siente…».
    """
    encontrados = []
    for nombre in nombres:
        n = re.escape(nombre)
        patrones = (
            rf"(?m)^\s*[*_]*{n}[*_]*\s*:",
            rf"[—–\"«“][^\n]{{1,240}}?[—–\"»”]\s*,?\s*{_VERBOS_DE_VOZ}\s+{n}(?!\w)",
            rf"(?<!\w){n}\s+{_VERBOS_DE_VOZ}(?!\w)",
        )
        if any(re.search(p, texto or "", re.IGNORECASE) for p in patrones):
            encontrados.append(nombre)
    return encontrados


def _texto_seguro(texto: str, maximo: int = 200) -> str:
    limpio = " ".join(str(texto or "").split())
    return limpio if len(limpio) <= maximo else limpio[: maximo - 1] + "…"


def _es_herramienta_mesa(tool: dict) -> bool:
    titulo = str(tool.get("title") or "").lower()
    crudo = json.dumps(tool.get("rawInput") or {}, ensure_ascii=False).lower()[:300]
    return bool(re.search(r"\bmesa\b|mcp[_:.-]+mesa|mesa[_:.-]", titulo) or '"server": "mesa"' in crudo)


def _aviso_de_herramienta(tool: dict) -> str:
    """Qué está haciendo el narrador, sin contenido: puede tocar secretos."""
    if _es_herramienta_mesa(tool):
        nombre = re.split(r"[_:.\-\s]+", str(tool.get("title") or ""))[-1] or "mesa"
        return f"registra en la mesa ({_texto_seguro(nombre, 30)})"
    return {"read": "consulta sus notas", "search": "busca en sus notas", "edit": "anota en sus notas",
            "think": "piensa", "execute": "ejecuta un comando", "fetch": "consulta fuera"}.get(tool.get("kind"), "trabaja")


class Narrador:
    """El narrador del visor: un agente ACP por partida, un turno a la vez."""

    def __init__(self, agente: str, comando: list[str] | None = None, cwd: str | None = None):
        self.agente = agente
        self.comando = comando or AGENTES[agente]
        self.cwd = str(cwd or estado.RAIZ)
        self._partidas: dict[str, dict] = {}
        self._cerrojo = threading.Lock()

    # ---------- estado por partida ----------

    def _p(self, slug: str) -> dict:
        with self._cerrojo:
            return self._partidas.setdefault(slug, {
                "cliente": None, "sesion": None, "en_curso": None, "cargando": False,
                "permiso": None, "escritura": threading.Lock(), "nombre": self.agente,
            })

    def _mcp(self, slug: str) -> list[dict]:
        """El MCP de juego para esta partida: el mismo Python y la misma raíz de datos que el visor."""
        paquete = str(Path(__file__).resolve().parent.parent)
        env = [
            {"name": "MESA_RAIZ", "value": str(estado.RAIZ)}, {"name": "MESA_PARTIDA", "value": slug},
            {"name": "PYTHONPATH", "value": paquete + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")},
        ]
        return [{"name": "mesa", "command": sys.executable, "args": ["-m", "mesa.mcp"], "env": env}]

    def _sesion_guardada(self, slug: str) -> dict:
        ruta = estado.dir_partida(slug) / ARCHIVO_SESION
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return datos if datos.get("agente") == self.agente else {}

    def _guardar_sesion(self, slug: str, sesion: str | None, nombre: str) -> None:
        ruta = estado.dir_partida(slug) / ARCHIVO_SESION
        if sesion is None:
            ruta.unlink(missing_ok=True)
            return
        ruta.write_text(json.dumps({"agente": self.agente, "sesion": sesion, "nombre": nombre, "desde": estado.ahora()}) + "\n", encoding="utf-8")

    def _anotar(self, slug: str, mensaje: dict) -> dict:
        p = self._p(slug)
        with p["escritura"]:
            previos = leer_chat(slug)
            completo = {"seq": (previos[-1]["seq"] if previos else 0) + 1, "ts": estado.ahora(), **mensaje}
            with ruta_chat(slug).open("a", encoding="utf-8") as f:
                f.write(json.dumps(completo, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        return completo

    # ---------- lo que ve el visor ----------

    def vista(self, slug: str) -> dict:
        p = self._p(slug)
        guardada = self._sesion_guardada(slug)
        en_curso = p["en_curso"]
        return {
            "activo": True, "agente": self.agente, "agentes": list(AGENTES),
            "nombre": p["nombre"] if p["sesion"] else guardada.get("nombre", self.agente),
            "sesion": bool(p["sesion"] or guardada.get("sesion")),
            "en_curso": None if en_curso is None else {
                **{k: en_curso[k] for k in ("id", "aviso", "desde", "inicio")}, "partes": [dict(x) for x in en_curso["partes"]],
            },
            "permiso": None if p["permiso"] is None else {k: p["permiso"][k] for k in ("id", "titulo", "tipo")},
        }

    # ---------- acciones ----------

    def enviar(self, slug: str, texto: str, autor: str = "jugador", *, fuera_de_personaje: bool = False,
               texto_agente: str | None = None) -> dict:
        """Anota el mensaje y despierta al narrador. `texto_agente` es lo que recibe el agente si
        difiere de lo publicado (por ejemplo, una tirada con datos que los jugadores no ven)."""
        texto = str(texto or "").strip()
        if not texto:
            raise ValueError("el mensaje está vacío")
        if len(texto) > MAX_MENSAJE:
            raise ValueError(f"el mensaje tiene {len(texto)} caracteres; el máximo es {MAX_MENSAJE}")
        p = self._p(slug)
        with self._cerrojo:
            if p["en_curso"] is not None:
                raise Ocupado("el narrador todavía está respondiendo: espera o detén su turno")
            p["en_curso"] = {"id": uuid.uuid4().hex[:12], "partes": [], "aviso": "lee la mesa", "desde": _ultimo_evento(slug), "inicio": estado.ahora()}
        try:
            entrada = {"rol": "jugador", "autor": autor, "texto": texto}
            if fuera_de_personaje:
                entrada["ooc"] = True
            mensaje = self._anotar(slug, entrada)
        except Exception:
            p["en_curso"] = None
            raise
        al_agente = str(texto_agente).strip()[:MAX_MENSAJE] if texto_agente else texto
        threading.Thread(target=self._turno, args=(slug, al_agente, autor, fuera_de_personaje), daemon=True).start()
        return mensaje

    def cancelar(self, slug: str) -> bool:
        p = self._p(slug)
        if p["en_curso"] is None or p["cliente"] is None or not p["sesion"]:
            return False
        if p["permiso"] is not None:
            self.responder_permiso(slug, p["permiso"]["id"], False)
        p["cliente"].cancelar(p["sesion"])
        return True

    def nueva_sesion(self, slug: str) -> None:
        p = self._p(slug)
        if p["en_curso"] is not None:
            raise Ocupado("el narrador está respondiendo: detén su turno antes de abrir una sesión nueva")
        p["sesion"] = None
        self._guardar_sesion(slug, None, self.agente)
        self._anotar(slug, {"rol": "sistema", "texto": "Sesión nueva del narrador: al próximo mensaje retoma desde la memoria de la historia."})

    def cambiar_agente(self, slug: str, agente: str) -> None:
        if agente not in AGENTES:
            raise ValueError(f"agente desconocido: {agente!r} (valen: {', '.join(AGENTES)})")
        p = self._p(slug)
        if p["en_curso"] is not None:
            raise Ocupado("el narrador está respondiendo: detén su turno antes de cambiar de agente")
        if p["cliente"] is not None:
            p["cliente"].cerrar()
            p["cliente"] = None
        p["sesion"] = None
        p["nombre"] = agente
        self.agente = agente
        self.comando = AGENTES[agente]
        self._anotar(slug, {"rol": "sistema", "texto": f"Narrador cambiado a `{agente}`: al próximo mensaje retoma la partida."})

    def responder_permiso(self, slug: str, ident: str, permitir: bool) -> None:
        permiso = self._p(slug)["permiso"]
        if permiso is None or permiso["id"] != ident:
            raise ValueError("ese permiso ya no está pendiente")
        permiso["decision"] = bool(permitir)
        permiso["listo"].set()

    def cerrar(self) -> None:
        for p in list(self._partidas.values()):
            if p["cliente"] is not None:
                p["cliente"].cerrar()

    # ---------- el turno ----------

    def _cliente(self, slug: str) -> ClienteACP:
        p = self._p(slug)
        if p["cliente"] is not None and p["cliente"].vivo:
            return p["cliente"]
        cliente = ClienteACP(
            self.comando, self.cwd,
            al_actualizar=lambda sesion, update: self._al_actualizar(slug, update),
            al_pedir_permiso=lambda params: self._al_pedir_permiso(slug, params),
        )
        try:
            cliente.iniciar()
        except ErrorACP:
            cliente.cerrar()
            raise
        p["cliente"], p["sesion"] = cliente, None
        return cliente

    def _abrir_sesion(self, slug: str, cliente: ClienteACP) -> bool:
        """Devuelve True si la sesión es nueva (hay que mandar el preámbulo)."""
        p = self._p(slug)
        if p["sesion"]:
            return False
        guardada = self._sesion_guardada(slug)
        if guardada.get("sesion"):
            p["cargando"] = True  # al cargar, el agente repite la historia: no es de este turno
            try:
                cargada = cliente.cargar_sesion(guardada["sesion"], self._mcp(slug))
            finally:
                p["cargando"] = False
            if cargada:
                p["sesion"], p["nombre"] = guardada["sesion"], guardada.get("nombre", self.agente)
                return False
        r = cliente.nueva_sesion(self._mcp(slug))
        modelos = r.get("models") or {}
        p["sesion"] = r["sessionId"]
        p["nombre"] = nombre_narrador(self.agente, modelos.get("currentModelId"))
        self._guardar_sesion(slug, p["sesion"], p["nombre"])
        return True

    def _turno(self, slug: str, texto: str, autor: str, fuera_de_personaje: bool = False) -> None:
        p = self._p(slug)
        en_curso = p["en_curso"]
        inicio = time.monotonic()
        vigia = threading.Event()
        threading.Thread(target=self._vigilar_bitacora, args=(slug, vigia), daemon=True).start()
        try:
            cliente = self._cliente(slug)
            nueva = self._abrir_sesion(slug, cliente)
            if fuera_de_personaje:
                quien_txt = f" ({autor})" if autor and autor != "jugador" else ""
                mensaje_agente = (
                    f"[CONSULTA FUERA DE PERSONAJE AL GM{quien_txt} — CONGELA LA ESCENA: "
                    "responde la duda sobre la partida, el mundo, pistas o reglas sin avanzar el turno, "
                    "sin tirar dados con riesgo ni gastar acciones de ningún personaje, y vuelve a dejar "
                    f"la decisión abierta]: {texto}"
                )
            else:
                mensaje_agente = f"[{autor}] {texto}" if autor and autor != "jugador" else texto
            motivo = cliente.preguntar(p["sesion"], (preambulo(slug, p["nombre"]) if nueva else "") + mensaje_agente)
            self._sumar_eventos(slug)
            partes = en_curso["partes"]
            texto_final = "".join(x["texto"] for x in partes if x["tipo"] == "texto").strip()
            if not partes:
                partes.append({"tipo": "texto", "texto": "(el narrador no respondió nada)"})
            self._anotar(slug, {
                "rol": "narrador", "autor": p["nombre"], "texto": texto_final, "partes": partes, "parada": motivo,
                "rango": [en_curso["desde"], _ultimo_evento(slug)], "segundos": round(time.monotonic() - inicio, 1),
            })
            humanos = [x["nombre"] for x in estado.cargar(slug).get("personajes", []) if vista.humano(x)]
            voces = voces_de_pj(texto_final, humanos)
            if voces:
                self._anotar(slug, {"rol": "sistema", "aviso": "voz_de_pj", "quien": voces, "texto": (
                    f"⚠ Puede que el narrador haya hablado o decidido por {', '.join(voces)}. "
                    "Si no lo das por bueno, dilo en el chat y se corrige."
                )})
        except Exception as e:  # frontera del hilo: cualquier fallo queda en el chat, nunca un turno colgado
            self._sumar_eventos(slug)
            if en_curso["partes"]:
                self._anotar(slug, {"rol": "narrador", "autor": p["nombre"], "texto": "", "partes": en_curso["partes"],
                                    "parada": "error", "rango": [en_curso["desde"], _ultimo_evento(slug)]})
            self._anotar(slug, {"rol": "sistema", "texto": f"El narrador falló: {_texto_seguro(str(e), 400)}"})
            if p["cliente"] is not None and not p["cliente"].vivo:
                p["cliente"].cerrar()
                p["cliente"] = None
                p["sesion"] = None
        finally:
            vigia.set()
            p["permiso"] = None
            p["en_curso"] = None

    def _vigilar_bitacora(self, slug: str, fin: threading.Event) -> None:
        while not fin.wait(0.4):
            self._sumar_eventos(slug)

    def _sumar_eventos(self, slug: str) -> None:
        """Lo nuevo de la bitácora entra en el mensaje en curso, en el orden en que pasó."""
        en_curso = self._p(slug)["en_curso"]
        if en_curso is None:
            return
        vistos = {x["seq"] for x in en_curso["partes"] if x["tipo"] == "evento"}
        for e in estado.leer_eventos(slug, en_curso["desde"]):
            if e["seq"] not in vistos:
                en_curso["partes"].append({"tipo": "evento", "seq": e["seq"]})

    def _al_actualizar(self, slug: str, update: dict) -> None:
        p = self._p(slug)
        en_curso = p["en_curso"]
        if en_curso is None or p["cargando"]:
            return
        tipo = update.get("sessionUpdate")
        if tipo == "agent_message_chunk":
            contenido = update.get("content") or {}
            trozo = contenido.get("text", "") if contenido.get("type", "text") == "text" else ""
            if trozo:
                self._sumar_eventos(slug)
                partes = en_curso["partes"]
                if partes and partes[-1]["tipo"] == "texto":
                    partes[-1]["texto"] += trozo
                else:
                    partes.append({"tipo": "texto", "texto": trozo})
                en_curso["aviso"] = "escribe"
        elif tipo == "tool_call":
            en_curso["aviso"] = _aviso_de_herramienta(update)
        elif tipo == "tool_call_update" and update.get("status") in ("completed", "failed"):
            self._sumar_eventos(slug)
            en_curso["aviso"] = "sigue"
        elif tipo == "agent_thought_chunk":
            en_curso["aviso"] = "piensa"

    def _al_pedir_permiso(self, slug: str, params: dict) -> str | None:
        tool = params.get("toolCall") or {}
        opciones = params.get("options") or []
        tipo = tool.get("kind")
        if _es_herramienta_mesa(tool) or tipo in TIPOS_LECTURA or (tipo == "edit" and self._dentro_de_la_partida(slug, tool)):
            return elegir_opcion(opciones, True)
        p = self._p(slug)
        permiso = {"id": uuid.uuid4().hex[:10], "titulo": _texto_seguro(tool.get("title") or "una acción sin nombre"),
                   "tipo": tipo or "otro", "listo": threading.Event(), "decision": False}
        p["permiso"] = permiso
        if p["en_curso"] is not None:
            p["en_curso"]["aviso"] = "espera tu permiso"
        permiso["listo"].wait(ESPERA_PERMISO)
        p["permiso"] = None
        self._anotar(slug, {"rol": "sistema", "texto": f"{'Permitido' if permiso['decision'] else 'Rechazado'}: {permiso['titulo']}"})
        return elegir_opcion(opciones, permiso["decision"])

    def _dentro_de_la_partida(self, slug: str, tool: dict) -> bool:
        base = estado.dir_partida(slug).resolve()
        rutas = [x.get("path") for x in tool.get("locations") or [] if x.get("path")]
        return bool(rutas) and all(Path(r).resolve().is_relative_to(base) for r in rutas)

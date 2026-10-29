// Chat con el narrador: historial, compositor y envío de mensajes.
import {
  $, app, CLASE_DOCUMENTO, colorSeguro, ES_TIRADA, enviarPost, esc, es2024, guardarLocal,
  hooks, leerLocal, mostrarError, reclamarPj, refrescarVisor, sinTildes,
} from "./nucleo.js";
import { animarDados, tarjetaDados } from "./dados.js";
import { elegirPjActivo, pintarFichas } from "./ficha.js";

const sondear = (...a) => hooks.sondear(...a);

function enLinea(s) {
  return s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*\w])\*([^*\n]+)\*/g, "$1<i>$2</i>").replace(/`([^`\n]+)`/g, "<code>$1</code>");
}
function md(texto) {
  const salida = [];
  let tipo = null, grupo = [];
  const cerrar = () => {
    if (!grupo.length) return;
    if (tipo === "lista") salida.push(`<ul>${grupo.map((l) => `<li>${enLinea(l)}</li>`).join("")}</ul>`);
    else if (tipo === "cita") salida.push(`<blockquote>${enLinea(grupo.join("<br>"))}</blockquote>`);
    else salida.push(`<p>${enLinea(grupo.join("<br>"))}</p>`);
    grupo = [];
  };
  for (const linea of esc(String(texto || "").trim()).split("\n")) {
    const [nuevo, contenido] = !linea.trim() ? [null, null]
      : /^\s*[-*] /.test(linea) ? ["lista", linea.replace(/^\s*[-*] /, "")]
        : linea.startsWith("&gt;") ? ["cita", linea.replace(/^&gt; ?/, "")]
          : /^#{1,4} /.test(linea) ? ["titulo", linea.replace(/^#{1,4} /, "")] : ["parrafo", linea];
    if (nuevo !== tipo || nuevo === "titulo" || nuevo === null) cerrar();
    tipo = nuevo;
    if (nuevo === "titulo") salida.push(`<h4>${enLinea(contenido)}</h4>`);
    else if (nuevo) grupo.push(contenido);
  }
  cerrar();
  return salida.join("");
}

const hora = (ts) => String(ts || "").slice(11, 16);
function pjPorNombre(nombre) {
  const q = sinTildes(nombre);
  return (app.datos?.personajes || []).find((p) => [sinTildes(p.nombre), sinTildes(p.id)].includes(q));
}
function nombreJugador(m) {
  // Firma quien firma (un PJ o «Mesa»); solo un mensaje sin firma se atribuye al único PJ.
  if (m.autor && m.autor !== "jugador") return m.autor;
  const pjs = app.datos?.personajes || [];
  return pjs.length === 1 ? pjs[0].nombre : "Jugador";
}
function burbuja(rol, nombre, cuerpo, sub = "") {
  const pj = rol === "jugador" ? pjPorNombre(nombre) : null;
  const color = rol === "narrador" ? "var(--acento)" : colorSeguro(pj?.color, "var(--texto-3)");
  const avatar = rol === "narrador" ? "✦" : esc((nombre || "?").trim().charAt(0).toUpperCase());
  return `<article class="msg ${rol}"><div class="avatar" style="--c:${color}" aria-hidden="true">${avatar}</div>
    <div class="burbuja"><header><b>${esc(nombre)}</b>${sub ? ` <small>${esc(sub)}</small>` : ""}</header>${cuerpo}</div></article>`;
}

function tarjetaEvento(e) {
  if (!e) return "";
  if (ES_TIRADA.has(e.tipo)) return tarjetaDados(e, e.seq > app.seqInicial && !app.animados.has(e.seq));
  const t = (clase, html, vista = "") => `<div class="tarjeta-evento t-${clase}"${vista ? ` data-abrir="${vista}" role="button" tabindex="0" title="Ver en el panel"` : ""}>${html}</div>`;
  const tras = (x) => `${esc(x.antes)} → <b>${esc(x.despues)}</b>/${esc(x.maximo)}`;
  switch (e.tipo) {
    case "vida":
      if (e.redactado) return t("dano", `<b>${esc(e.quien)}</b> · ${esc(e.estado || "herido")}${e.motivo ? ` <span class="texto-3">· ${esc(e.motivo)}</span>` : ""}`, "ficha");
      return t((e.despues ?? 0) < (e.antes ?? 0) ? "dano" : "cura", `<b>${esc(e.quien)}</b> · vida ${tras(e)}${e.motivo ? ` <span class="texto-3">· ${esc(e.motivo)}</span>` : ""}`, "ficha");
    case "vendaje": return t("cura", `Vendaje a <b>${esc(e.quien)}</b> · vida ${tras(e)}`, "ficha");
    case "condicion": return t("condicion", e.accion === "agregar" ? `<b>${esc(e.quien)}</b> queda <b>${esc(e.nombre)}</b>` : `<b>${esc(e.quien)}</b> ya no está ${esc(e.nombre)}`, "ficha");
    case "habilidad": return t("habilidad", `<b>${esc(e.quien)}</b> · «${esc(e.nombre)}» ${e.disponible ? "disponible" : "gastada"}`, "ficha");
    case "nivel": return t("cura", `<b>${esc(e.quien)}</b> sube a nivel ${esc(e.nivel)}: ${esc(e.mejora)}`, "ficha");
    case "descanso": return t("cura", `Descanso ${esc(e.clase)}${(e.cambios || []).length ? `: ${esc(e.cambios.join(" · "))}` : ""}`, "ficha");
    case "enemigo": return t("dano", e.accion === "agregar" ? `Amenaza en escena: <b>${esc(e.nombre)}</b>` : e.accion === "quitar" ? `${esc(e.nombre)} sale de escena` : `Fin del combate${e.recargadas ? ` · se recargan ${esc(e.recargadas.join("; "))}` : ""}`, "ficha");
    case "pista": return t("pista", `<span class="eyebrow">Pista</span> ${esc(e.texto)}`, "registro");
    case "trama": return t("pista", `<span class="eyebrow">Trama</span> <b>${esc(e.nombre)}</b> [${esc(e.estado)}]${e.nota ? `: ${esc(e.nota)}` : ""}`, "registro");
    case "misterio": return t("pista", `<span class="eyebrow">${e.resuelto ? "Pregunta resuelta" : "Pregunta abierta"}</span> ${esc(e.texto)}`, "registro");
    case "pnj": return t("pnj", `<b>${esc(e.nombre)}</b> <span class="actitud" data-a="${esc(e.actitud)}">${esc(e.actitud)}</span>${e.nota ? ` ${esc(e.nota)}` : ""}`, "registro");
    case "recurso": return t("recurso", `${esc(e.clave)}: <b>${esc(e.valor)}</b>`, "registro");
    case "reloj": return t("recurso", `Día ${esc(e.dia ?? "?")}${e.hora ? ` · ${esc(e.hora)}` : ""}${(e.plazos || []).length ? ` · ⏳ ${esc(e.plazos.join("; "))}` : ""}`);
    case "regla": return t("regla", `<span class="eyebrow">Regla de la casa ${esc(e.id)}</span> ${esc(e.texto)}`, "registro");
    case "hecho":
      // En la historia cuentan los hechos nuevos y las correcciones del narrador; fijar o archivar es ordenar la memoria.
      if (!(e.accion === "agregar" || (e.accion === "editar" && e.autor !== "jugador"))) return "";
      return t("hecho", `<span class="eyebrow">Hecho clave ${esc(e.id)}${e.accion !== "agregar" ? ` · ${esc(e.accion)}` : ""}</span> ${esc(e.texto || "")}${e.autor === "jugador" ? ' <span class="texto-3">· lo anotaste tú</span>' : ""}`, "hechos");
    case "memoria":
      if (e.autor === "jugador" || e.accion === "presupuesto") return "";
      return t("hecho", e.accion === "escena" ? `<span class="eyebrow">Crónica · escena ${esc(e.numero)}</span> ${esc(e.texto || "")}` : e.accion === "presupuesto" ? `Presupuesto de memoria: ${esc(e.presupuesto)}` : '<span class="eyebrow">Hasta ahora</span> actualizado', "hechos");
    case "mapa": return e.accion === "zona" ? t("mapa", `Mapa de la zona${e.nombre ? `: <b>${esc(e.nombre)}</b>` : ""} (${esc(e.columnas)}×${esc(e.filas)} casillas)`, "zona") : "";
    case "mundo":
      if (e.accion === "aqui") return t("mapa", `Ahora en <b>${esc(e.nombre)}</b>`, "mundo");
      return e.accion === "lugar" && e.nuevo ? t("mapa", `Nuevo lugar en el mapa: <b>${esc(e.nombre)}</b>`, "mundo") : "";
    case "escena":
      return e.accion === "nueva" ? `<div class="divisor-escena"><span>Escena ${esc(e.numero)} · ${esc(e.titulo || "")}${e.lugar ? ` — ${esc(e.lugar)}` : ""}</span></div>` : "";
    case "documento": {
      const doc = (app.datos?.documentos || []).find((x) => x.id === e.id);
      if (!doc) return t("pista", `Documento «${esc(e.titulo)}»`, "registro");
      return `<article class="documento en-chat" data-clase="${esc(doc.clase)}"><header><span class="clase">${esc(CLASE_DOCUMENTO[doc.clase] || "Documento")}</span><h3>${esc(doc.titulo)}</h3></header><p class="cuerpo">${esc(doc.texto)}</p><footer>${esc(doc.fuente || "")}</footer></article>`;
    }
    case "nota": return `<p class="nota-chat">${esc(e.texto)}</p>`;
    case "turno": {
      // El narrador no habla por los jugadores: si registró algo que su jugador no escribió, se ve aquí.
      const sin = e.sin_declarar || [];
      if (!sin.length) return "";
      const lineas = sin.map((pj) => {
        const clave = Object.keys(e.acciones || {}).find((k) => sinTildes(pj).startsWith(sinTildes(k)));
        return `<b>${esc(pj)}</b>${clave ? ` «${esc(e.acciones[clave])}»` : ""}`;
      }).join("; ");
      return t("condicion", `<span class="eyebrow">⚠ Sin declarar por su jugador</span> El narrador registró por ${lineas}. Si no lo das por bueno, dilo en el chat y se corrige.`);
    }
    case "piloto": return t("regla", e.piloto === "narrador" ? `<b>${esc(e.quien)}</b> lo lleva el narrador mientras falta su jugador` : `<b>${esc(e.quien)}</b> vuelve a jugarlo su jugador`, "ficha");
    default: return "";
  }
}

function partesHTML(partes, porSeq) {
  return partes.map((p) => (p.tipo === "texto" ? `<div class="narracion-chat">${md(p.texto)}</div>` : tarjetaEvento(porSeq.get(p.seq)))).join("");
}

function htmlMensaje(m, porSeq) {
  if (m.rol === "sistema") return `<p class="sistema">${esc(m.texto)}</p>`;
  if (m.rol === "jugador") {
    const badge = m.ooc ? '<span class="etiqueta-ooc">Fuera de personaje · GM</span>' : "";
    const sub = [m.ooc ? "consulta al GM" : "", hora(m.ts)].filter(Boolean).join(" · ");
    return burbuja("jugador", nombreJugador(m), `<p>${badge}${esc(m.texto).replace(/\n/g, "<br>")}</p>`, sub);
  }
  const sub = [m.autor, hora(m.ts), m.parada && m.parada !== "end_turn" ? ({ cancelled: "detenido", error: "interrumpido" }[m.parada] || m.parada) : ""].filter(Boolean).join(" · ");
  return burbuja("narrador", "Narrador", partesHTML(m.partes || [{ tipo: "texto", texto: m.texto }], porSeq), sub);
}

// Un turno narrado desde la terminal: lo que declaró cada uno, lo que pasó en la mesa y el resumen.
function htmlTurnoTerminal(turno, grupo) {
  const sin = (turno.sin_declarar || []).map(sinTildes);
  const acciones = Object.entries(turno.acciones || {}).map(([k, v]) => burbuja("jugador", k, `<p>${esc(v)}</p>`,
    [hora(turno.ts), sin.some((s) => s.startsWith(sinTildes(k))) ? "⚠ lo registró el narrador: sin declarar" : ""].filter(Boolean).join(" · "))).join("");
  const tarjetas = grupo.map(tarjetaEvento).join("");
  return acciones + (tarjetas ? `<div class="tarjetas-sueltas">${tarjetas}</div>` : "")
    + burbuja("narrador", "Narrador", `<p class="resumen-terminal">${esc(turno.resumen)}</p>`, `${turno.narrador || "terminal"} · resumen del turno`);
}

function itemsDelChat() {
  const rangos = app.chat.filter((m) => m.rol === "narrador" && m.rango).map((m) => m.rango);
  const desdeVivo = app.narrador?.en_curso?.desde;
  const cubierto = (seq) => rangos.some(([a, b]) => seq > a && seq <= b) || (desdeVivo != null && seq > desdeVivo);
  const porSeq = new Map(app.eventos.map((e) => [e.seq, e]));
  const items = app.chat.map((m) => ({ ts: m.ts, orden: 1, html: htmlMensaje(m, porSeq) }));
  let grupo = [];
  for (const e of app.eventos) {
    if (cubierto(e.seq)) continue;
    if (e.tipo === "turno") {
      items.push({ ts: grupo[0]?.ts || e.ts, orden: 0, html: htmlTurnoTerminal(e, grupo) });
      grupo = [];
    } else if (tarjetaEvento(e)) {
      grupo.push(e);
    }
  }
  grupo.forEach((e) => items.push({ ts: e.ts, orden: 0, html: tarjetaEvento(e) }));
  return items.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : a.orden - b.orden));
}

function cercaDelFinal() {
  const c = $("#chat");
  return c.scrollTop + c.clientHeight >= c.scrollHeight - 120;
}

function pintarChat(forzar = false) {
  const n = app.narrador || {};
  const abajo = cercaDelFinal();
  const firmaH = JSON.stringify([app.chatSeq, app.ultimoSeq, n.en_curso?.desde ?? null, app.datos?.version ?? null, app.escritura]);
  if (forzar || firmaH !== app.firmaHistorial) {
    app.firmaHistorial = firmaH;
    const items = itemsDelChat();
    const btnAmbiente = app.escritura ? '<div class="chat-vacio-acciones"><button type="button" class="principal" data-abrir-campana="configurar">✦ Elegir campaña y ambiente para nosotros</button></div>' : "";
    $("#chat-historial").innerHTML = items.map((i) => i.html).join("") || `<div class="chat-vacio"><h2>${esc(app.datos?.titulo || "")}</h2><p>${app.chatActivo ? "La historia empieza aquí: escribe qué hace tu personaje o configura el ambiente que quieren jugar." : "Todavía no hay turnos."}</p>${btnAmbiente}</div>`;
    animarDados($("#chat-historial"));
  }
  const firmaV = JSON.stringify([n.en_curso, n.permiso]);
  if (forzar || firmaV !== app.firmaVivo) {
    app.firmaVivo = firmaV;
    let html = "";
    if (n.en_curso) {
      const porSeq = new Map(app.eventos.map((e) => [e.seq, e]));
      const cuerpo = partesHTML(n.en_curso.partes || [], porSeq) + `<p class="escribiendo"><span class="puntos" aria-hidden="true"><i></i><i></i><i></i></span> ${esc(n.nombre || "El narrador")} ${esc(n.en_curso.aviso || "piensa")}…</p>`;
      html += burbuja("narrador", "Narrador", cuerpo, "ahora");
    }
    if (n.permiso) {
      html += `<div class="tarjeta-evento t-permiso" role="alertdialog" aria-label="El narrador pide permiso">
        <p><b>El narrador pide permiso</b> para algo que no es de la mesa (${esc(n.permiso.tipo)}):</p>
        <p><code>${esc(n.permiso.titulo)}</code></p>
        ${app.anfitrion ? `<p class="acciones"><button type="button" data-permiso="${esc(n.permiso.id)}" data-permitir="si">Permitir una vez</button> <button type="button" data-permiso="${esc(n.permiso.id)}" data-permitir="no" class="principal">Rechazar</button></p>` : '<p class="texto-3">Lo decide el anfitrión de la mesa, desde su equipo.</p>'}
      </div>`;
    }
    $("#chat-vivo").innerHTML = html;
    animarDados($("#chat-vivo"));
  }
  if (abajo) $("#chat").scrollTop = $("#chat").scrollHeight;
  pintarComposer();
}

function pintarComposer() {
  const n = app.narrador || {};
  const ocupado = Boolean(n.en_curso);
  const puede = app.chatActivo && app.escritura;
  const pedirSala = !app.escritura && app.salaDisponible;
  const botonCampana = $("#boton-campana");
  if (botonCampana) {
    // Cualquiera que escriba en la mesa (anfitrión o sala) puede crear o configurar la campaña.
    botonCampana.hidden = !app.escritura;
    if (!$("#boton-eliminar-campana")) {
      botonCampana.insertAdjacentHTML("afterend", '<button type="button" id="boton-eliminar-campana" title="Eliminar esta campaña (va a la papelera: se puede recuperar)">🗑 Campaña</button>');
    }
    $("#boton-eliminar-campana").hidden = !app.escritura;
  }
  $(".composer-fila").hidden = !puede;
  if ($("#sala-acceso")) $("#sala-acceso").hidden = !pedirSala;
  $("#enviar").disabled = ocupado;
  if ($("#preguntar-gm")) {
    $("#preguntar-gm").disabled = ocupado;
    $("#preguntar-gm").setAttribute("aria-pressed", String(Boolean(app.modoOoc)));
  }
  if ($("#mensaje")) {
    $("#mensaje").placeholder = app.modoOoc
      ? "Pregunta fuera de personaje al GM (reglas, distancias, pistas, dudas… no avanza la escena)"
      : "¿Qué hace tu personaje? (Enter envía · Mayús+Enter, salto de línea)";
  }
  $("#detener").hidden = !ocupado;
  $("#sesion-nueva").hidden = !puede || !app.anfitrion || ocupado || !n.sesion;
  const selJugador = $("#selector-jugador");
  if (selJugador) {
    // Los PJ que lleva el narrador no los reclama nadie.
    const pjs = (app.datos?.personajes || []).filter((p) => p.piloto !== "narrador").map((p) => p.nombre).filter(Boolean);
    const firmaPjs = [pjs.join("|"), app.anfitrion, app.reclamo ? app.jugador : ""].join("#");
    if (selJugador.dataset.opciones !== firmaPjs) {
      selJugador.dataset.opciones = firmaPjs;
      if (app.anfitrion) {
        const guardado = leerLocal(`mesa-jugador-${app.slug}`, pjs[0] || "");
        app.jugador = pjs.includes(guardado) ? guardado : (pjs[0] || "");
      } else if (!app.reclamo) {
        app.jugador = "";  // un invitado elige su PJ: nadie lo elige por él
      }
      const vacia = !app.anfitrion && !app.reclamo ? '<option value="" selected>— Elige tu personaje —</option>' : "";
      selJugador.innerHTML = vacia + pjs.map((nombre) => `<option value="${esc(nombre)}"${nombre === app.jugador ? " selected" : ""}>${app.anfitrion ? "Hablar como" : "Juego como"}: ${esc(nombre)}</option>`).join("");
    }
    selJugador.hidden = !app.escritura || pjs.length < 1;
  }
  const selAgente = $("#selector-agente");
  if (selAgente) {
    const agentes = Array.isArray(n.agentes) && n.agentes.length ? n.agentes : ["hermes", "devin", "codex", "claude", "gemini"];
    const firmaOpciones = agentes.join(",");
    if (selAgente.dataset.opciones !== firmaOpciones) {
      selAgente.dataset.opciones = firmaOpciones;
      selAgente.innerHTML = agentes.map((a) => `<option value="${esc(a)}">CLI: ${esc(a)}</option>`).join("");
    }
    if (n.agente && selAgente.value !== n.agente) selAgente.value = n.agente;
    selAgente.hidden = !puede;
    selAgente.disabled = ocupado;
  }
  const aviso = pedirSala ? "Ingresa la clave de sala para unirte a la partida."
    : !app.chatActivo ? "Este visor está en modo solo lectura (arrancado con --sin-agente)."
    : !app.escritura ? "Solo lectura: desde aquí no se puede escribir (en el equipo de la mesa, por Tailscale o con clave de sala)."
    : !app.anfitrion && !app.reclamo ? "Elige tu personaje («Juego como») para escribir y tirar." : "";
  $("#composer-aviso").hidden = !aviso;
  $("#composer-aviso").textContent = aviso;
  $("#estado-narrador").textContent = !app.chatActivo ? "" : ocupado ? `${n.nombre} ${n.en_curso.aviso}…` : `Narra ${n.nombre || "el narrador"}${n.sesion ? "" : " · al primer mensaje retoma la partida"}`;
}

async function enviarMensaje(forzarOoc = null) {
  const area = $("#mensaje");
  const texto = area.value.trim();
  if (!texto || app.narrador?.en_curso) return;
  const esOoc = forzarOoc !== null ? Boolean(forzarOoc) : Boolean(app.modoOoc);
  $("#enviar").disabled = true;
  if ($("#preguntar-gm")) $("#preguntar-gm").disabled = true;
  try {
    const cuerpo = { texto };
    if (app.jugador) cuerpo.autor = app.jugador;
    if (esOoc) cuerpo.fuera_de_personaje = true;
    await enviarPost("/api/chat", cuerpo);
    area.value = "";
    app.modoOoc = false;
    await sondear();
  } catch (err) {
    $("#estado-narrador").textContent = `✕ ${err.message}`;
  } finally {
    const enCurso = Boolean(app.narrador?.en_curso);
    $("#enviar").disabled = enCurso;
    if ($("#preguntar-gm")) $("#preguntar-gm").disabled = enCurso;
    pintarComposer();
  }
}

$("#preguntar-gm")?.addEventListener("click", () => {
  const area = $("#mensaje");
  if (area && area.value.trim()) {
    enviarMensaje(true);
    return;
  }
  app.modoOoc = !app.modoOoc;
  pintarComposer();
  area?.focus();
});
$("#composer").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!app.escritura && app.salaDisponible && $("#clave-sala-input")) {
    const clave = $("#clave-sala-input").value.trim();
    if (!clave) return;
    app.sala = clave;
    guardarLocal("mesa-sala", clave);
    await refrescarVisor();
    if (app.escritura) {
      location.reload();
      return;
    }
    $("#composer-aviso").hidden = false;
    $("#composer-aviso").textContent = "✕ Clave de sala incorrecta.";
    return;
  }
  enviarMensaje();
});
document.addEventListener("click", async (ev) => {
  if (!ev.target.closest("#boton-eliminar-campana")) return;
  const escrito = prompt(`Para eliminar «${app.datos?.titulo || app.slug}», escribe su nombre corto: ${app.slug}\n(Va a partidas/.papelera y se puede recuperar.)`);
  if (!escrito) return;
  try {
    await enviarPost("/api/campana", { modo: "eliminar", confirmar: escrito.trim() });
    location.search = "";
  } catch (err) {
    mostrarError(err);
  }
});
$("#selector-jugador")?.addEventListener("change", async (ev) => {
  const elegido = ev.target.value;
  if (!app.anfitrion && !(await reclamarPj(elegido))) {
    ev.target.dataset.opciones = "";
    pintarComposer();
    return;
  }
  app.jugador = elegido;
  guardarLocal(`mesa-jugador-${app.slug}`, app.jugador);
  elegirPjActivo(app.jugador);
  pintarFichas();
  pintarComposer();
});
$("#mensaje").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); enviarMensaje(); }
});
$("#detener").addEventListener("click", async () => {
  try { await enviarPost("/api/chat/cancelar", {}); } catch (err) { $("#estado-narrador").textContent = `✕ ${err.message}`; }
});
$("#sesion-nueva").addEventListener("click", async () => {
  if (!confirm("¿Sesión nueva del narrador? Retomará desde la memoria de la historia, sin la conversación anterior.")) return;
  try { await enviarPost("/api/chat/sesion-nueva", {}); await hooks.sondear(); } catch (err) { $("#estado-narrador").textContent = `✕ ${err.message}`; }
});
$("#selector-agente")?.addEventListener("change", async (ev) => {
  try {
    await enviarPost("/api/chat/agente", { agente: ev.target.value });
    await hooks.sondear();
  } catch (err) {
    $("#estado-narrador").textContent = `✕ ${err.message}`;
    await hooks.sondear();
  }
});
$("#chat").addEventListener("click", async (ev) => {
  const permiso = ev.target.closest("button[data-permiso]");
  if (permiso) {
    permiso.disabled = true;
    try { await enviarPost("/api/chat/permiso", { id: permiso.dataset.permiso, permitir: permiso.dataset.permitir === "si" }); } catch (err) { $("#estado-narrador").textContent = `✕ ${err.message}`; }
    return;
  }
  const abrir = ev.target.closest("[data-abrir]");
  if (abrir) {
    hooks.elegirVista(abrir.dataset.abrir);
    const lado = hooks.ladoDe(abrir.dataset.abrir);
    if (getComputedStyle($(`#abrir-${lado}`)).display !== "none" && document.body.dataset.cajon !== lado) hooks.abrirCajon(lado);
  }
});
$("#chat").addEventListener("keydown", (ev) => {
  if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches("[data-abrir]")) { ev.preventDefault(); ev.target.click(); }
});

export { pintarChat, pintarComposer, enviarMensaje };

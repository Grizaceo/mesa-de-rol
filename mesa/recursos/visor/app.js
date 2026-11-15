// Visor de la mesa: el chat con el narrador al centro (con las tiradas y los cambios como tarjetas),
// la ficha, la memoria y el registro a la izquierda, y la zona, el mundo y la ambientación a la derecha.
// Sondea el servidor local; sin narrador en el visor, el centro muestra la bitácora como conversación.
import {
  $, api, app, aplicarTema, CATEGORIAS, esc, guardarLocal, hooks, leerTema,
  refrescarVisor, VISTA_DE_EVENTO, VISTAS_DER, VISTAS_IZQ,
} from "./nucleo.js";
import { pintarFichas } from "./ficha.js";
import { pintarZona } from "./zona.js";
import { pintarMundo } from "./mundo.js";
import { pintarAmbiente, pintarHechos, pintarRegistro } from "./historia.js";
import { pintarChat, pintarComposer } from "./chat.js";
import { actualizarMoodAmbiente, alternarModoSonido, aplicarModoSonido, leerModoSonido } from "./audio.js";
import "./campana.js";
import "./tiradas.js";

$("#boton-sonido")?.addEventListener("click", alternarModoSonido);
$("#boton-tema").addEventListener("click", () => {
  const orden = ["auto", "light", "dark"];
  aplicarTema(orden[(orden.indexOf(leerTema()) + 1) % orden.length]);
});

function pintarVistas() {
  for (const [lado, vistas] of [["izq", VISTAS_IZQ], ["der", VISTAS_DER]]) {
    $(`#vistas-${lado}`).innerHTML = vistas.map(([id, nombre]) => `<button type="button" role="tab" data-v="${id}" aria-selected="${id === app[lado]}" aria-controls="v-${id}">${nombre}${app.novedades.has(id) ? '<span class="novedad" title="Hay novedades">•</span>' : ""}</button>`).join("");
    vistas.forEach(([id]) => { $(`#v-${id}`).hidden = id !== app[lado]; });
  }
  $("#abrir-izq").classList.toggle("con-novedad", VISTAS_IZQ.some(([id]) => app.novedades.has(id)));
  $("#abrir-der").classList.toggle("con-novedad", VISTAS_DER.some(([id]) => app.novedades.has(id)));
}
for (const lado of ["izq", "der"]) {
  $(`#vistas-${lado}`).addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-v]");
    if (b) elegirVista(b.dataset.v);
  });
}
function ladoDe(id) { return VISTAS_IZQ.some(([v]) => v === id) ? "izq" : "der"; }
function elegirVista(id) {
  const lado = ladoDe(id);
  app[lado] = id;
  app.novedades.delete(id);
  guardarLocal(`mesa-${lado}`, id);
  pintarVista();
}

const PINTORES = { ficha: () => pintarFichas(), zona: () => pintarZona(), mundo: () => pintarMundo(), hechos: () => pintarHechos(), ambiente: () => pintarAmbiente(), registro: () => pintarRegistro() };
function pintarVista() {
  pintarVistas();
  if (!app.datos) return;
  PINTORES[app.izq]();
  PINTORES[app.der]();
}

function abrirCajon(lado) {
  document.body.dataset.cajon = document.body.dataset.cajon === lado ? "" : lado;
  $("#velo").hidden = !document.body.dataset.cajon;
  $("#abrir-izq").setAttribute("aria-expanded", String(document.body.dataset.cajon === "izq"));
  $("#abrir-der").setAttribute("aria-expanded", String(document.body.dataset.cajon === "der"));
}
$("#abrir-izq").addEventListener("click", () => abrirCajon("izq"));
$("#abrir-der").addEventListener("click", () => abrirCajon("der"));
$("#velo").addEventListener("click", () => abrirCajon(document.body.dataset.cajon));
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && document.body.dataset.cajon) abrirCajon(document.body.dataset.cajon); });

function pintarEstado() {
  const d = app.datos;
  document.title = `${d.titulo} · Mesa de rol`;
  if (d.tema?.acento) document.documentElement.style.setProperty("--acento", d.tema.acento);
  $("#nombre-historia").textContent = d.titulo;
  const e = d.escena || {};
  $("#reloj").innerHTML = `<span>Día ${esc(d.reloj?.dia ?? "?")}${e.hora ? ` · ${esc(e.hora)}` : ""}</span>${(d.reloj?.plazos || []).map((p) => `<span class="plazo">${esc(p)}</span>`).join("")}`;
  $("#escena-numero").textContent = `Escena ${e.numero ?? ""}`;
  $("#titulo-escena").textContent = e.titulo || "";
  $("#escena-meta").textContent = [e.lugar, e.hora].filter(Boolean).join(" · ");
  actualizarMoodAmbiente(d);
  pintarVista();
}

async function cargarEstado() {
  const datos = await api(`/api/estado?p=${encodeURIComponent(app.slug)}`);
  const firma = JSON.stringify(datos);
  if (firma === app.firmaEstado) return;
  app.firmaEstado = firma;
  app.datos = datos;
  app.firmaZonaMapa = JSON.stringify([datos.escena?.mapa || null, datos.escena?.posiciones || []]);
  pintarEstado();
}

async function cargarChat() {
  const r = await api(`/api/chat?p=${encodeURIComponent(app.slug)}&desde=${app.chatSeq}`);
  if (r.mensajes.length) {
    app.chat.push(...r.mensajes);
    app.chatSeq = r.mensajes.at(-1).seq;
  }
  app.narrador = r.narrador || { activo: false };
  if (r.conectados) {
    app.conectados = r.conectados;
    const el = $("#conectados");
    if (el) {
      const n = Number(r.conectados.total || 0);
      const lista = (r.conectados.jugadores || []).filter(Boolean);
      el.hidden = n < 1;
      el.textContent = `${n} ${n === 1 ? "jugador" : "jugadores"}${lista.length ? ` (${lista.join(", ")})` : ""}`;
      el.title = `Jugadores conectados en esta partida: ${lista.join(", ") || n}`;
    }
  }
  if (Boolean(app.narrador.activo) !== app.chatActivo) {
    await refrescarVisor();
  }
}

function conexion(ok) {
  const n = $("#conexion");
  n.dataset.estado = ok ? "vivo" : "caido";
  n.textContent = ok ? "en vivo" : "sin conexión";
}

async function sondear() {
  if (app.sondeando) return;
  app.sondeando = true;
  try {
    const { eventos } = await api(`/api/eventos?p=${encodeURIComponent(app.slug)}&desde=${app.ultimoSeq}`);
    if (eventos.length) {
      app.eventos.push(...eventos);
      app.ultimoSeq = eventos.at(-1).seq;
      for (const e of eventos) {
        const vista = VISTA_DE_EVENTO[e.tipo];
        if (vista && vista !== app[ladoDe(vista)] && e.autor !== "jugador") app.novedades.add(vista);
      }
    }
    await cargarEstado();
    await cargarChat();
    pintarChat();
    conexion(true);
  } catch (err) {
    conexion(false);
    console.error(err);
  } finally {
    app.sondeando = false;
  }
}

async function bucle() {
  await sondear();
  setTimeout(bucle, app.narrador?.en_curso ? 500 : 1000);
}

hooks.pintarComposer = pintarComposer;
hooks.cargarEstado = cargarEstado;
hooks.pintarVista = pintarVista;
hooks.sondear = sondear;
hooks.elegirVista = elegirVista;
hooks.ladoDe = ladoDe;
hooks.abrirCajon = abrirCajon;

async function iniciar() {
  aplicarTema(leerTema());
  aplicarModoSonido(leerModoSonido());
  $("#nuevo-categoria").innerHTML = CATEGORIAS.map((c) => `<option${c === "otro" ? " selected" : ""}>${c}</option>`).join("");
  pintarVistas();
  try {
    await refrescarVisor();
    if (app.salaDisponible && !app.lectura) {
      $("#nombre-historia").textContent = "Mesa privada: entra con la clave de sala";
      pintarComposer();
      conexion(true);
      return;
    }
    const { activa, partidas } = await api("/api/partidas");
    const pedida = new URLSearchParams(location.search).get("p");
    app.slug = pedida || activa || partidas[0]?.slug;
    $("#selector-partida").innerHTML = partidas.map((p) => `<option value="${esc(p.slug)}"${p.slug === app.slug ? " selected" : ""}>${esc(p.titulo)}</option>`).join("");
    $("#selector-partida").addEventListener("change", (ev) => { location.search = `?p=${encodeURIComponent(ev.target.value)}`; });
    if (!app.slug) {
      $("#nombre-historia").textContent = "No hay partidas: crea la primera con «+ Campaña / Ambiente»";
      pintarComposer();
      return;
    }
    try { app.reclamo = sessionStorage.getItem(`mesa-reclamo-${app.slug}`) || ""; } catch { app.reclamo = ""; }
    await refrescarVisor();
    const { eventos } = await api(`/api/eventos?p=${encodeURIComponent(app.slug)}&desde=0`);
    app.eventos = eventos;
    app.ultimoSeq = app.seqInicial = eventos.at(-1)?.seq ?? 0;
    await cargarEstado();
    await cargarChat();
    pintarChat(true);
    $("#chat").scrollTop = $("#chat").scrollHeight;
    conexion(true);
  } catch (err) {
    conexion(false);
    console.error(err);
  }
  setTimeout(bucle, 1000);
}

iniciar();

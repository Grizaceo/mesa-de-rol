// Hechos, ambientación y registro: la memoria editable y las pestañas del diario.
import {
  $, app, CATEGORIAS, CLASE_DOCUMENTO, enviarPost, esc, guardarLocal, hooks,
} from "./nucleo.js";
import { listaTiradas } from "./dados.js";

const cargarEstado = (...a) => hooks.cargarEstado(...a);

async function enviarMemoria(cuerpo) {
  const aviso = $("#memoria-aviso");
  try {
    const j = await enviarPost("/api/memoria", cuerpo);
    aviso.dataset.tipo = "ok";
    aviso.textContent = `✓ ${j.texto}`;
    app.firmaEstado = "";
    await cargarEstado();
    return true;
  } catch (err) {
    aviso.dataset.tipo = "error";
    aviso.textContent = `✕ No se guardó: ${err.message}`;
    return false;
  }
}

function pintarHechos() {
  $("#nuevo-hecho").hidden = !app.escritura;
  if (app.editando) return; // no pisar lo que el jugador está escribiendo
  const d = app.datos;
  const m = d.memoria || {};
  const uso = d.memoria_uso || { presupuesto: 2400, fijados: 0, libres: 0, en_contexto: [], fuera: [], archivados: [] };
  const enContexto = new Set(uso.en_contexto), fuera = new Set(uso.fuera);
  const pct = uso.presupuesto ? Math.min(100, (100 * uso.libres) / uso.presupuesto) : 0;
  $("#presupuesto").innerHTML = `
    <div class="presupuesto-pista" role="meter" aria-label="Presupuesto de contexto" aria-valuemin="0" aria-valuemax="${uso.presupuesto}" aria-valuenow="${uso.libres}"><div style="width:${pct}%"></div></div>
    <span class="texto-3">No fijados: ${uso.libres} de ${uso.presupuesto} caracteres · fijados: ${uso.fijados} (entran siempre)${uso.fuera.length ? ` · <b>${uso.fuera.length} fuera por presupuesto</b>` : ""}</span>
    ${app.escritura ? "" : '<p class="texto-3">Solo lectura: la memoria se edita desde el visor de este equipo (http://127.0.0.1:…).</p>'}`;
  const editar = (tipo, clave) => (app.escritura ? `<button type="button" class="mini" data-editar="${tipo}" data-clave="${esc(clave)}">Editar</button>` : "");
  $("#hasta-ahora").innerHTML = `<article class="hasta-ahora-caja"><header><h3>Hasta ahora</h3>${editar("hasta-ahora", "")}</header>
    <p class="narracion" data-texto>${m.hasta_ahora ? esc(m.hasta_ahora) : '<span class="texto-3">Todavía no hay resumen de la historia.</span>'}</p></article>`;
  const hechos = m.hechos || [];
  const vigentes = hechos.filter((h) => !h.archivado), archivados = hechos.filter((h) => h.archivado);
  const item = (h) => {
    const estado = h.archivado ? "archivado" : enContexto.has(h.id) ? "contexto" : fuera.has(h.id) ? "fuera" : "contexto";
    const etiqueta = { archivado: "archivado", contexto: "en contexto", fuera: "fuera por presupuesto" }[estado];
    const acciones = !app.escritura ? "" : [
      `<button type="button" class="mini" data-editar="hecho" data-clave="${esc(h.id)}">Editar</button>`,
      h.archivado ? "" : `<button type="button" class="mini" data-a="${h.fijado ? "soltar" : "fijar"}" data-id="${esc(h.id)}">${h.fijado ? "Soltar" : "Fijar"}</button>`,
      `<button type="button" class="mini" data-a="${h.archivado ? "restaurar" : "archivar"}" data-id="${esc(h.id)}">${h.archivado ? "Restaurar" : "Archivar"}</button>`,
    ].join("");
    return `<li class="hecho" data-id="${esc(h.id)}" data-estado="${estado}"${h.fijado ? ' data-fijado="si"' : ""}>
      <div class="hecho-cabeza"><span class="hecho-id">${esc(h.id)}</span><span class="chip">${esc(h.categoria || "otro")}</span>${h.fijado ? '<span class="chip fijado">◆ fijado</span>' : ""}<span class="hecho-estado">${etiqueta}</span></div>
      <p data-texto>${esc(h.texto)}</p>
      <div class="hecho-pie"><span class="texto-3">${esc(h.autor === "jugador" ? "lo anotó el jugador" : "lo propuso el narrador")}${h.escena != null ? ` · escena ${esc(h.escena)}` : ""}${h.editado ? ` · corregido (${esc(h.editado_por || "")})` : ""}</span><span class="acciones">${acciones}</span></div>
    </li>`;
  };
  $("#lista-hechos").innerHTML = (vigentes.length ? `<ol class="hechos">${vigentes.map(item).join("")}</ol>` : '<p class="texto-3">Sin hechos clave todavía. El narrador los propone al cerrar cada escena; también puedes anotarlos tú.</p>')
    + (archivados.length ? `<details class="archivados"><summary>Archivados (${archivados.length}): a la vista, fuera del contexto</summary><ol class="hechos">${archivados.map(item).join("")}</ol></details>` : "");
  const escenas = (m.escenas || []).filter((x) => x.resumen);
  $("#cronica").innerHTML = escenas.length
    ? `<ol class="cronica">${escenas.map((x) => `<li data-numero="${esc(x.numero)}"><header><b>Escena ${esc(x.numero)}${x.titulo ? ` · ${esc(x.titulo)}` : ""}</b>${editar("escena", x.numero)}</header><p data-texto>${esc(x.resumen)}</p></li>`).join("")}</ol>`
    : '<p class="texto-3">Sin escenas cerradas todavía.</p>';
}

function abrirEditor(boton) {
  const tipo = boton.dataset.editar, clave = boton.dataset.clave;
  const m = app.datos.memoria || {};
  const caja = boton.closest("li, article");
  let texto = "", categoria = null, maximo = 500;
  if (tipo === "hecho") {
    const h = (m.hechos || []).find((x) => x.id === clave);
    if (!h) return;
    texto = h.texto; categoria = h.categoria || "otro";
  } else if (tipo === "escena") {
    texto = (m.escenas || []).find((x) => String(x.numero) === clave)?.resumen || ""; maximo = 600;
  } else {
    texto = m.hasta_ahora || ""; maximo = 4000;
  }
  app.editando = { tipo, clave };
  const destino = caja.querySelector("[data-texto]");
  destino.outerHTML = `<form class="editor" data-tipo="${esc(tipo)}" data-clave="${esc(clave)}">
    <textarea rows="${tipo === "hasta-ahora" ? 6 : 3}" maxlength="${maximo}" required>${esc(texto)}</textarea>
    <div class="editor-pie">${categoria ? `<select name="categoria">${CATEGORIAS.map((c) => `<option${c === categoria ? " selected" : ""}>${c}</option>`).join("")}</select>` : ""}
    <span class="texto-3">Ctrl+Enter guarda · Esc cancela</span><button type="button" data-cancelar>Cancelar</button><button type="submit">Guardar</button></div>
  </form>`;
  const area = caja.querySelector(".editor textarea");
  area.focus();
  area.setSelectionRange(area.value.length, area.value.length);
}

$("#v-hechos").addEventListener("click", async (ev) => {
  const editarBoton = ev.target.closest("button[data-editar]");
  if (editarBoton && !app.editando) return abrirEditor(editarBoton);
  if (ev.target.closest("button[data-cancelar]")) { app.editando = null; return pintarHechos(); }
  const accion = ev.target.closest("button[data-a]");
  if (accion && !app.editando) {
    accion.disabled = true;
    await enviarMemoria({ accion: accion.dataset.a, id: accion.dataset.id });
  }
});
$("#v-hechos").addEventListener("keydown", (ev) => {
  const editor = ev.target.closest("form.editor");
  if (!editor) return;
  if (ev.key === "Escape") { app.editando = null; pintarHechos(); }
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); editor.requestSubmit(); }
});
$("#v-hechos").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  if (form.id === "nuevo-hecho") {
    const texto = $("#nuevo-texto").value.trim();
    if (!texto) return;
    if (await enviarMemoria({ accion: "agregar", texto, categoria: $("#nuevo-categoria").value, fijado: $("#nuevo-fijar").checked })) {
      $("#nuevo-texto").value = "";
      $("#nuevo-fijar").checked = false;
    }
    return;
  }
  if (!form.classList.contains("editor")) return;
  const texto = form.querySelector("textarea").value.trim();
  const { tipo, clave } = form.dataset;
  const cuerpo = tipo === "hecho" ? { accion: "editar", id: clave, texto, categoria: form.querySelector("select")?.value }
    : tipo === "escena" ? { accion: "escena", numero: Number(clave), texto } : { accion: "hasta-ahora", texto };
  form.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  const listo = await enviarMemoria(cuerpo);
  if (listo) { app.editando = null; pintarHechos(); } else form.querySelectorAll("button").forEach((b) => { b.disabled = false; });
});

// ---------- ambientación ----------
function pintarAmbiente() {
  const d = app.datos;
  const a = d.ambientacion || {}, r = d.reglas || {};
  const chips = (lista) => (lista || []).map((x) => `<span class="chip">${esc(x)}</span>`).join(" ");
  const filas = [
    ["Época", esc(a.epoca)], ["Lugar", esc(a.lugar)], ["Tono", chips(a.tono)], ["Etiquetas", chips(a.etiquetas)],
    ["Estilo visual", esc(a.estilo_visual)], ["Descripción", esc(a.descripcion)],
  ].filter(([, v]) => v);
  const mesa = [
    ["Reglamento", esc(d.reglamento || "")], ["Unidades", esc(r.unidades)], ["Muerte", esc(r.muerte)], ["Crudeza", esc(r.crudeza)],
  ].filter(([, v]) => v);
  const dl = (pares) => `<dl class="ambiente">${pares.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>`;
  $("#v-ambiente").innerHTML = `
    <h2>${esc(d.titulo || "")}</h2>
    ${filas.length ? dl(filas) : '<p class="texto-3">La ambientación se define en la sesión cero.</p>'}
    ${mesa.length ? `<h3 class="subtitulo-panel">La mesa</h3>${dl(mesa)}` : ""}
    <h3 class="subtitulo-panel">Reglas de la casa</h3>
    ${(d.reglas_casa || []).length ? `<ul class="lista">${d.reglas_casa.map((x) => `<li><b>${esc(x.id)}</b> ${esc(x.texto)} <span class="fuente">(${esc(x.desde || "")})</span></li>`).join("")}</ul>` : '<p class="texto-3">Ninguna todavía.</p>'}`;
}

// ---------- registro ----------
const PESTANAS = [
  ["pnj", "PNJ"], ["pistas", "Pistas"], ["documentos", "Documentos"], ["tramas", "Tramas"], ["misterios", "Preguntas"],
  ["recursos", "Recursos"], ["tiradas", "Tiradas"], ["bitacora", "Bitácora"],
];
if (!PESTANAS.some(([id]) => id === app.pestana)) app.pestana = "pnj";
function pintarPestanas() {
  $("#pestanas").innerHTML = PESTANAS.map(([id, nombre]) => `<button type="button" role="tab" data-p="${id}" aria-selected="${id === app.pestana}">${nombre}</button>`).join("");
}
$("#pestanas").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-p]");
  if (!b) return;
  app.pestana = b.dataset.p;
  guardarLocal("mesa-registro", app.pestana);
  pintarRegistro();
});

function lineaBitacora(e) {
  const cuando = `<div class="cuando">#${e.seq} · ${esc((e.ts || "").replace("T", " ").slice(0, 16))} · ${esc(e.tipo)}${e.autor === "jugador" ? " · jugador" : ""}</div>`;
  if (e.tipo === "turno") return `<li>${cuando}${Object.entries(e.acciones || {}).map(([k, v]) => `<p class="accion"><b>${esc(k)}:</b> ${esc(v)}</p>`).join("")}<p class="resumen">${esc(e.resumen)}</p></li>`;
  if (e.tipo === "escena") return `<li>${cuando}<p class="resumen">Escena ${esc(e.numero)}: ${esc(e.titulo)} — ${esc(e.lugar || "")}</p></li>`;
  if (e.tipo === "documento") return `<li>${cuando}<p>${esc(CLASE_DOCUMENTO[e.clase] || "Documento")}: «${esc(e.titulo)}»</p></li>`;
  if (e.tipo === "hecho") return `<li>${cuando}<p>${esc(e.id)} · ${esc(e.accion)}: ${esc(e.texto || "")}</p></li>`;
  if (e.tipo === "memoria") return `<li>${cuando}<p>${e.accion === "escena" ? `Crónica, escena ${esc(e.numero)}` : e.accion === "presupuesto" ? `Presupuesto: ${esc(e.presupuesto)}` : "Hasta ahora"}${e.texto ? `: ${esc(e.texto)}` : ""}</p></li>`;
  if (e.tipo === "mapa") return `<li>${cuando}<p>${e.accion === "quitar" ? "Mapa de zona retirado" : `Mapa de zona ${esc(e.nombre || "")} (${esc(e.columnas)}×${esc(e.filas)})`}</p></li>`;
  if (e.tipo === "mundo") return `<li>${cuando}<p>Mundo · ${esc(e.accion)}: ${esc(e.nombre || [e.de, e.a].filter(Boolean).join(" – "))}</p></li>`;
  return `<li>${cuando}<p>${esc(e.texto || "")}</p></li>`;
}

function pintarRegistro() {
  pintarPestanas();
  const d = app.datos || {};
  const vacio = '<p class="texto-3">Nada por aquí todavía.</p>';
  let html = "";
  switch (app.pestana) {
    case "pnj":
      html = (d.pnj || []).length ? `<div class="tarjetas">${d.pnj.map((n) => `
        <div class="tarjeta"><h3>${esc(n.nombre)} <span class="actitud" data-a="${esc(n.actitud)}">${esc(n.actitud)}</span></h3>
        <p class="texto-3">${esc(n.rol || "")}</p>${n.estado ? `<p>${esc(n.estado)}</p>` : ""}
        ${(n.notas || []).map((x) => `<p class="texto-2">${esc(x)}</p>`).join("")}</div>`).join("")}</div>` : vacio;
      break;
    case "pistas":
      html = (d.pistas || []).length ? `<ol class="lista">${d.pistas.map((p) => `<li>${esc(p.texto)}${p.fuente ? ` <span class="fuente">— ${esc(p.fuente)}</span>` : ""}</li>`).join("")}</ol>` : vacio;
      break;
    case "documentos":
      html = (d.documentos || []).length ? `<div class="documentos">${[...d.documentos].reverse().map((doc) => `
        <article class="documento${doc.id === app.documentoNuevo ? " nuevo" : ""}" data-clase="${esc(doc.clase)}" data-id="${esc(doc.id)}">
          <header><span class="clase">${esc(CLASE_DOCUMENTO[doc.clase] || "Documento")}</span><h3>${esc(doc.titulo)}</h3></header>
          <p class="cuerpo">${esc(doc.texto)}</p>
          <footer>${[doc.fuente, doc.escena != null ? `escena ${doc.escena}` : ""].filter(Boolean).map(esc).join(" · ")}</footer>
        </article>`).join("")}</div>` : vacio;
      break;
    case "tramas":
      html = (d.tramas || []).length ? `<ul class="lista">${d.tramas.map((t) => `<li><b>${esc(t.nombre)}</b><span class="estado-trama">${esc(t.estado)}</span>${t.nota ? `<br><span class="texto-2">${esc(t.nota)}</span>` : ""}</li>`).join("")}</ul>` : vacio;
      break;
    case "misterios":
      html = (d.misterios || []).length ? `<ul class="lista">${d.misterios.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : vacio;
      break;
    case "recursos":
      html = Object.keys(d.recursos || {}).length ? `<table class="recursos"><tbody>${Object.entries(d.recursos).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("")}</tbody></table>` : vacio;
      break;
    case "tiradas":
      html = listaTiradas();
      break;
    case "bitacora": {
      const tipos = ["turno", "nota", "escena", "regla", "pista", "documento", "hecho", "memoria", "mapa", "mundo"];
      const items = app.eventos.filter((e) => tipos.includes(e.tipo)).slice(-60).reverse();
      html = items.length ? `<ol class="bitacora">${items.map(lineaBitacora).join("")}</ol>` : vacio;
      break;
    }
  }
  $("#mundo").innerHTML = html;
}

export { pintarHechos, pintarAmbiente, pintarRegistro };

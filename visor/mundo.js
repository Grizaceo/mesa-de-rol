// Mapa del mundo: lugares, regiones, trazos y zoom.
import { $, app, cifra, colorSeguro, esc, sinTildes } from "./nucleo.js";

// ---------- mundo ----------
const svgMundo = $("#svg-mundo");
function cajaMundo(lugares, regiones = [], trazos = []) {
  const xs = [], ys = [];
  lugares.forEach((l) => { xs.push(Number(l.x)); ys.push(-Number(l.y)); });
  regiones.forEach((r) => (r.puntos || []).forEach(([px, py]) => { xs.push(Number(px)); ys.push(-Number(py)); }));
  trazos.forEach((t) => (t.puntos || []).forEach(([px, py]) => { xs.push(Number(px)); ys.push(-Number(py)); }));
  if (!xs.length) xs.push(0), ys.push(0);
  const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
  const lado = Math.max(maxx - minx, maxy - miny, 1);
  const margen = lado * 0.18 + 0.5;
  const w = Math.max(maxx - minx, lado * 0.75) + 2 * margen, h = Math.max(maxy - miny, lado * 0.5) + 2 * margen;
  return { x: (minx + maxx) / 2 - w / 2, y: (miny + maxy) / 2 - h / 2, w, h };
}
function escalaBonita(objetivo) {
  const p = 10 ** Math.floor(Math.log10(objetivo));
  return [1, 2, 5, 10].map((k) => k * p).filter((v) => v <= objetivo).at(-1) || p;
}
const TAMANO_LUGAR = { ciudad: 1.7, capital: 1.9, pueblo: 1.3, aldea: 1.1, castillo: 1.4, puerto: 1.3 };
export function pintarMundo() {
  const d = app.datos;
  const m = d.mundo || {};
  const todosLugares = (m.lugares || []).filter((l) => Number.isFinite(Number(l.x)) && Number.isFinite(Number(l.y)));
  const todasRegiones = (m.regiones || []).filter((r) => Array.isArray(r.puntos) && r.puntos.length >= 3);
  const todosTrazos = (m.trazos || []).filter((t) => Array.isArray(t.puntos) && t.puntos.length >= 2);
  const controles = document.querySelector("#v-mundo .mapa-controles");
  if (!todosLugares.length && !todasRegiones.length && !todosTrazos.length) {
    svgMundo.innerHTML = "";
    svgMundo.parentElement.hidden = true;
    $("#info-lugar").textContent = "";
    $("#mundo-texto").innerHTML = '<p class="texto-3">Sin mapa del mundo todavía: el narrador anota los lugares que conocen con <code>mundo lugar</code>.</p>';
    return;
  }
  svgMundo.parentElement.hidden = false;
  controles.hidden = false;
  const todosPorId = Object.fromEntries(todosLugares.map((l) => [l.id, l]));
  if (app.padreMundo && !todosPorId[app.padreMundo]) app.padreMundo = null;
  const padreActual = app.padreMundo ? todosPorId[app.padreMundo] : null;
  const enAmbito = (item) => (item.en || null) === (app.padreMundo || null);
  let lugares = todosLugares.filter(enAmbito);
  if (!lugares.length && !app.padreMundo) lugares = todosLugares;
  const regiones = todasRegiones.filter(enAmbito);
  const trazos = todosTrazos.filter(enAmbito);
  const hijosPorPadre = {};
  todosLugares.forEach((l) => { if (l.en) (hijosPorPadre[l.en] ||= []).push(l); });

  const firma = `${app.padreMundo || ""}|` + lugares.map((l) => `${l.id}:${l.x}:${l.y}`).join("|") + "|" + regiones.map((r) => r.id).join(",");
  if (!app.vistaMundo || app.firmaLugares !== firma) {
    app.vistaMundo = cajaMundo(lugares, regiones, trazos);
    app.firmaLugares = firma;
  }
  const v = app.vistaMundo, unidad = m.unidad || "km";
  const porId = Object.fromEntries(lugares.map((l) => [l.id, l]));
  const actualRaw = todosPorId[m.actual];
  const actual = actualRaw ? (porId[actualRaw.id] || (actualRaw.en && porId[actualRaw.en]) || null) : null;
  const r = v.w * 0.011, fs = v.w * 0.03;

  // Niebla de guerra cartográfica: solo lo descubierto despeja la bruma.
  const radioNiebla = Math.max(v.w, v.h) * 0.22;
  let claros = "";
  lugares.forEach((l) => {
    const mult = l.visitado || l === actual ? 1.15 : 0.72;
    claros += `<circle cx="${l.x}" cy="${-l.y}" r="${radioNiebla * mult}" fill="black"/>`;
  });
  regiones.forEach((reg) => {
    const pts = reg.puntos.map(([px, py]) => `${px},${-py}`).join(" ");
    claros += `<polygon points="${pts}" fill="black" stroke="black" stroke-width="${radioNiebla * 0.4}" stroke-linejoin="round"/>`;
  });

  let svg = `<defs>
    <mask id="mascara-niebla">
      <rect x="${v.x - v.w}" y="${v.y - v.h}" width="${v.w * 3}" height="${v.h * 3}" fill="white"/>
      ${claros}
    </mask>
  </defs>`;

  // 1. Regiones con biomas
  for (const reg of regiones) {
    const pts = reg.puntos.map(([px, py]) => `${px},${-py}`).join(" ");
    const bioma = sinTildes(reg.bioma || "bosque");
    const cx = reg.puntos.reduce((s, p) => s + Number(p[0]), 0) / reg.puntos.length;
    const cy = reg.puntos.reduce((s, p) => s - Number(p[1]), 0) / reg.puntos.length;
    svg += `<g class="region bioma-${esc(bioma)}"><polygon points="${pts}"><title>${esc(reg.nombre)} (${esc(reg.bioma || "región")})${reg.nota ? `: ${esc(reg.nota)}` : ""}</title></polygon><text class="region-nombre" x="${cx}" y="${cy}" font-size="${fs * 0.85}" text-anchor="middle">${esc(reg.nombre)}</text></g>`;
  }

  // 2. Ríos y trazos lineales
  for (const t of trazos) {
    const pts = t.puntos.map(([px, py]) => `${px},${-py}`).join(" ");
    const clase = sinTildes(t.tipo || "rio");
    svg += `<polyline class="trazo trazo-${esc(clase)}" points="${pts}" fill="none"><title>${esc(t.nombre)} (${esc(t.tipo || "trazo")})</title></polyline>`;
  }

  // 3. Rutas (con polilínea si tiene `puntos` o segmento recto)
  for (const ruta of m.rutas || []) {
    const a = porId[ruta.de], b = porId[ruta.a];
    if (!a || !b) continue;
    const tipo = sinTildes(ruta.tipo);
    const clase = /rio|canal/.test(tipo) ? "rio" : /mar|barco|bote|nave/.test(tipo) ? "mar" : /sendero|trocha|calle/.test(tipo) ? "sendero" : "camino";
    const titulo = `${esc(a.nombre)} – ${esc(b.nombre)}${ruta.tiempo ? ` · ${esc(ruta.tiempo)}` : ""}${ruta.distancia ? ` · ${esc(ruta.distancia)}` : ""}`;
    if (Array.isArray(ruta.puntos) && ruta.puntos.length >= 2) {
      const pts = ruta.puntos.map(([px, py]) => `${px},${-py}`).join(" ");
      svg += `<polyline class="ruta ${clase}" points="${pts}" fill="none"><title>${titulo}</title></polyline>`;
    } else {
      svg += `<line class="ruta ${clase}" x1="${a.x}" y1="${-a.y}" x2="${b.x}" y2="${-b.y}"><title>${titulo}</title></line>`;
    }
  }

  // 4. Niebla de guerra en tierras incógnitas
  svg += `<rect class="niebla-mundo" x="${v.x - v.w}" y="${v.y - v.h}" width="${v.w * 3}" height="${v.h * 3}" mask="url(#mascara-niebla)"/>`;

  if (actual) svg += `<circle class="aqui" cx="${actual.x}" cy="${-actual.y}" r="${r * 3}"/>`;
  // Nombres sin pisarse
  const radioDe = (l) => r * (TAMANO_LUGAR[sinTildes(l.tipo)] || 1);
  const prioridad = (l) => (l === actual ? 0 : l.id === app.lugarElegido ? 1 : 3 - (TAMANO_LUGAR[sinTildes(l.tipo)] || 1));
  const cajas = [], etiquetas = new Map();
  for (const l of [...lugares].sort((a, b) => prioridad(a) - prioridad(b))) {
    const radio = radioDe(l), largo = l.nombre.length * fs * 0.56, y = -l.y;
    const derecha = Number(l.x) + radio * 1.6 + largo <= v.x + v.w;
    const x = derecha ? Number(l.x) + radio * 1.6 : Number(l.x) - radio * 1.6;
    const caja = [derecha ? x : x - largo, y - fs * 0.8, derecha ? x + largo : x, y + fs * 0.4];
    if (cajas.some((c) => caja[0] < c[2] && c[0] < caja[2] && caja[1] < c[3] && c[1] < caja[3])) continue;
    cajas.push(caja);
    etiquetas.set(l.id, { x, ancla: derecha ? "start" : "end" });
  }
  for (const l of lugares) {
    const radio = radioDe(l), et = etiquetas.get(l.id), tieneHijos = Boolean(hijosPorPadre[l.id]?.length);
    const clases = ["lugar", l === actual ? "actual" : "", l.visitado ? "visitado" : "no-visitado", l.id === app.lugarElegido ? "elegido" : "", tieneHijos ? "con-hijos" : ""].filter(Boolean).join(" ");
    const texto = et ? `<text x="${et.x}" y="${-l.y + fs * 0.35}" font-size="${fs}" text-anchor="${et.ancla}">${esc(l.nombre)}${tieneHijos ? " ⊕" : ""}</text>` : "";
    svg += `<g class="${clases}" data-id="${esc(l.id)}"><circle cx="${l.x}" cy="${-l.y}" r="${radio}"/>${texto}<title>${esc(l.nombre)} (${esc(l.tipo || "lugar")})${l.nota ? `: ${esc(l.nota)}` : ""}</title></g>`;
  }
  const callados = lugares.length - etiquetas.size;
  const largo = escalaBonita(v.w * 0.25), bx = v.x + v.w * 0.05, by = v.y + v.h * 0.93;
  svg += `<g class="escala"><line x1="${bx}" y1="${by}" x2="${bx + largo}" y2="${by}"/><text x="${bx}" y="${by - fs * 0.5}" font-size="${fs * 0.8}">${cifra(largo)} ${esc(unidad)}</text></g>`;
  svg += `<text class="norte" x="${v.x + v.w * 0.95}" y="${v.y + v.h * 0.1}" font-size="${fs}" text-anchor="end">N ↑</text>`;
  svgMundo.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`);
  svgMundo.innerHTML = svg;
  svgMundo.setAttribute("aria-label", `Mapa del mundo${m.nombre ? `: ${m.nombre}` : ""}`);

  const rutaEntre = (a, b) => (m.rutas || []).find((x) => (x.de === a.id && x.a === b.id) || (x.de === b.id && x.a === a.id));
  const detalle = (x) => [x.tipo, x.distancia, x.tiempo].filter(Boolean).map(esc).join(", ");
  const recta = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const tiempoSrd = (km) => {
    if (km <= 0) return "0 min";
    if (km < 4.8) return `${Math.max(1, Math.round((km / 4.8) * 60))} min a pie`;
    if (km < 38) return `${cifra(km / 4.8)} h a pie`;
    const dias = Math.floor(km / 38), h = Math.round((km - dias * 38) / 4.8);
    return `${dias} ${dias === 1 ? "día" : "días"}${h > 0 ? ` y ${h} h` : ""} a pie`;
  };
  const elegido = porId[app.lugarElegido];
  let migas = "";
  if (padreActual) {
    migas = `<div class="mundo-migas"><button type="button" class="enlace" data-entrar="">← ${esc(m.nombre || "Mapa general")}</button> <span>›</span> <b>${esc(padreActual.nombre)}</b></div>`;
  }
  if (elegido) {
    const distRecta = actual && actual !== elegido ? recta(actual, elegido) : 0;
    const ruta = actual && actual !== elegido ? rutaEntre(actual, elegido) : null;
    const desde = actual && actual !== elegido
      ? ` · a ${cifra(distRecta)} ${esc(unidad)} en línea recta de ${esc(actual.nombre)} (${ruta ? `ruta: ${detalle(ruta) || "conocida"}` : `~${tiempoSrd(distRecta)} a ritmo normal`})`
      : elegido === actual ? " · están aquí" : "";
    const hijos = hijosPorPadre[elegido.id] || [];
    const btnEntrar = hijos.length ? ` <button type="button" class="boton-entrar" data-entrar="${esc(elegido.id)}">Entrar a ${esc(elegido.nombre)} (${hijos.length})</button>` : "";
    $("#info-lugar").innerHTML = `${migas}<b>${esc(elegido.nombre)}</b> <span class="texto-3">${esc(elegido.tipo || "lugar")}${elegido.visitado ? " · visitado" : " · oído/avistado"}</span>${desde}${btnEntrar}${elegido.nota ? `<br>${esc(elegido.nota)}` : ""}`;
  } else {
    const dondeTxt = actualRaw ? `Están en <b>${esc(actualRaw.nombre)}</b>.` : "Toca un lugar para ver sus datos.";
    $("#info-lugar").innerHTML = `${migas}${dondeTxt} Toca un lugar para medir viaje; arrastra para moverte y usa + y − para el zoom.`;
  }
  if (callados) $("#info-lugar").innerHTML += ` <span class="texto-3">(${callados} ${callados === 1 ? "nombre oculto" : "nombres ocultos"} por estar muy juntos: acerca el zoom)</span>`;
  const orden = actual ? [...lugares].sort((a, b) => recta(actual, a) - recta(actual, b)) : lugares;
  $("#mundo-texto").innerHTML = `
    <h3 class="subtitulo-panel">${esc(padreActual ? `Lugares en ${padreActual.nombre}` : m.nombre || "Lugares conocidos")}</h3>
    <ul class="lugares">${orden.map((l) => {
      const hijos = hijosPorPadre[l.id] || [];
      const btn = hijos.length ? ` <button type="button" class="enlace" data-entrar="${esc(l.id)}">abrir mapa (${hijos.length})</button>` : "";
      return `<li data-id="${esc(l.id)}"><b>${esc(l.nombre)}</b> <span class="texto-3">${esc(l.tipo || "lugar")}${l === actual ? " · aquí" : actual ? ` · ${cifra(recta(actual, l))} ${esc(unidad)}` : ""}${l.visitado && l !== actual ? " · visitado" : ""}</span>${btn}${l.nota ? `<br><span class="texto-2">${esc(l.nota)}</span>` : ""}</li>`;
    }).join("")}</ul>
    ${regiones.length ? `<h3 class="subtitulo-panel">Regiones y biomas</h3><ul class="lista">${regiones.map((reg) => `<li><b>${esc(reg.nombre)}</b> <span class="texto-3">(${esc(reg.bioma)})</span>${reg.nota ? ` — ${esc(reg.nota)}` : ""}</li>`).join("")}</ul>` : ""}
    ${(m.rutas || []).filter((x) => porId[x.de] && porId[x.a]).length ? `<h3 class="subtitulo-panel">Rutas</h3><ul class="lista">${m.rutas.filter((x) => porId[x.de] && porId[x.a]).map((x) => `<li>${esc(porId[x.de].nombre)} – ${esc(porId[x.a].nombre)}${detalle(x) ? ` <span class="texto-3">(${detalle(x)})</span>` : ""}</li>`).join("")}</ul>` : ""}`;
}
$("#v-mundo").addEventListener("click", (ev) => {
  const entrar = ev.target.closest("[data-entrar]");
  if (entrar) {
    app.padreMundo = entrar.dataset.entrar || null;
    app.lugarElegido = null;
    app.vistaMundo = null;
    pintarMundo();
  }
});
function zoomMundo(factor, cx, cy) {
  const v = app.vistaMundo;
  if (!v) return;
  cx ??= v.x + v.w / 2; cy ??= v.y + v.h / 2;
  app.vistaMundo = { x: cx - (cx - v.x) * factor, y: cy - (cy - v.y) * factor, w: v.w * factor, h: v.h * factor };
  pintarMundo();
}
document.querySelector("#v-mundo .mapa-controles").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-zoom]");
  if (!b) return;
  if (b.dataset.zoom === "centrar") { app.vistaMundo = null; return pintarMundo(); }
  zoomMundo(b.dataset.zoom === "mas" ? 0.7 : 1 / 0.7);
});
function puntoSvg(ev) {
  const p = svgMundo.createSVGPoint();
  p.x = ev.clientX; p.y = ev.clientY;
  return p.matrixTransform(svgMundo.getScreenCTM().inverse());
}
svgMundo.addEventListener("wheel", (ev) => {
  if (!app.vistaMundo) return;
  ev.preventDefault();
  const p = puntoSvg(ev);
  zoomMundo(ev.deltaY < 0 ? 0.85 : 1 / 0.85, p.x, p.y);
}, { passive: false });
let arrastre = null;
svgMundo.addEventListener("pointerdown", (ev) => {
  if (!app.vistaMundo) return;
  arrastre = { x: ev.clientX, y: ev.clientY, vista: { ...app.vistaMundo }, movido: false };
  svgMundo.setPointerCapture(ev.pointerId);
});
svgMundo.addEventListener("pointermove", (ev) => {
  if (!arrastre) return;
  const dx = ev.clientX - arrastre.x, dy = ev.clientY - arrastre.y;
  if (!arrastre.movido && Math.hypot(dx, dy) < 4) return;
  arrastre.movido = true;
  const caja = svgMundo.getBoundingClientRect(), v = arrastre.vista;
  const escala = Math.max(v.w / caja.width, v.h / caja.height);
  app.vistaMundo = { ...v, x: v.x - dx * escala, y: v.y - dy * escala };
  pintarMundo();
});
svgMundo.addEventListener("pointerup", (ev) => {
  const fue = arrastre;
  arrastre = null;
  if (fue?.movido) return;
  const lugar = document.elementFromPoint(ev.clientX, ev.clientY)?.closest("g.lugar");
  app.lugarElegido = lugar ? (lugar.dataset.id === app.lugarElegido ? null : lugar.dataset.id) : null;
  pintarMundo();
});
$("#mundo-texto").addEventListener("click", (ev) => {
  const li = ev.target.closest("li[data-id]");
  if (!li) return;
  app.lugarElegido = li.dataset.id;
  pintarMundo();
});

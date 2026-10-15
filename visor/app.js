// Visor de la mesa: sondea el servidor local y pinta escena, dados, fichas y mundo.
const app = { slug: null, firmaEstado: "", ultimoSeq: 0, datos: null, eventos: [], pestana: "pnj" };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const signo = (n) => (n >= 0 ? `+${n}` : `${n}`);
const ATRIBUTOS = { fuerza: "Fuerza", agilidad: "Agilidad", ingenio: "Ingenio", corazon: "Corazón" };
const ES_TIRADA = new Set(["prueba", "ataque", "tirada", "dano", "suerte"]);
const MOVIMIENTO_REDUCIDO = matchMedia("(prefers-reduced-motion: reduce)").matches;

async function api(ruta) {
  const r = await fetch(ruta, { cache: "no-store" });
  if (!r.ok) throw new Error(`${ruta}: ${r.status}`);
  return r.json();
}

// ---------- tema ----------
function leerTema() { try { return localStorage.getItem("mesa-tema") || "auto"; } catch { return "auto"; } }
function aplicarTema(t) {
  if (t === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  $("#boton-tema").textContent = `Tema: ${t === "auto" ? "auto" : t === "dark" ? "oscuro" : "claro"}`;
  try { localStorage.setItem("mesa-tema", t); } catch { /* sin almacenamiento: no pasa nada */ }
}
$("#boton-tema").addEventListener("click", () => {
  const orden = ["auto", "light", "dark"];
  aplicarTema(orden[(orden.indexOf(leerTema()) + 1) % orden.length]);
});

// ---------- dados ----------
const FORMAS = {
  2: "50,6 94,50 50,94 6,50",
  3: "50,8 92,86 8,86",
  4: "50,8 93,88 7,88",
  6: "12,12 88,12 88,88 12,88",
  8: "50,4 95,50 50,96 5,50",
  10: "50,4 93,42 50,96 7,42",
  12: "50,4 95,37 78,93 22,93 5,37",
  20: "50,3 93,27 93,73 50,97 7,73 7,27",
  100: "50,3 79,12 96,38 96,62 79,88 50,97 21,88 4,62 4,38 21,12",
};
function svgDado(caras, valor) {
  const arista = caras === 20 ? '<polygon class="arista" points="50,24 75,66 25,66"/>' : caras === 8 ? '<line class="arista" x1="5" y1="50" x2="95" y2="50"/>' : "";
  const y = caras === 4 || caras === 3 ? 62 : 52;
  return `<svg viewBox="0 0 100 100" role="img" aria-label="d${caras}: ${esc(valor)}"><polygon class="cara" points="${FORMAS[caras] || FORMAS[20]}"/>${arista}<text class="valor" x="50" y="${y}">${esc(valor)}</text></svg>`;
}
function caras(dado) { return Number(String(dado).replace("d", "")) || 20; }

function dadosDeEvento(e) {
  if (e.tipo === "prueba" || e.tipo === "ataque") {
    const n = e.caras || 20;
    const elegidoIdx = e.valores.indexOf(e.elegido);
    const lista = e.valores.map((v, i) => ({
      caras: n, valor: v,
      descartado: e.modo !== "normal" && i !== elegidoIdx,
      critico: i === elegidoIdx && e.resultado === "critico",
      uno: i === elegidoIdx && e.resultado === "uno_natural",
    }));
    if (e.dano) {
      lista.push({ separador: "daño" });
      e.dano.tirada.dados.forEach((t) => t.valores.forEach((v) => lista.push({ caras: caras(t.dado), valor: v, pequeno: true })));
    }
    return lista;
  }
  if (e.tipo === "suerte") return [{ caras: 100, valor: e.valor }];
  return (e.dados || []).flatMap((t) => t.valores.map((v) => ({ caras: caras(t.dado), valor: v, pequeno: (e.dados.length > 1 || t.valores.length > 2) })));
}

function nombreAccion(e) {
  if (e.tipo === "ataque") return e.arma === "Ataque" ? `ataca a ${e.objetivo}` : `ataque con ${e.arma} a ${e.objetivo}`;
  if (e.tipo === "prueba") return [ATRIBUTOS[e.atributo], e.habilidad && `(${e.habilidad})`].filter(Boolean).join(" ");
  if (e.tipo === "dano") return `daño${e.objetivo ? ` a ${e.objetivo}` : ""}`;
  if (e.tipo === "suerte") return "suerte";
  return e.expr;
}

function cuentaDe(e) {
  if (e.tipo === "prueba" || e.tipo === "ataque") {
    const mods = e.partes.map((p) => `${signo(p.valor)} ${p.fuente}`).join(" ");
    const contra = e.cd == null ? "" : ` contra ${e.tipo === "ataque" ? "Defensa" : "dificultad"} ${e.cd}`;
    let txt = `${e.elegido} ${mods} = <b>${e.total}</b>${contra}`;
    if (e.dano) {
      const d = e.dano;
      txt += `<br>Daño ${esc(d.tirada.expr)}${d.tirada.critico ? " (crítico: dados dobles)" : ""}: ${d.bruto} − protección ${d.proteccion} = <b>${d.final}</b> → ${esc(d.objetivo)} ${d.vida.despues}/${d.vida.maximo}`;
    }
    return txt;
  }
  if (e.tipo === "suerte") return `d100 = <b>${e.valor}</b> contra ${e.probabilidad}%`;
  const suma = (e.dados || []).flatMap((t) => t.valores).join(" + ");
  let txt = `${esc(e.expr)}${e.critico ? " (crítico)" : ""}: ${suma}${e.modificador ? ` ${signo(e.modificador)}` : ""} = <b>${e.total}</b>`;
  if (e.tipo === "dano" && e.objetivo) txt += ` − protección ${e.proteccion} = <b>${e.final}</b> → ${esc(e.objetivo)} ${e.vida.despues}/${e.vida.maximo}`;
  return txt;
}

function modoDe(e) {
  if (e.modo === "ventaja") return `Ventaja: ${esc(e.ventajas.join(", "))}`;
  if (e.modo === "desventaja") return `Desventaja: ${esc(e.desventajas.join(", "))}`;
  if (e.ventajas?.length && e.desventajas?.length) return `Ventaja y desventaja se anulan (${esc([...e.ventajas, ...e.desventajas].join(", "))})`;
  return "";
}

function resultadoDe(e) {
  if (e.tipo === "suerte") return e.exito ? ["si", "✓ Sí"] : ["no", "✕ No"];
  if (!("resultado" in e)) return null;
  return {
    critico: ["critico", "★ ¡CRÍTICO! (20 natural)"],
    uno_natural: ["uno_natural", "✕ 1 natural: fallo"],
    exito: ["exito", "✓ Éxito"],
    fallo: ["fallo", "✕ Fallo"],
    sin_cd: null,
  }[e.resultado];
}

function pintarBandeja(e, animar) {
  const dados = dadosDeEvento(e);
  const res = resultadoDe(e);
  const filas = dados.map((d) => d.separador
    ? `<span class="separador-dano">${d.separador}</span>`
    : `<div class="dado${d.pequeno ? " pequeno" : ""}${d.descartado ? " descartado" : ""}${d.critico ? " critico" : ""}${d.uno ? " uno" : ""}" data-caras="${d.caras}" data-valor="${d.valor}">${svgDado(d.caras, animar ? "?" : d.valor)}<span class="dado-tipo">d${d.caras}</span></div>`).join("");
  const modo = modoDe(e);
  $("#bandeja").innerHTML = `
    <div class="tirada-cabeza">${esc(e.quien || "")} · ${esc(nombreAccion(e))}${e.etiqueta ? ` <span class="texto-3">· ${esc(e.etiqueta)}</span>` : ""}</div>
    <div class="dados-fila">${filas}</div>
    ${modo ? `<div class="tirada-modo">${modo}</div>` : ""}
    <div class="tirada-cuenta">${cuentaDe(e)}</div>
    ${res ? `<div class="resultado${animar ? " esperando" : ""}" data-r="${res[0]}">${res[1]}</div>` : ""}`;
  if (!animar) return;
  const nodos = [...document.querySelectorAll("#bandeja .dado")];
  const final = () => {
    nodos.forEach((n) => { n.classList.remove("rodando"); n.querySelector(".valor").textContent = n.dataset.valor; });
    $("#bandeja .resultado")?.classList.remove("esperando");
  };
  if (MOVIMIENTO_REDUCIDO) return final();
  nodos.forEach((n) => n.classList.add("rodando"));
  const inicio = performance.now();
  const paso = () => {
    if (performance.now() - inicio > 900) return final();
    nodos.forEach((n) => { n.querySelector(".valor").textContent = 1 + Math.floor(Math.random() * Number(n.dataset.caras)); });
    setTimeout(paso, 70);
  };
  paso();
}

function pintarHistorial() {
  const tiradas = app.eventos.filter((e) => ES_TIRADA.has(e.tipo)).slice(-40).reverse();
  $("#historial").innerHTML = tiradas.map((e) => {
    const res = resultadoDe(e);
    const dado = e.tipo === "suerte" ? "d100" : e.tipo === "prueba" || e.tipo === "ataque" ? `${e.modo === "normal" ? "1" : "2"}d${e.caras || 20}` : esc(e.expr);
    const total = e.tipo === "suerte" ? e.valor : (e.final ?? e.total);
    return `<li><button type="button" data-seq="${e.seq}"><span class="mini-dado">${dado}</span><span><b>${esc(e.quien || "")}</b> ${esc(nombreAccion(e))} — ${total}${e.cd != null ? ` vs ${e.cd}` : ""}</span>${res ? `<span class="chip r-${res[0]}">${res[1].replace(/^\S+ /, "")}</span>` : ""}</button></li>`;
  }).join("") || '<li class="texto-3">Sin tiradas todavía.</li>';
}
$("#historial").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-seq]");
  if (!b) return;
  const e = app.eventos.find((x) => x.seq === Number(b.dataset.seq));
  if (e) pintarBandeja(e, false);
});

// ---------- estado ----------
function estadoVida(p) {
  const r = p.vida_max ? p.vida / p.vida_max : 0;
  if (p.vida <= 0) return ["fuera", "✕ Fuera de combate"];
  if (r >= 1) return ["ileso", "✓ Ileso"];
  if (r > 0.5) return ["leve", "◐ Herida leve"];
  if (r > 0.25) return ["herido", "▲ Herido"];
  return ["grave", "▲ Grave"];
}

function pintarFicha(p) {
  const [est, etiquetaVida] = estadoVida(p);
  const afectados = new Set((p.condiciones || []).flatMap((c) => (c.desventaja || [])));
  const atributos = Object.entries(p.atributos || {}).map(([k, v]) => `
    <li><span class="attr-nombre">${ATRIBUTOS[k] || k}</span><span class="attr-valor">${signo(v)}</span>${afectados.has(k) || afectados.has("todo") ? '<span class="attr-marca">desventaja</span>' : ""}</li>`).join("");
  const habilidades = (p.habilidades || []).map((h) => `<span class="etiqueta${h.disponible === false ? " gastada" : ""}" title="${esc(h.texto)}">${esc(h.nombre)} · ${h.disponible === false ? "gastada" : "disponible"}</span>`).join("");
  const condiciones = (p.condiciones || []).map((c) => `<span class="etiqueta condicion" title="${esc(c.efecto)}">${esc(c.nombre)}${c.niveles > 1 ? ` ${c.niveles}` : ""}: ${esc(c.efecto || "")}</span>`).join("");
  const equipo = (p.equipo || []).map((x) => `<li>${esc(x.nombre)}${x.dano ? ` — <b>${esc(x.dano)}</b>${x.distancia ? " a distancia" : ""}` : ""}${x.texto ? ` <span class="texto-3">(${esc(x.texto)})</span>` : ""}</li>`).join("");
  const rasgos = (p.rasgos || []).map((r) => `<li><b>${esc(r.nombre)}:</b> ${esc(r.texto)}</li>`).join("");
  const pct = p.vida_max ? Math.max(0, Math.min(100, (100 * p.vida) / p.vida_max)) : 0;
  return `
  <article class="ficha" style="--color:${esc(p.color || "var(--acento)")}">
    <header><h3>${esc(p.nombre)}</h3><span class="rol">${esc(p.rol || "")} · nivel ${p.nivel ?? 1}</span></header>
    <div class="vida">
      <div class="vida-pista" role="meter" aria-label="Vida de ${esc(p.nombre)}" aria-valuemin="0" aria-valuemax="${p.vida_max}" aria-valuenow="${p.vida}"><div class="vida-relleno" data-estado="${est}" style="width:${pct}%"></div></div>
      <span class="vida-num">${p.vida}/${p.vida_max}</span>
      <span class="vida-estado">${etiquetaVida}</span>
    </div>
    <dl class="defensas"><div><dt>Defensa</dt><dd>${p.defensa ?? "-"}</dd></div><div><dt>Protección</dt><dd>${p.proteccion ?? 0}</dd></div></dl>
    <ul class="atributos">${atributos}</ul>
    ${condiciones ? `<div class="etiquetas">${condiciones}</div>` : ""}
    ${habilidades ? `<div class="etiquetas">${habilidades}</div>` : ""}
    ${p.oficio?.aplica ? `<p class="oficio">Oficio ${signo(p.oficio.bono)}: ${esc(p.oficio.aplica)}</p>` : ""}
    <details><summary>Equipo y rasgos</summary><ul>${equipo}${rasgos}</ul>${p.aspecto ? `<p class="texto-2">${esc(p.aspecto)}</p>` : ""}</details>
  </article>`;
}

function pintarEnemigos(lista) {
  if (!lista?.length) return "";
  const filas = lista.map((e) => `<tr><td>${esc(e.nombre)}</td><td>${e.vida}/${e.vida_max}</td><td>${e.defensa}</td><td>${signo(e.ataque || 0)}</td><td>${esc(e.dano || (e.armas || []).map((a) => `${a.nombre} ${a.dano}`).join(" / "))}</td><td>${e.proteccion || 0}</td></tr>`).join("");
  return `<div class="enemigos"><h3>Amenazas en escena</h3><table><thead><tr><th>Quién</th><th>Vida</th><th>Defensa</th><th>Ataque</th><th>Daño</th><th>Prot.</th></tr></thead><tbody>${filas}</tbody></table></div>`;
}

const PESTANAS = [
  ["pnj", "PNJ"], ["pistas", "Pistas"], ["tramas", "Tramas"], ["misterios", "Preguntas"],
  ["recursos", "Recursos"], ["reglas", "Reglas de la casa"], ["bitacora", "Bitácora"],
];
function pintarPestanas() {
  $("#pestanas").innerHTML = PESTANAS.map(([id, nombre]) => `<button type="button" role="tab" data-p="${id}" aria-selected="${id === app.pestana}">${nombre}</button>`).join("");
}
$("#pestanas").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-p]");
  if (!b) return;
  app.pestana = b.dataset.p;
  pintarPestanas();
  pintarMundo();
});

function pintarMundo() {
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
    case "tramas":
      html = (d.tramas || []).length ? `<ul class="lista">${d.tramas.map((t) => `<li><b>${esc(t.nombre)}</b><span class="estado-trama">${esc(t.estado)}</span>${t.nota ? `<br><span class="texto-2">${esc(t.nota)}</span>` : ""}</li>`).join("")}</ul>` : vacio;
      break;
    case "misterios":
      html = (d.misterios || []).length ? `<ul class="lista">${d.misterios.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : vacio;
      break;
    case "recursos":
      html = Object.keys(d.recursos || {}).length ? `<table class="recursos"><tbody>${Object.entries(d.recursos).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("")}</tbody></table>` : vacio;
      break;
    case "reglas":
      html = (d.reglas_casa || []).length ? `<ul class="lista">${d.reglas_casa.map((r) => `<li><b>${esc(r.id)}</b> ${esc(r.texto)} <span class="fuente">(${esc(r.desde || "")})</span></li>`).join("")}</ul>` : vacio;
      break;
    case "bitacora": {
      const items = app.eventos.filter((e) => ["turno", "nota", "escena", "regla", "pista"].includes(e.tipo)).slice(-60).reverse();
      html = items.length ? `<ol class="bitacora">${items.map((e) => {
        const cuando = `<div class="cuando">#${e.seq} · ${esc((e.ts || "").replace("T", " ").slice(0, 16))} · ${esc(e.tipo)}</div>`;
        if (e.tipo === "turno") return `<li>${cuando}${Object.entries(e.acciones || {}).map(([k, v]) => `<p class="accion"><b>${esc(k)}:</b> ${esc(v)}</p>`).join("")}<p class="resumen">${esc(e.resumen)}</p></li>`;
        if (e.tipo === "escena") return `<li>${cuando}<p class="resumen">Escena ${e.numero}: ${esc(e.titulo)} — ${esc(e.lugar || "")}</p></li>`;
        return `<li>${cuando}<p>${esc(e.texto || "")}</p></li>`;
      }).join("")}</ol>` : vacio;
      break;
    }
  }
  $("#mundo").innerHTML = html;
}

function pintarEstado() {
  const d = app.datos;
  document.title = `${d.titulo} · Mesa de rol`;
  if (d.tema?.acento) document.documentElement.style.setProperty("--acento", d.tema.acento);
  $("#titulo-partida").textContent = d.titulo;
  $("#subtitulo").textContent = [d.ambientacion?.epoca, d.ambientacion?.lugar].filter(Boolean).join(" · ");
  const esc_ = d.escena || {};
  $("#reloj").innerHTML = `<span>Día ${esc(d.reloj?.dia ?? "?")} · ${esc(esc_.hora || "")}</span>${(d.reloj?.plazos || []).map((p) => `<span class="plazo">${esc(p)}</span>`).join("")}`;
  $("#escena-numero").textContent = `Escena ${esc_.numero ?? ""}`;
  $("#titulo-escena").textContent = esc_.titulo || "";
  $("#escena-meta").textContent = [esc_.lugar, esc_.clima].filter(Boolean).join(" · ");
  $("#escena-descripcion").textContent = esc_.descripcion || "";
  $("#posiciones").innerHTML = (esc_.posiciones || []).map((p) => `<li><b>${esc(p.quien)}</b><span>${esc(p.donde)}</span></li>`).join("");
  const img = $("#escena-imagen");
  if (esc_.imagen) {
    const src = `/media/${encodeURIComponent(app.slug)}/${encodeURIComponent(esc_.imagen)}`;
    if (img.dataset.src !== src) {
      img.dataset.src = src;
      img.innerHTML = `<img src="${src}" alt="${esc(esc_.titulo || "Escena")}">`;
    }
    const f = esc_.imagen_fuente || {};
    $("#escena-pie").textContent = f.modo ? `Imagen: ${f.modo === "generar" ? "generada" : f.modo === "elegir" ? "elegida" : "tarjeta local"} · ${f.origen || ""}` : "";
  } else {
    img.dataset.src = "";
    img.innerHTML = `<div class="sin-imagen">${esc(esc_.titulo || "")}</div>`;
    $("#escena-pie").textContent = "";
  }
  $("#fichas").innerHTML = (d.personajes || []).map(pintarFicha).join("");
  $("#enemigos").innerHTML = pintarEnemigos(d.enemigos);
  pintarMundo();
}

async function cargarEstado() {
  const datos = await api(`/api/estado?p=${encodeURIComponent(app.slug)}`);
  const firma = JSON.stringify(datos);
  if (firma === app.firmaEstado) return;
  app.firmaEstado = firma;
  app.datos = datos;
  pintarEstado();
}

function conexion(ok) {
  const n = $("#conexion");
  n.dataset.estado = ok ? "vivo" : "caido";
  n.textContent = ok ? "en vivo" : "sin conexión";
}

async function sondear() {
  try {
    const { eventos } = await api(`/api/eventos?p=${encodeURIComponent(app.slug)}&desde=${app.ultimoSeq}`);
    if (eventos.length) {
      app.eventos.push(...eventos);
      app.ultimoSeq = eventos.at(-1).seq;
      pintarHistorial();
      const tirada = eventos.filter((e) => ES_TIRADA.has(e.tipo)).at(-1);
      if (tirada) pintarBandeja(tirada, true);
    }
    await cargarEstado();
    conexion(true);
  } catch {
    conexion(false);
  }
}

async function iniciar() {
  aplicarTema(leerTema());
  pintarPestanas();
  try {
    const { activa, partidas } = await api("/api/partidas");
    const pedida = new URLSearchParams(location.search).get("p");
    app.slug = pedida || activa || partidas[0]?.slug;
    $("#selector-partida").innerHTML = partidas.map((p) => `<option value="${esc(p.slug)}"${p.slug === app.slug ? " selected" : ""}>${esc(p.titulo)}</option>`).join("");
    $("#selector-partida").addEventListener("change", (ev) => { location.search = `?p=${encodeURIComponent(ev.target.value)}`; });
    if (!app.slug) { $("#titulo-partida").textContent = "No hay partidas"; return; }
    await cargarEstado();
    const { eventos } = await api(`/api/eventos?p=${encodeURIComponent(app.slug)}&desde=0`);
    app.eventos = eventos;
    app.ultimoSeq = eventos.at(-1)?.seq ?? 0;
    pintarHistorial();
    pintarMundo();
    const ultima = eventos.filter((e) => ES_TIRADA.has(e.tipo)).at(-1);
    if (ultima) pintarBandeja(ultima, false);
    conexion(true);
  } catch (err) {
    conexion(false);
    console.error(err);
  }
  setInterval(sondear, 1000);
}

iniciar();

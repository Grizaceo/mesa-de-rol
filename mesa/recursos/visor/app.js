// Visor de la mesa: el chat con el narrador al centro (con las tiradas y los cambios como tarjetas),
// la ficha, la memoria y el registro a la izquierda, y la zona, el mundo y la ambientación a la derecha.
// Sondea el servidor local; sin narrador en el visor, el centro muestra la bitácora como conversación.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const signo = (n) => (n >= 0 ? `+${n}` : `${n}`);
const leerLocal = (clave, defecto) => { try { return localStorage.getItem(clave) || defecto; } catch { return defecto; } };
const guardarLocal = (clave, valor) => { try { localStorage.setItem(clave, valor); } catch { /* sin almacenamiento: no pasa nada */ } };
const sinTildes = (s) => String(s ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
const cifra = (n) => String(Math.round(Number(n) * 10) / 10).replace(".", ",");
const metros = (n) => `${cifra(n)} m`;
const colorSeguro = (c, defecto) => (/^#[0-9a-f]{3,8}$/i.test(String(c || "")) ? c : defecto);

const app = {
  slug: null, firmaEstado: "", ultimoSeq: 0, datos: null, eventos: [], sondeando: false,
  izq: leerLocal("mesa-izq", "ficha"), der: leerLocal("mesa-der", "zona"), pestana: leerLocal("mesa-registro", "pnj"), documentoNuevo: null,
  escritura: false, token: null, editando: null, novedades: new Set(),
  origenZona: null, destinoZona: null, vistaMundo: null, firmaLugares: "", lugarElegido: null,
  chat: [], chatSeq: 0, narrador: { activo: false }, chatActivo: false, autor: null,
  firmaHistorial: "", firmaVivo: "", animados: new Set(), seqInicial: 0,
  // La zona se pinta desde `/api/zona`: firmaZona es lo que se ha pedido y
  // firmaZonaMapa lo que el estado dice que hay detrás, para no redibujar el SVG
  // cuando llega un evento que no toca el mapa.
  proyeccion: null, firmaZona: "", firmaZonaMapa: "", zonaToken: 0, zonaPendiente: false,
};

const ATRIBUTOS = {
  fuerza: "Fuerza", agilidad: "Agilidad", ingenio: "Ingenio", corazon: "Corazón",
  destreza: "Destreza", constitucion: "Constitución", inteligencia: "Inteligencia", sabiduria: "Sabiduría", carisma: "Carisma",
};
const ABREVIATURA_2024 = { fuerza: "FUE", destreza: "DES", constitucion: "CON", inteligencia: "INT", sabiduria: "SAB", carisma: "CAR" };
const ES_TIRADA = new Set(["prueba", "ataque", "tirada", "dano", "suerte"]);
const CLASE_DOCUMENTO = { carta: "Carta", telegrama: "Telegrama", periodico: "Periódico", nota: "Nota", cartel: "Cartel", informe: "Informe", otro: "Documento" };
const CATEGORIAS = ["personaje", "pnj", "lugar", "objeto", "promesa", "mundo", "trama", "otro"];
const MOVIMIENTO_REDUCIDO = matchMedia("(prefers-reduced-motion: reduce)").matches;
const VISTAS_IZQ = [["ficha", "Ficha"], ["hechos", "Hechos"], ["registro", "Registro"]];
const VISTAS_DER = [["zona", "Zona"], ["mundo", "Mundo"], ["ambiente", "Ambientación"]];
// Qué pestaña tiene algo nuevo cuando llega un evento (si no es la que se está mirando).
const VISTA_DE_EVENTO = {
  mapa: "zona", posicion: "zona", escena: "zona", mundo: "mundo", hecho: "hechos", memoria: "hechos",
  documento: "registro", pista: "registro", pnj: "registro", trama: "registro", misterio: "registro",
  vida: "ficha", condicion: "ficha", habilidad: "ficha", nivel: "ficha", enemigo: "ficha", vendaje: "ficha", descanso: "ficha",
};
if (!VISTAS_IZQ.some(([id]) => id === app.izq)) app.izq = "ficha";
if (!VISTAS_DER.some(([id]) => id === app.der)) app.der = "zona";

async function api(ruta) {
  const r = await fetch(ruta, { cache: "no-store" });
  if (!r.ok) throw new Error(`${ruta}: ${r.status}`);
  return r.json();
}

// ---------- tema ----------
function leerTema() { return leerLocal("mesa-tema", "auto"); }
function aplicarTema(t) {
  if (t === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  $("#boton-tema").textContent = `Tema: ${t === "auto" ? "auto" : t === "dark" ? "oscuro" : "claro"}`;
  guardarLocal("mesa-tema", t);
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
    const mods = e.partes.map((p) => `${signo(p.valor)} ${esc(p.fuente)}`).join(" ");
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

// Una tirada como tarjeta del chat; `animar` la deja con «?» para que ruede al aparecer.
function tarjetaDados(e, animar) {
  const res = resultadoDe(e);
  const filas = dadosDeEvento(e).map((d) => d.separador
    ? `<span class="separador-dano">${d.separador}</span>`
    : `<div class="dado${d.pequeno ? " pequeno" : ""}${d.descartado ? " descartado" : ""}${d.critico ? " critico" : ""}${d.uno ? " uno" : ""}" data-caras="${d.caras}" data-valor="${d.valor}">${svgDado(d.caras, animar ? "?" : d.valor)}<span class="dado-tipo">d${d.caras}</span></div>`).join("");
  const modo = modoDe(e);
  return `<div class="tarjeta-evento t-dados"${animar ? ` data-animar="${e.seq}"` : ""}>
    <div class="tirada-cabeza">${esc(e.quien || "")}${e.quien ? " · " : ""}${esc(nombreAccion(e))}${e.etiqueta ? ` <span class="texto-3">· ${esc(e.etiqueta)}</span>` : ""}</div>
    <div class="dados-fila">${filas}</div>
    ${modo ? `<div class="tirada-modo">${modo}</div>` : ""}
    <div class="tirada-cuenta">${cuentaDe(e)}</div>
    ${res ? `<div class="resultado${animar ? " esperando" : ""}" data-r="${res[0]}">${res[1]}</div>` : ""}
  </div>`;
}

function animarDados(raiz) {
  raiz.querySelectorAll("[data-animar]").forEach((tarjeta) => {
    app.animados.add(Number(tarjeta.dataset.animar));
    tarjeta.removeAttribute("data-animar");
    const nodos = [...tarjeta.querySelectorAll(".dado")];
    const final = () => {
      nodos.forEach((n) => { n.classList.remove("rodando"); n.querySelector(".valor").textContent = n.dataset.valor; });
      tarjeta.querySelector(".resultado")?.classList.remove("esperando");
    };
    if (MOVIMIENTO_REDUCIDO) return final();
    nodos.forEach((n) => n.classList.add("rodando"));
    const inicio = performance.now();
    const paso = () => {
      if (!tarjeta.isConnected || performance.now() - inicio > 900) return final();
      nodos.forEach((n) => { n.querySelector(".valor").textContent = 1 + Math.floor(Math.random() * Number(n.dataset.caras)); });
      setTimeout(paso, 70);
    };
    paso();
  });
}

function listaTiradas() {
  const tiradas = app.eventos.filter((e) => ES_TIRADA.has(e.tipo)).slice(-60).reverse();
  return tiradas.length ? `<ol class="historial">${tiradas.map((e) => {
    const res = resultadoDe(e);
    const dado = e.tipo === "suerte" ? "d100" : e.tipo === "prueba" || e.tipo === "ataque" ? `${e.modo === "normal" ? "1" : "2"}d${e.caras || 20}` : esc(e.expr);
    const total = e.tipo === "suerte" ? e.valor : (e.final ?? e.total);
    return `<li><span class="mini-dado">${dado}</span><span><b>${esc(e.quien || "")}</b> ${esc(nombreAccion(e))} — ${esc(total)}${e.cd != null ? ` vs ${esc(e.cd)}` : ""}${e.etiqueta ? ` <span class="texto-3">· ${esc(e.etiqueta)}</span>` : ""}</span>${res ? `<span class="chip r-${res[0]}">${res[1].replace(/^\S+ /, "")}</span>` : ""}</li>`;
  }).join("")}</ol>` : '<p class="texto-3">Sin tiradas todavía.</p>';
}

// ---------- pestañas de los dos lados ----------
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

// En pantallas estrechas los lados son cajones que se abren con los botones de la barra.
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

// ---------- ficha ----------
function estadoVida(p) {
  const r = p.vida_max ? p.vida / p.vida_max : 0;
  if (p.vida <= 0) return ["fuera", "✕ Fuera de combate"];
  if (r >= 1) return ["ileso", "✓ Ileso"];
  if (r > 0.5) return ["leve", "◐ Herida leve"];
  if (r > 0.25) return ["herido", "▲ Herido"];
  return ["grave", "▲ Grave"];
}
const es2024 = (d) => Number(d?.schema_version) === 2 || d?.reglamento === "dnd-2024";

function pintarFicha(p, d) {
  const [est, etiquetaVida] = estadoVida(p);
  const afectados = new Set((p.condiciones || []).flatMap((c) => (c.desventaja || [])));
  const moderno = es2024(d);
  const atributos = Object.entries(p.atributos || {}).map(([k, v]) => {
    const marca = afectados.has(k) || afectados.has("todo") ? '<span class="attr-marca">desventaja</span>' : "";
    if (moderno) return `<li title="${esc(ATRIBUTOS[k] || k)}"><span class="attr-nombre">${ABREVIATURA_2024[k] || esc(k)}</span><span class="attr-valor">${signo(Math.floor((v - 10) / 2))}</span><span class="attr-punt">${esc(v)}</span>${marca}</li>`;
    return `<li><span class="attr-nombre">${esc(ATRIBUTOS[k] || k)}</span><span class="attr-valor">${signo(v)}</span>${marca}</li>`;
  }).join("");
  const habilidades = (p.habilidades || []).map((h) => `<span class="etiqueta${h.disponible === false ? " gastada" : ""}" title="${esc(h.texto)}">${esc(h.nombre)} · ${h.disponible === false ? "gastada" : "disponible"}</span>`).join("")
    + (p.vendaje_usado ? '<span class="etiqueta gastada" title="Vuelve tras un descanso">Vendaje · usado</span>' : "");
  const condiciones = (p.condiciones || []).map((c) => `<span class="etiqueta condicion" title="${esc(c.efecto)}">${esc(c.nombre)}${c.niveles > 1 ? ` ${c.niveles}` : ""}: ${esc(c.efecto || "")}</span>`).join("");
  const equipo = (p.equipo || []).map((x) => `<li>${esc(x.nombre)}${x.dano ? ` — <b>${esc(x.dano)}</b>${x.distancia ? " a distancia" : ""}` : ""}${x.texto ? ` <span class="texto-3">(${esc(x.texto)})</span>` : ""}</li>`).join("");
  const rasgos = (p.rasgos || []).map((r) => `<li><b>${esc(r.nombre)}:</b> ${esc(r.texto)}</li>`).join("");
  const habilidadesTexto = (p.habilidades || []).map((h) => `<li><b>${esc(h.nombre)}:</b> ${esc(h.texto || "")}</li>`).join("");
  const retrato = [["Aspecto", p.aspecto], ["Personalidad", p.personalidad], ["Bueno para", p.bueno_para]].filter(([, v]) => v)
    .map(([k, v]) => `<p><b>${k}:</b> ${esc(v)}</p>`).join("");
  const pct = p.vida_max ? Math.max(0, Math.min(100, (100 * p.vida) / p.vida_max)) : 0;
  return `
  <article class="ficha" style="--color:${colorSeguro(p.color, "var(--acento)")}">
    <header><h3>${esc(p.nombre)}</h3><span class="rol">${esc(p.rol || "")} · nivel ${esc(p.nivel ?? 1)}</span></header>
    <div class="vida">
      <div class="vida-pista" role="meter" aria-label="Vida de ${esc(p.nombre)}" aria-valuemin="0" aria-valuemax="${esc(p.vida_max)}" aria-valuenow="${esc(p.vida)}"><div class="vida-relleno" data-estado="${est}" style="width:${pct}%"></div></div>
      <span class="vida-num">${esc(p.vida)}/${esc(p.vida_max)}</span>
      <span class="vida-estado">${etiquetaVida}</span>
    </div>
    <dl class="defensas"><div><dt>Defensa</dt><dd>${esc(p.defensa ?? "-")}</dd></div><div><dt>Protección</dt><dd>${esc(p.proteccion ?? 0)}</dd></div></dl>
    <ul class="atributos${moderno ? " seis" : ""}">${atributos}</ul>
    ${condiciones ? `<div class="etiquetas">${condiciones}</div>` : ""}
    ${habilidades ? `<div class="etiquetas">${habilidades}</div>` : ""}
    ${p.oficio?.aplica ? `<p class="oficio">Oficio ${signo(p.oficio.bono)}: ${esc(p.oficio.aplica)}</p>` : ""}
    <details><summary>Habilidades, equipo y rasgos</summary><ul>${habilidadesTexto}${equipo}${rasgos}</ul></details>
    ${retrato ? `<details><summary>Quién es</summary><div class="retrato">${retrato}</div></details>` : ""}
  </article>`;
}

function pintarEnemigos(lista) {
  if (!lista?.length) return "";
  const filas = lista.map((e) => `<tr><td>${esc(e.nombre)}</td><td>${esc(e.vida)}/${esc(e.vida_max)}</td><td>${esc(e.defensa)}</td><td>${signo(e.ataque || 0)}</td><td>${esc(e.dano || (e.armas || []).map((a) => `${a.nombre} ${a.dano}`).join(" / "))}</td><td>${esc(e.proteccion || 0)}</td></tr>`).join("");
  return `<div class="enemigos"><h3>Amenazas en escena</h3><table><thead><tr><th>Quién</th><th>Vida</th><th>Defensa</th><th>Ataque</th><th>Daño</th><th>Prot.</th></tr></thead><tbody>${filas}</tbody></table></div>`;
}

function pintarFichas() {
  const d = app.datos;
  $("#fichas").innerHTML = (d.personajes || []).map((p) => pintarFicha(p, d)).join("") || '<p class="texto-3">Sin personajes.</p>';
  $("#enemigos").innerHTML = pintarEnemigos(d.enemigos);
}

// ---------- zona (cuadrícula) ----------
// Aquí no hay reglas: el motor resuelve terreno, visión, cobertura, camino, área e
// iluminación (mesa/mapis/zona.py → `proyeccion_zona`) y el visor solo pinta lo que
// llega en `/api/zona`. Una sola fuente de verdad para el SRD, también en pantalla.
const COLUMNAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const CASILLA = 32;

function coordenada(celda) {
  const m = /^([A-Z])(\d{1,2})$/i.exec(String(celda || "").trim());
  return m ? [COLUMNAS.indexOf(m[1].toUpperCase()), Number(m[2]) - 1] : null;
}
const nombreCelda = (c, f) => `${COLUMNAS[c]}${f + 1}`;

const PARAMETROS_ZONA = () => {
  const p = new URLSearchParams({ p: app.slug });
  if (app.origenZona) p.set("origen", app.origenZona);
  if (app.destinoZona) p.set("destino", app.destinoZona);
  if (app.plantillaZona && app.plantillaZona !== "ninguna") {
    p.set("forma", app.plantillaZona);
    p.set("tamano", String(app.tamanoArea || 4.5));
  }
  return p;
};

async function proyeccionZona(forzar = false) {
  // La proyección cambia con el mapa, las fichas y lo que el jugador está midiendo;
  // si nada de eso se movió, no se vuelve a pintar el SVG entero.
  const firma = JSON.stringify([PARAMETROS_ZONA().toString(), app.firmaZonaMapa]);
  if (!forzar && firma === app.firmaZona) return app.proyeccion;
  const datos = await api(`/api/zona?${PARAMETROS_ZONA()}`);
  app.firmaZona = firma;
  app.proyeccion = datos;
  return datos;
}

function pintarZona(forzar = false) {
  const e = app.datos?.escena || {};
  let html = "";
  if (e.imagen) {
    const src = `/media/${encodeURIComponent(app.slug)}/${encodeURIComponent(e.imagen)}`;
    html += `<figure class="escena-figura"><div class="escena-imagen"><img src="${src}" alt="${esc(e.titulo || "Escena")}"></div></figure>`;
  }
  html += `<div class="escena-texto"><h2>${esc(e.titulo || "Escena")}</h2><p class="texto-2">${esc([e.lugar, e.hora, e.clima].filter(Boolean).join(" · "))}</p>${e.descripcion ? `<p class="narracion">${esc(e.descripcion)}</p>` : ""}</div>`;

  const zona = $("#v-zona");
  if (!e.mapa?.filas?.length) {
    zona.innerHTML = html + '<p class="texto-3">Sin mapa de zona todavía: el narrador lo dibuja con <code>mapa zona</code> o <code>mapa generar</code> cuando haga falta decidir en metros.</p>';
    app.firmaZona = "";
    return;
  }
  // Si la proyección ya está en caché y sigue valiendo, se pinta al instante; si hay
  // que pedirla, se pinta el texto ya y el SVG en cuanto llegue.
  if (!forzar && app.firmaZona && app.firmaZonaMapa === app.firmaZona && !app.zonaPendiente) {
    return pintarZonaCon(app.proyeccion);
  }
  zona.innerHTML = html + '<p class="texto-3">Calculando la zona…</p>';
  const token = ++app.zonaToken;
  app.zonaPendiente = true;
  proyeccionZona(forzar).then((p) => {
    if (token !== app.zonaToken) return; // llegó una respuesta más nueva: esta ya no vale
    app.zonaPendiente = false;
    pintarZonaCon(p);
  }).catch((err) => {
    if (token !== app.zonaToken) return;
    app.zonaPendiente = false;
    console.error(err);
    zona.innerHTML = html + '<p class="texto-3">No se pudo calcular la zona.</p>';
  });
}

function pintarZonaCon(p) {
  const e = app.datos?.escena || {};
  const mapa = e.mapa;
  const html0 = `<div class="escena-texto"><h2>${esc(e.titulo || "Escena")}</h2><p class="texto-2">${esc([e.lugar, e.hora, e.clima].filter(Boolean).join(" · "))}</p>${e.descripcion ? `<p class="narracion">${esc(e.descripcion)}</p>` : ""}</div>`;
  if (!p.hay_mapa) {
    $("#v-zona").innerHTML = html0 + '<p class="texto-3">Sin mapa de zona todavía.</p>';
    return;
  }

  const porChar = {};
  for (const t of p.terrenos) porChar[t.caracter] = t;
  const luzPorCelda = {};
  for (const x of p.luz) luzPorCelda[x.celda] = x.nivel;
  const fichas = p.fichas || [];
  const filas = mapa.filas, ancho = filas[0].length, alto = filas.length, T = CASILLA, M = 22;
  const celdaM = p.celda || 1.5;
  if (!app.origenZona || !fichas.some((f) => f.quien === app.origenZona)) {
    app.origenZona = (fichas.find((f) => f.clase === "personaje") || fichas[0])?.quien || null;
  }
  if (app.destinoZona && !coordenada(app.destinoZona)) app.destinoZona = null;
  app.plantillaZona ||= "ninguna";
  app.tamanoArea ||= 4.5;

  const origen = fichas.find((f) => f.quien === app.origenZona);
  const infoLinea = p.linea || null;
  const infoCamino = p.camino || null;
  const infoArea = p.area || null;
  const setArea = new Set(infoArea?.casillas || []), setSombraArea = new Set(infoArea?.sombra || []);
  const setObst = new Set(infoLinea?.obstaculos || []);
  const luzCelda = (c) => luzPorCelda[c] || p.luz_base;

  let svg = `<defs>
      <pattern id="pat-solido" width="16" height="16" patternUnits="userSpaceOnUse">
        <rect width="16" height="16" fill="var(--t-solido)"/>
        <path d="M0 8h16M8 0v8M0 8v8" stroke="color-mix(in srgb, var(--fondo) 25%, transparent)" stroke-width="1"/>
      </pattern>
      <pattern id="pat-suelo" width="32" height="32" patternUnits="userSpaceOnUse">
        <rect width="32" height="32" fill="var(--t-suelo)"/>
        <circle cx="16" cy="16" r="0.9" fill="color-mix(in srgb, var(--texto) 14%, transparent)"/>
      </pattern>
      <pattern id="pat-agua" width="16" height="16" patternUnits="userSpaceOnUse">
        <rect width="16" height="16" fill="var(--t-agua)"/>
        <path d="M2 6q3-3 6 0t6 0M2 12q3-3 6 0t6 0" fill="none" stroke="color-mix(in srgb, var(--superficie) 42%, transparent)" stroke-width="1.2"/>
      </pattern>
      <pattern id="pat-planta" width="16" height="16" patternUnits="userSpaceOnUse">
        <rect width="16" height="16" fill="var(--t-planta)"/>
        <circle cx="5" cy="6" r="2.2" fill="color-mix(in srgb, var(--texto) 16%, transparent)"/>
        <circle cx="11" cy="11" r="2.5" fill="color-mix(in srgb, var(--texto) 14%, transparent)"/>
      </pattern>
    </defs>`;
  const usarFondo = Boolean(mapa.fondo) && app.mostrarFondoZona !== false;
  if (usarFondo) {
    const srcFondo = `/media/${encodeURIComponent(app.slug)}/${encodeURIComponent(mapa.fondo)}`;
    svg += `<image class="zona-fondo" href="${srcFondo}" x="0" y="0" width="${ancho * T}" height="${alto * T}" preserveAspectRatio="none"/>`;
  }
  for (let c = 0; c < ancho; c++) svg += `<text class="eje" x="${c * T + T / 2}" y="-8">${COLUMNAS[c]}</text>`;
  for (let f = 0; f < alto; f++) svg += `<text class="eje" x="-8" y="${f * T + T / 2 + 4}" text-anchor="end">${f + 1}</text>`;
  const esMuro = (c, f) => c >= 0 && c < ancho && f >= 0 && f < alto && (porChar[filas[f][c]]?.clase === "solido");
  for (let f = 0; f < alto; f++) {
    for (let c = 0; c < ancho; c++) {
      const ch = filas[f][c];
      if (ch === " ") continue;
      const t = porChar[ch];
      if (!t) continue;
      const nombre = nombreCelda(c, f);
      const x = c * T, y = f * T;
      const nivelLuz = luzCelda(nombre);
      const extraCls = [
        usarFondo ? "con-fondo" : "",
        nombre === app.destinoZona ? "destino" : "",
        setArea.has(nombre) ? "en-area" : "",
        setSombraArea.has(nombre) ? "sombra-area" : "",
        setObst.has(nombre) ? "obstaculo" : "",
      ].filter(Boolean).join(" ");
      const semTxt = [t.dificil ? "terreno difícil" : "", t.cobertura !== "ninguna" ? `cobertura ${t.cobertura}` : "", nivelLuz !== p.luz_base ? `luz: ${nivelLuz}` : ""].filter(Boolean).join(" · ");
      svg += `<rect class="casilla t-${t.clase}${extraCls ? " " + extraCls : ""}" x="${x}" y="${y}" width="${T}" height="${T}" data-c="${nombre}"><title>${nombre} · ${esc(t.significado)}${semTxt ? ` (${esc(semTxt)})` : ""}</title></rect>`;
      if (t.clase === "solido") {
        if (!esMuro(c, f - 1)) svg += `<line class="muro-borde" x1="${x}" y1="${y + 1.5}" x2="${x + T}" y2="${y + 1.5}"/>`;
        if (!esMuro(c, f + 1)) svg += `<line class="muro-borde" x1="${x}" y1="${y + T - 1.5}" x2="${x + T}" y2="${y + T - 1.5}"/>`;
        if (!esMuro(c - 1, f)) svg += `<line class="muro-borde" x1="${x + 1.5}" y1="${y}" x2="${x + 1.5}" y2="${y + T}"/>`;
        if (!esMuro(c + 1, f)) svg += `<line class="muro-borde" x1="${x + T - 1.5}" y1="${y}" x2="${x + T - 1.5}" y2="${y + T}"/>`;
      } else if (t.clase === "puerta") {
        const horiz = esMuro(c - 1, f) || esMuro(c + 1, f);
        svg += horiz
          ? `<rect class="detalle-puerta" x="${x + 4}" y="${y + T / 2 - 3}" width="${T - 8}" height="6" rx="1.5"/>`
          : `<rect class="detalle-puerta" x="${x + T / 2 - 3}" y="${y + 4}" width="6" height="${T - 8}" rx="1.5"/>`;
      } else if (t.clase === "ventana") {
        svg += `<rect class="detalle-ventana" x="${x + 5}" y="${y + 5}" width="${T - 10}" height="${T - 10}" rx="2"/>`;
      } else if (t.clase === "escalera") {
        for (let s = 6; s <= T - 6; s += 6) svg += `<line class="detalle-escalon" x1="${x + 5}" y1="${y + s}" x2="${x + T - 5}" y2="${y + s}"/>`;
      } else if (t.clase === "mueble") {
        svg += `<rect class="detalle-mueble" x="${x + 5}" y="${y + 5}" width="${T - 10}" height="${T - 10}" rx="4"/>`;
      }
      if (nivelLuz === "penumbra") svg += `<rect class="capa-luz penumbra" x="${x}" y="${y}" width="${T}" height="${T}"/>`;
      else if (nivelLuz === "oscuridad") svg += `<rect class="capa-luz oscuridad" x="${x}" y="${y}" width="${T}" height="${T}"/>`;
      if (t.clase !== "suelo") svg += `<text class="glifo${t.clase === "solido" || t.clase === "vacio" ? " glifo-claro" : ""}" x="${x + T / 2}" y="${y + T / 2 + 5}">${esc(ch)}</text>`;
    }
  }
  for (const foco of p.focos || []) {
    const pf = coordenada(foco.celda);
    if (!pf) continue;
    const rPix = Math.max(T * 0.8, (foco.brillante / celdaM) * T);
    svg += `<circle class="foco-halo" cx="${pf[0] * T + T / 2}" cy="${pf[1] * T + T / 2}" r="${rPix}"/>`;
  }
  if (infoCamino?.alcanzable && infoCamino.camino.length > 1) {
    const pts = infoCamino.camino.map((cel) => { const [cx, fy] = coordenada(cel); return `${cx * T + T / 2},${fy * T + T / 2}`; }).join(" ");
    svg += `<polyline class="camino-linea" points="${pts}"/>`;
  }
  if (origen && app.destinoZona) {
    const [c1, f1] = coordenada(origen.celda), [c2, f2] = coordenada(app.destinoZona);
    svg += `<line class="regla-linea${infoLinea && !infoLinea.visible ? " bloqueada" : ""}" x1="${c1 * T + T / 2}" y1="${f1 * T + T / 2}" x2="${c2 * T + T / 2}" y2="${f2 * T + T / 2}"/>`;
  }
  const porCasilla = {};
  fichas.forEach((x) => { (porCasilla[x.celda] ||= []).push(x); });
  for (const x of fichas) {
    const [c, f] = coordenada(x.celda);
    if (c == null || f == null) continue;
    const grupo = porCasilla[x.celda], i = grupo.indexOf(x), dx = (i - (grupo.length - 1) / 2) * 9;
    const relleno = x.clase === "personaje" ? colorSeguro(x.color, "var(--acento)") : x.clase === "amenaza" ? "var(--critico)" : "var(--texto-3)";
    svg += `<g class="ficha-zona ${x.clase}${x.quien === app.origenZona ? " origen" : ""}" data-quien="${esc(x.quien)}" data-c="${esc(x.celda)}" transform="translate(${c * T + T / 2 + dx} ${f * T + T / 2})" tabindex="0" role="button" aria-label="${esc(x.quien)} en ${esc(x.celda)}"><circle r="12" fill="${relleno}"/><text y="5">${esc(x.marca)}</text><title>${esc(x.quien)} (${esc(x.celda)}): ${esc(x.donde || "")}</title></g>`;
  }

  const modos = [["ninguna", "Visión y camino"], ["cono", "Cono"], ["esfera", "Esfera"], ["linea", "Línea"], ["cubo", "Cubo"]];
  const tamanos = [3, 4.5, 6, 9];
  let html = html0 + `<div class="zona-herramientas" role="group" aria-label="Herramientas tácticas de zona">
      <div class="zona-modos">${modos.map(([id, etiq]) => `<button type="button" data-plantilla="${id}" class="${app.plantillaZona === id ? "activo" : ""}">${etiq}</button>`).join("")}</div>
      ${app.plantillaZona !== "ninguna" ? `<div class="zona-tamanos">${tamanos.map((m) => `<button type="button" data-tamano-area="${m}" class="${Number(app.tamanoArea) === m ? "activo" : ""}">${metros(m)}</button>`).join("")}</div>` : ""}
      ${mapa.fondo ? `<button type="button" data-alternar-fondo="1" class="${usarFondo ? "activo" : ""}" title="Alternar imagen de fondo del mapa">Fondo: ${usarFondo ? "sí" : "no"}</button>` : ""}
      <span class="chip luz-chip" title="Iluminación ambiental">Luz: ${esc(p.luz_base)}</span>
    </div>`;
  html += `<div class="mapa-zona"><svg viewBox="${-M} ${-M} ${ancho * T + M + 2} ${alto * T + M + 2}" role="img" aria-label="Mapa de la zona: ${esc(mapa.nombre || e.lugar || "")}">${svg}</svg></div>`;
  if (mapa.origen?.licencia) {
    html += `<p class="mapa-licencia texto-3">Mapa: ${esc(mapa.origen.fuente || mapa.origen.archivo || "catálogo")} · Licencia: <b>${esc(mapa.origen.licencia)}</b></p>`;
  }
  let regla = `Casilla de ${metros(celdaM)}. `;
  if (origen && app.destinoZona && infoLinea) {
    const n = infoLinea.distancia_casillas;
    const vis = infoLinea.visible ? "visión clara" : "visión bloqueada";
    const cob = infoLinea.cobertura && infoLinea.cobertura !== "ninguna"
      ? ` · cobertura ${infoLinea.cobertura}${infoLinea.bono ? ` (+${infoLinea.bono})` : ""}`
      : " · sin cobertura";
    const camTxt = infoCamino?.alcanzable ? ` · camino ${metros(infoCamino.metros_coste)}` : " · paso bloqueado";
    regla += `<b>${esc(origen.quien)}</b> (${esc(origen.celda)}) → ${esc(app.destinoZona)}: ${n} ${n === 1 ? "casilla" : "casillas"} · <b>${metros(n * celdaM)}</b> (${vis}${cob}${camTxt})`;
    if (infoArea) {
      regla += `<br>Área <b>${esc(app.plantillaZona)} ${metros(app.tamanoArea)}</b>: ${infoArea.casillas.length} casillas${infoArea.fichas.length ? ` · Afecta a: <b>${esc(infoArea.fichas.join(", "))}</b>` : ""}`;
    }
  } else if (origen) {
    regla += `Midiendo desde <b>${esc(origen.quien)}</b>: toca una casilla para ver visión, cobertura, camino${app.plantillaZona !== "ninguna" ? ` y el área (${esc(app.plantillaZona)})` : ""}.`;
  }
  html += `<p class="regla" aria-live="polite">${regla}</p>`;
  if (fichas.length) {
    html += `<ul class="leyenda-fichas">${fichas.map((x) => {
      const dist = origen && x !== origen && x.distancia_m != null ? ` · ${metros(x.distancia_m)}` : "";
      const fondo = x.clase === "personaje" ? colorSeguro(x.color, "var(--acento)") : x.clase === "amenaza" ? "var(--critico)" : "var(--texto-3)";
      return `<li><span class="marca-ficha" style="background:${fondo}">${esc(x.marca)}</span><b>${esc(x.quien)}</b> <span class="texto-3">${esc(x.celda)}${x.clase === "amenaza" ? " · amenaza" : ""}${dist}</span><br><span class="texto-2">${esc(x.donde || "")}</span></li>`;
    }).join("")}</ul>`;
  }
  html += `<ul class="leyenda-terreno">${p.terrenos.map((t) => {
    const et = [t.dificil && !t.bloquea_paso ? "difícil" : "", t.cobertura !== "ninguna" && t.cobertura !== "total" ? `cob. ${t.cobertura}` : ""].filter(Boolean).join(", ");
    return `<li><span class="muestra t-${t.clase}">${t.clase === "suelo" ? "" : esc(t.caracter)}</span><span>${esc(t.significado)}${et ? ` <small class="texto-3">(${esc(et)})</small>` : ""}</span></li>`;
  }).join("")}</ul>`;

  const sinCasilla = (e.posiciones || []).filter((x) => !coordenada(x.celda));
  if (sinCasilla.length) {
    html += `<h3 class="subtitulo-panel">${mapa ? "Sin casilla en el mapa" : "Posiciones"}</h3><ul class="posiciones">${sinCasilla.map((x) => `<li><b>${esc(x.quien)}</b><span>${esc(x.donde)}</span></li>`).join("")}</ul>`;
  }
  $("#v-zona").innerHTML = html;
}

// El jugador cambió lo que está midiendo: hay que pedir la proyección de nuevo.
function refrescarZona() {
  app.firmaZona = "";
  return pintarZona(true);
}
$("#v-zona").addEventListener("click", (ev) => {
  if (ev.target.closest("button[data-alternar-fondo]")) {
    app.mostrarFondoZona = app.mostrarFondoZona === false;
    return refrescarZona();
  }
  const btnPlantilla = ev.target.closest("button[data-plantilla]");
  if (btnPlantilla) {
    app.plantillaZona = btnPlantilla.dataset.plantilla;
    return refrescarZona();
  }
  const btnTam = ev.target.closest("button[data-tamano-area]");
  if (btnTam) {
    app.tamanoArea = Number(btnTam.dataset.tamanoArea);
    return refrescarZona();
  }
  const ficha = ev.target.closest(".ficha-zona");
  if (ficha) {
    if (!ficha.classList.contains("personaje") && app.origenZona && app.origenZona !== ficha.dataset.quien && app.destinoZona !== ficha.dataset.c) {
      app.destinoZona = ficha.dataset.c;
    } else {
      app.origenZona = ficha.dataset.quien;
      app.destinoZona = null;
    }
    return refrescarZona();
  }
  const casilla = ev.target.closest("rect.casilla");
  if (casilla) {
    app.destinoZona = casilla.dataset.c === app.destinoZona ? null : casilla.dataset.c;
    refrescarZona();
  }
});
$("#v-zona").addEventListener("keydown", (ev) => {
  const ficha = ev.target.closest(".ficha-zona");
  if (ficha && (ev.key === "Enter" || ev.key === " ")) {
    ev.preventDefault();
    app.origenZona = ficha.dataset.quien;
    app.destinoZona = null;
    refrescarZona();
  }
});

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
function pintarMundo() {
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

// Toda escritura del visor: memoria y chat. El servidor exige el token de esta ejecución.
async function enviarPost(ruta, cuerpo) {
  const r = await fetch(`${ruta}?p=${encodeURIComponent(app.slug)}`, {
    method: "POST", cache: "no-store",
    headers: { "Content-Type": "application/json", "X-Mesa-Token": app.token || "" },
    body: JSON.stringify(cuerpo),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `error ${r.status}`);
  return j;
}

// ---------- hechos clave (memoria editable) ----------
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

// ---------- chat ----------
// Texto del narrador con un markdown mínimo y seguro: se escapa primero y luego se marcan negritas,
// cursivas, código, citas y listas.
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
  const pjs = app.datos?.personajes || [];
  return pjs.length === 1 ? pjs[0].nombre : (m.autor && m.autor !== "jugador" ? m.autor : "Jugador");
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
    case "vida": return t((e.despues ?? 0) < (e.antes ?? 0) ? "dano" : "cura", `<b>${esc(e.quien)}</b> · vida ${tras(e)}${e.motivo ? ` <span class="texto-3">· ${esc(e.motivo)}</span>` : ""}`, "ficha");
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
    default: return "";
  }
}

function partesHTML(partes, porSeq) {
  return partes.map((p) => (p.tipo === "texto" ? `<div class="narracion-chat">${md(p.texto)}</div>` : tarjetaEvento(porSeq.get(p.seq)))).join("");
}

function htmlMensaje(m, porSeq) {
  if (m.rol === "sistema") return `<p class="sistema">${esc(m.texto)}</p>`;
  if (m.rol === "jugador") return burbuja("jugador", nombreJugador(m), `<p>${esc(m.texto).replace(/\n/g, "<br>")}</p>`, hora(m.ts));
  const sub = [m.autor, hora(m.ts), m.parada && m.parada !== "end_turn" ? ({ cancelled: "detenido", error: "interrumpido" }[m.parada] || m.parada) : ""].filter(Boolean).join(" · ");
  return burbuja("narrador", "Narrador", partesHTML(m.partes || [{ tipo: "texto", texto: m.texto }], porSeq), sub);
}

// Un turno narrado desde la terminal: lo que declaró cada uno, lo que pasó en la mesa y el resumen.
function htmlTurnoTerminal(turno, grupo) {
  const acciones = Object.entries(turno.acciones || {}).map(([k, v]) => burbuja("jugador", k, `<p>${esc(v)}</p>`, hora(turno.ts))).join("");
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
  const firmaH = JSON.stringify([app.chatSeq, app.ultimoSeq, n.en_curso?.desde ?? null, app.datos?.version ?? null]);
  if (forzar || firmaH !== app.firmaHistorial) {
    app.firmaHistorial = firmaH;
    const items = itemsDelChat();
    $("#chat-historial").innerHTML = items.map((i) => i.html).join("") || `<div class="chat-vacio"><h2>${esc(app.datos?.titulo || "")}</h2><p>${app.chatActivo ? "La historia empieza aquí: escribe qué hace tu personaje." : "Todavía no hay turnos."}</p></div>`;
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
        ${app.escritura ? `<p class="acciones"><button type="button" data-permiso="${esc(n.permiso.id)}" data-permitir="si">Permitir una vez</button> <button type="button" data-permiso="${esc(n.permiso.id)}" data-permitir="no" class="principal">Rechazar</button></p>` : ""}
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
  $(".composer-fila").hidden = !puede;
  $("#enviar").disabled = ocupado;
  $("#detener").hidden = !ocupado;
  $("#sesion-nueva").hidden = !puede || ocupado || !n.sesion;
  const aviso = !app.chatActivo
    ? "Este visor no tiene narrador: se narra desde la terminal y aquí ves la partida en vivo. Para narrar aquí, arráncalo con «bin/mesa servir --agente hermes»."
    : !app.escritura ? "Solo lectura: desde aquí no se puede escribir (en el equipo de la mesa, o por Tailscale con «servir --tailscale»)." : "";
  $("#composer-aviso").hidden = !aviso;
  $("#composer-aviso").textContent = aviso;
  $("#estado-narrador").textContent = !app.chatActivo ? "" : ocupado ? `${n.nombre} ${n.en_curso.aviso}…` : `Narra ${n.nombre || "el narrador"}${n.sesion ? "" : " · al primer mensaje retoma la partida"}`;
}

async function enviarMensaje() {
  const area = $("#mensaje");
  const texto = area.value.trim();
  if (!texto || app.narrador?.en_curso) return;
  $("#enviar").disabled = true;
  try {
    await enviarPost("/api/chat", { texto });
    area.value = "";
    await sondear();
  } catch (err) {
    $("#estado-narrador").textContent = `✕ ${err.message}`;
  } finally {
    $("#enviar").disabled = Boolean(app.narrador?.en_curso);
  }
}
$("#composer").addEventListener("submit", (ev) => { ev.preventDefault(); enviarMensaje(); });
$("#mensaje").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); enviarMensaje(); }
});
$("#detener").addEventListener("click", async () => {
  try { await enviarPost("/api/chat/cancelar", {}); } catch (err) { $("#estado-narrador").textContent = `✕ ${err.message}`; }
});
$("#sesion-nueva").addEventListener("click", async () => {
  if (!confirm("¿Sesión nueva del narrador? Retomará desde la memoria de la historia, sin la conversación anterior.")) return;
  try { await enviarPost("/api/chat/sesion-nueva", {}); await sondear(); } catch (err) { $("#estado-narrador").textContent = `✕ ${err.message}`; }
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
    elegirVista(abrir.dataset.abrir);
    if (getComputedStyle($(`#abrir-${ladoDe(abrir.dataset.abrir)}`)).display !== "none" && document.body.dataset.cajon !== ladoDe(abrir.dataset.abrir)) abrirCajon(ladoDe(abrir.dataset.abrir));
  }
});
$("#chat").addEventListener("keydown", (ev) => {
  if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches("[data-abrir]")) { ev.preventDefault(); ev.target.click(); }
});

// ---------- estado ----------
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
  pintarVista();
}

async function cargarEstado() {
  const datos = await api(`/api/estado?p=${encodeURIComponent(app.slug)}`);
  const firma = JSON.stringify(datos);
  if (firma === app.firmaEstado) return;
  app.firmaEstado = firma;
  app.datos = datos;
  // Firma propia de la zona: lo que hay detrás del mapa y las fichas. Si no cambia,
  // el SVG de la zona no se vuelve a construir aunque la escena entera sea otra.
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
      // La bitácora cambió, pero el estado puede ser idéntico: `cargarEstado` lo
      // compara él mismo. Invalidar aquí a la fuerza hacía que una `nota` reconstruyera
      // el SVG entero de la zona (4.000 nodos) sin que el mapa se hubiera movido.
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

async function iniciar() {
  aplicarTema(leerTema());
  $("#nuevo-categoria").innerHTML = CATEGORIAS.map((c) => `<option${c === "otro" ? " selected" : ""}>${c}</option>`).join("");
  pintarVistas();
  try {
    const visor = await api("/api/visor").catch(() => ({ escritura: false, token: null, chat: false }));
    app.escritura = Boolean(visor.escritura && visor.token);
    app.token = visor.token;
    app.chatActivo = Boolean(visor.chat);
    app.autor = visor.autor;
    const { activa, partidas } = await api("/api/partidas");
    const pedida = new URLSearchParams(location.search).get("p");
    app.slug = pedida || activa || partidas[0]?.slug;
    $("#selector-partida").innerHTML = partidas.map((p) => `<option value="${esc(p.slug)}"${p.slug === app.slug ? " selected" : ""}>${esc(p.titulo)}</option>`).join("");
    $("#selector-partida").addEventListener("change", (ev) => { location.search = `?p=${encodeURIComponent(ev.target.value)}`; });
    if (!app.slug) { $("#nombre-historia").textContent = "No hay partidas"; return; }
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

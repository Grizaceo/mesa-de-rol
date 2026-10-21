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

const clienteSesion = () => {
  try {
    let id = sessionStorage.getItem("mesa-cliente-id");
    if (!id) {
      id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
      sessionStorage.setItem("mesa-cliente-id", id);
    }
    return id;
  } catch {
    return `c-${Math.random().toString(36).slice(2, 10)}`;
  }
};

const app = {
  slug: null, firmaEstado: "", ultimoSeq: 0, datos: null, eventos: [], sondeando: false,
  izq: leerLocal("mesa-izq", "ficha"), der: leerLocal("mesa-der", "zona"), pestana: leerLocal("mesa-registro", "pnj"), documentoNuevo: null,
  escritura: false, token: null, editando: null, novedades: new Set(), anfitrion: false, lectura: true, reclamo: "",
  sala: new URLSearchParams(location.search).get("sala") || leerLocal("mesa-sala", ""), salaDisponible: false,
  clienteId: clienteSesion(), conectados: { total: 0, jugadores: [] },
  origenZona: null, destinoZona: null, vistaMundo: null, firmaLugares: "", lugarElegido: null,
  chat: [], chatSeq: 0, narrador: { activo: false }, chatActivo: false, autor: null, jugador: "", modoOoc: false,
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
  vida: "ficha", condicion: "ficha", habilidad: "ficha", nivel: "ficha", enemigo: "ficha", vendaje: "ficha", descanso: "ficha", piloto: "ficha",
};
if (!VISTAS_IZQ.some(([id]) => id === app.izq)) app.izq = "ficha";
if (!VISTAS_DER.some(([id]) => id === app.der)) app.der = "zona";

if (new URLSearchParams(location.search).get("sala")) {
  // La clave queda en este navegador, no en la barra de direcciones ni en el historial.
  guardarLocal("mesa-sala", app.sala);
  const sinClave = new URLSearchParams(location.search);
  sinClave.delete("sala");
  history.replaceState(null, "", `${location.pathname}${sinClave.toString() ? `?${sinClave}` : ""}${location.hash}`);
}

function cabecerasSala(extra = {}) {
  const base = { "X-Mesa-Cliente": app.clienteId, ...extra };
  if (app.jugador) base["X-Mesa-Jugador"] = encodeURIComponent(app.jugador);
  if (app.sala) base["X-Mesa-Sala"] = app.sala;
  if (app.reclamo) base["X-Mesa-Reclamo"] = app.reclamo;
  return base;
}
const mostrarError = (err) => { $("#estado-narrador").textContent = `✕ ${err.message}`; };

async function api(ruta) {
  const r = await fetch(ruta, { cache: "no-store", headers: cabecerasSala() });
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
  if (e.tipo === "prueba") {
    if (e.salvacion && !e.habilidad) return `Salvación de ${ATRIBUTOS[e.atributo] || e.atributo}`;
    return [ATRIBUTOS[e.atributo], e.habilidad && `(${e.habilidad})`].filter(Boolean).join(" ");
  }
  if (e.tipo === "dano") return `daño${e.arma ? ` con ${e.arma}` : ""}${e.objetivo ? ` a ${e.objetivo}` : ""}`;
  if (e.tipo === "suerte") return "suerte";
  return e.expr || "tirada";
}

// Cómo queda el objetivo: sus PG si se ven; si no (desconocido para los personajes), solo su estado aparente.
const destinoDe = (d) => (d.vida ? ` → ${esc(d.objetivo)} ${esc(d.vida.despues)}/${esc(d.vida.maximo)}` : d.estado ? ` → ${esc(d.objetivo)} (${esc(d.estado)})` : "");

function cuentaDano(d, moderno) {
  const valores = (d.tirada?.dados || []).flatMap((t) => t.valores).join(" + ") || esc(d.tirada?.total ?? "");
  const mod = d.bonus_mod ? ` ${signo(d.bonus_mod)} (${esc(d.fuente_mod || "mod")})` : "";
  const cabeza = `Daño ${esc(d.tirada?.expr || "")}${d.tirada?.critico ? " (crítico: dados dobles)" : ""}: ${valores}${mod} = ${esc(d.bruto)}`;
  if (moderno) return `${cabeza}${d.ajuste_resistencia ? ` [${esc(d.ajuste_resistencia)}]` : ""} → <b>${esc(d.final)}</b>${destinoDe(d)}`;
  return `${cabeza} − protección ${esc(d.proteccion ?? 0)} = <b>${esc(d.final)}</b>${destinoDe(d)}`;
}

function cuentaDe(e) {
  const moderno = e.reglamento === "dnd-2024" || es2024(app.datos);
  if (e.tipo === "prueba" || e.tipo === "ataque") {
    const contra = e.cd == null ? "" : ` contra ${e.tipo === "ataque" ? (moderno ? "CA" : "Defensa") : "dificultad"} ${esc(e.cd)}`;
    let txt = e.redactado || e.total == null
      ? `${esc(e.elegido)} <span class="texto-3">(sus modificadores no se ven)</span>${contra}`
      : `${esc(e.elegido)} ${(e.partes || []).map((p) => `${signo(p.valor)} ${esc(p.fuente)}`).join(" ")} = <b>${esc(e.total)}</b>${contra}`;
    if (e.dano) txt += `<br>${cuentaDano(e.dano, moderno)}`;
    if (e.dano_maestria) txt += `<br>Maestría Rozar: <b>${esc(e.dano_maestria.final)}</b>${destinoDe(e.dano_maestria)}`;
    return txt;
  }
  if (e.tipo === "suerte") return `d100 = <b>${esc(e.valor)}</b> contra ${esc(e.probabilidad)}%`;
  const suma = (e.dados || []).flatMap((t) => t.valores).join(" + ");
  const total = e.bonus_mod ? e.bruto : e.total;
  let txt = `${esc(e.expr || "")}${e.critico ? " (crítico)" : ""}: ${suma}${e.modificador ? ` ${signo(e.modificador)}` : ""}`
    + `${e.bonus_mod ? ` ${signo(e.bonus_mod)} (${esc(e.fuente_mod || "mod")})` : ""} = <b>${esc(total)}</b>`;
  if (e.tipo === "dano" && e.objetivo) {
    txt += moderno
      ? `${e.ajuste_resistencia ? ` [${esc(e.ajuste_resistencia)}]` : ""} → <b>${esc(e.final)}</b>${destinoDe(e)}`
      : ` − protección ${esc(e.proteccion ?? 0)} = <b>${esc(e.final)}</b>${destinoDe(e)}`;
  }
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
    fallo_automatico: ["fallo", "✕ Fallo automático (condición)"],
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
    const total = e.tipo === "suerte" ? e.valor : (e.final ?? e.total ?? e.elegido);
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

// ---------- ficha (estilo D&D Beyond) ----------
const ESTADOS_APARENTES = {
  "ileso": ["ileso", "✓ Ileso"], "herida leve": ["leve", "◐ Herida leve"], "herido": ["herido", "▲ Herido"],
  "grave": ["grave", "▲ Grave"], "fuera de combate": ["fuera", "✕ Fuera de combate"], "muerto": ["fuera", "✕ Muerto"],
};
function estadoVida(p) {
  // De quien no se ven las estadísticas llega solo cómo se le ve (vista.py), no sus PG.
  if (ESTADOS_APARENTES[p.estado_aparente]) return ESTADOS_APARENTES[p.estado_aparente];
  const r = p.vida_max ? p.vida / p.vida_max : 0;
  if (p.vida <= 0) return ["fuera", "✕ Fuera de combate"];
  if (r >= 1) return ["ileso", "✓ Ileso"];
  if (r > 0.5) return ["leve", "◐ Herida leve"];
  if (r > 0.25) return ["herido", "▲ Herido"];
  return ["grave", "▲ Grave"];
}
const es2024 = (d) => Number(d?.schema_version) === 2 || d?.reglamento === "dnd-2024";

const ORDEN_6_STATS = [
  ["fuerza", "STRENGTH", "STR"],
  ["destreza", "DEXTERITY", "DEX"],
  ["constitucion", "CONSTITUTION", "CON"],
  ["inteligencia", "INTELLIGENCE", "INT"],
  ["sabiduria", "WISDOM", "WIS"],
  ["carisma", "CHARISMA", "CHA"],
];

const HABILIDADES_DDB = [
  ["acrobacias", "DEX", "destreza", "Acrobatics · Acrobacias"],
  ["trato con animales", "WIS", "sabiduria", "Animal Handling · Animales"],
  ["arcanos", "INT", "inteligencia", "Arcana · Arcanos"],
  ["atletismo", "STR", "fuerza", "Athletics · Atletismo"],
  ["engano", "CHA", "carisma", "Deception · Engaño"],
  ["historia", "INT", "inteligencia", "History · Historia"],
  ["perspicacia", "WIS", "sabiduria", "Insight · Perspicacia"],
  ["intimidacion", "CHA", "carisma", "Intimidation · Intimidación"],
  ["investigacion", "INT", "inteligencia", "Investigation · Investigación"],
  ["medicina", "WIS", "sabiduria", "Medicine · Medicina"],
  ["naturaleza", "INT", "inteligencia", "Nature · Naturaleza"],
  ["percepcion", "WIS", "sabiduria", "Perception · Percepción"],
  ["interpretacion", "CHA", "carisma", "Performance · Interpretación"],
  ["persuasion", "CHA", "carisma", "Persuasion · Persuasión"],
  ["religion", "INT", "inteligencia", "Religion · Religión"],
  ["juego de manos", "DEX", "destreza", "Sleight of Hand · J. de manos"],
  ["sigilo", "DEX", "destreza", "Stealth · Sigilo"],
  ["supervivencia", "WIS", "sabiduria", "Survival · Supervivencia"],
];

let pjActivoFicha = "";
let tabDdbPorPj = {};
let filtroAccionPorPj = {};
let modalDdbPj = null;
let tabModalPrincipal = "sheet";
let filtroInvCategoria = "all";
let filtroInvTexto = "";
let mostrarFormNuevoItem = false;

const RANURAS_PAPERDOLL = [
  null, ["head", "Head"], null,
  ["ammo", "Ammunition"], ["neck", "Neck"], ["armor", "Armor"],
  ["off_hand", "Off-Hand"], ["chest", "Torso"], ["main_hand", "Weapon"],
  ["gloves", "Gloves"], ["belt", "Belt"], ["ring", "Ring"],
  null, ["legs", "Trousers"], null,
  null, ["boots", "Boots"], null,
];

function inferirCategoriaItem(x) {
  if (x.categoria) return x.categoria;
  if (x.dano) return "weapon";
  const n = sinTildes(x.nombre || "");
  if (x.bono_ca || /armadura|cota|malla|cuero|escudo|casco|chaleco|shield|vest|armor/.test(n)) return "armor";
  return "gear";
}

function inferirRanuraItem(x) {
  if (x.ranura) return x.ranura;
  const n = sinTildes(x.nombre || "");
  if (/casco|yelmo|sombrero|capucha|head|helm/.test(n)) return "head";
  if (/amuleto|collar|medallon|neck/.test(n)) return "neck";
  if (/escudo|rodela|antorcha|shield/.test(n)) return "off_hand";
  if (/cota|armadura|coraza|chaleco|cuero|malla|vest|armor/.test(n)) return "armor";
  if (/camisa|tunica|ropas|capa|manto|shirt|cloak/.test(n)) return "chest";
  if (/guante|manopla|gloves/.test(n)) return "gloves";
  if (/cinturon|cinto|belt/.test(n)) return "belt";
  if (/anillo|sortija|ring/.test(n)) return "ring";
  if (/pantalon|greba|calzas|trousers|legs/.test(n)) return "legs";
  if (/bota|calzado|zapato|boots/.test(n)) return "boots";
  if (/flecha|virote|municion|ammo/.test(n)) return "ammo";
  if (x.dano) return "main_hand";
  return "";
}

function svgArteItem(x) {
  const n = sinTildes(x.nombre || "");
  const cat = inferirCategoriaItem(x);
  if (/arco|bow|ballesta/.test(n)) {
    return `<svg viewBox="0 0 120 100"><defs><radialGradient id="g-bow" cx="50%" cy="50%" r="60%"><stop offset="0%" stop-color="#3b2d1f"/><stop offset="100%" stop-color="#11161f"/></radialGradient></defs><rect width="120" height="100" fill="url(#g-bow)"/><path d="M38 14 C78 30, 78 70, 38 86" fill="none" stroke="#c89b52" stroke-width="5" stroke-linecap="round"/><line x1="38" y1="14" x2="38" y2="86" stroke="#cbd5e1" stroke-width="1.6"/><line x1="24" y1="50" x2="88" y2="50" stroke="#e2b86b" stroke-width="3"/><polygon points="92,50 80,44 82,50 80,56" fill="#94a3b8"/></svg>`;
  }
  if (/escudo|shield/.test(n)) {
    return `<svg viewBox="0 0 120 100"><defs><radialGradient id="g-sh" cx="50%" cy="45%" r="60%"><stop offset="0%" stop-color="#2c3e55"/><stop offset="100%" stop-color="#0f141c"/></radialGradient></defs><rect width="120" height="100" fill="url(#g-sh)"/><path d="M36 18 H84 V50 C84 70, 60 84, 60 88 C60 84, 36 70, 36 50 Z" fill="#475569" stroke="#d8a657" stroke-width="4"/><circle cx="60" cy="48" r="9" fill="#d8a657"/></svg>`;
  }
  if (/pocion|elixir|frasco|potion/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#131922"/><rect x="52" y="16" width="16" height="12" rx="2" fill="#a16207"/><path d="M48 28 H72 L84 62 C86 76, 76 86, 60 86 C44 86, 34 76, 36 62 Z" fill="#dc2626" stroke="#fca5a5" stroke-width="3"/><path d="M44 58 Q60 52 76 58" fill="none" stroke="#fecaca" stroke-width="2"/></svg>`;
  }
  if (/venda|vendaje|bandage/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#182026"/><ellipse cx="56" cy="54" rx="26" ry="18" fill="#e2e8f0" stroke="#94a3b8" stroke-width="3"/><ellipse cx="56" cy="46" rx="26" ry="12" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/><ellipse cx="56" cy="46" rx="9" ry="4" fill="#64748b"/><path d="M76 58 L98 70 L90 78 L66 66" fill="#e2e8f0" stroke="#94a3b8" stroke-width="2"/></svg>`;
  }
  if (/bota|calzado|zapato|boots/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#1a1612"/><path d="M36 22 H58 V58 L84 66 C88 68, 88 78, 80 78 H34 V22 Z" fill="#78350f" stroke="#d97706" stroke-width="3"/><line x1="34" y1="74" x2="84" y2="74" stroke="#451a03" stroke-width="4"/></svg>`;
  }
  if (/cinturon|cinto|belt/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#161412"/><ellipse cx="60" cy="52" rx="36" ry="20" fill="none" stroke="#5c4028" stroke-width="12"/><rect x="48" y="58" width="24" height="16" rx="3" fill="none" stroke="#eab308" stroke-width="4"/></svg>`;
  }
  if (/capa|manto|camisa|ropas|tunica|shirt|cloak/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#151c24"/><path d="M42 20 L60 28 L78 20 L92 38 L80 46 L78 82 H42 L40 46 L28 38 Z" fill="#ca8a04" stroke="#fde047" stroke-width="2.5"/></svg>`;
  }
  if (/cota|armadura|malla|cuero|chaleco|vest|armor/.test(n) || cat === "armor") {
    return `<svg viewBox="0 0 120 100"><defs><radialGradient id="g-arm" cx="50%" cy="45%" r="60%"><stop offset="0%" stop-color="#334155"/><stop offset="100%" stop-color="#0f141c"/></radialGradient></defs><rect width="120" height="100" fill="url(#g-arm)"/><path d="M38 18 L50 26 H70 L82 18 L92 36 L80 46 V82 H40 V46 L28 36 Z" fill="#475569" stroke="#94a3b8" stroke-width="3"/><line x1="60" y1="26" x2="60" y2="80" stroke="#cbd5e1" stroke-width="2"/></svg>`;
  }
  if (/carta|contrato|pergamino|libro|mapa|scroll/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#181512"/><rect x="32" y="16" width="56" height="68" rx="4" fill="#dfd2b5" stroke="#a16207" stroke-width="3"/><line x1="42" y1="32" x2="78" y2="32" stroke="#57534e" stroke-width="2.5"/><line x1="42" y1="44" x2="78" y2="44" stroke="#57534e" stroke-width="2.5"/><line x1="42" y1="56" x2="68" y2="56" stroke="#57534e" stroke-width="2.5"/><circle cx="72" cy="70" r="7" fill="#9333ea"/></svg>`;
  }
  if (cat === "weapon" || /espada|mandoble|estoque|daga|cuchillo|hacha|jabalina|lanza|bichero|baton/.test(n)) {
    return `<svg viewBox="0 0 120 100"><defs><radialGradient id="g-wp" cx="50%" cy="50%" r="60%"><stop offset="0%" stop-color="#2a3441"/><stop offset="100%" stop-color="#0d1117"/></radialGradient></defs><rect width="120" height="100" fill="url(#g-wp)"/><line x1="28" y1="76" x2="88" y2="18" stroke="#e2e8f0" stroke-width="6" stroke-linecap="round"/><line x1="28" y1="76" x2="88" y2="18" stroke="#94a3b8" stroke-width="2"/><line x1="34" y1="56" x2="52" y2="74" stroke="#d8a657" stroke-width="5" stroke-linecap="round"/><line x1="22" y1="82" x2="36" y2="68" stroke="#78350f" stroke-width="6" stroke-linecap="round"/><circle cx="20" cy="84" r="4.5" fill="#d8a657"/></svg>`;
  }
  return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#141a22"/><rect x="34" y="26" width="52" height="48" rx="8" fill="#334155" stroke="#d8a657" stroke-width="3"/><path d="M48 26 V20 H72 V26" fill="none" stroke="#d8a657" stroke-width="3"/><circle cx="60" cy="50" r="6" fill="#f5d087"/></svg>`;
}

function calcDatosDdb(p, d) {
  const moderno = es2024(d);
  const attrs = p.atributos || {};
  const nivel = Number(p.nivel ?? 1);
  const bonoComp = Number(p.competencia_bono || (2 + Math.floor((nivel - 1) / 4)));
  const punt = (k) => {
    if (moderno) return Number(attrs[k] ?? 10);
    const mapa = { fuerza: "fuerza", constitucion: "fuerza", destreza: "agilidad", inteligencia: "ingenio", sabiduria: "ingenio", carisma: "corazon" };
    const b = Number(attrs[mapa[k] || k] ?? 0);
    return 10 + b * 2;
  };
  const mod = (k) => {
    if (moderno) return Math.floor((Number(attrs[k] ?? 10) - 10) / 2);
    const mapa = { fuerza: "fuerza", constitucion: "fuerza", destreza: "agilidad", inteligencia: "ingenio", sabiduria: "ingenio", carisma: "corazon" };
    return Number(attrs[mapa[k] || k] ?? 0);
  };
  const comp = p.competencias || {};
  const salvSet = new Set((comp.salvaciones || []).map(sinTildes));
  const habSet = new Set((comp.habilidades || []).map(sinTildes));
  const perSet = new Set((comp.pericia || comp.expertise || []).map(sinTildes));
  const modHab = (clave, attr) => {
    const c = sinTildes(clave);
    const extra = perSet.has(c) ? bonoComp * 2 : habSet.has(c) ? bonoComp : 0;
    return { total: mod(attr) + extra, comp: habSet.has(c), pericia: perSet.has(c) };
  };
  const modSalv = (attr) => {
    const tiene = salvSet.has(sinTildes(attr));
    return { total: mod(attr) + (tiene ? bonoComp : 0), comp: tiene };
  };
  return { moderno, nivel, bonoComp, punt, mod, modHab, modSalv };
}

function pintarFicha(p, d, completa = false) {
  const c = calcDatosDdb(p, d);
  const nombre = p.nombre || "Personaje";
  const tabActual = tabDdbPorPj[nombre] || "actions";
  const filtroAtk = filtroAccionPorPj[nombre] || "all";
  const velMetros = Number(p.velocidad ?? 9);
  const velPies = Math.round((velMetros / 1.5) * 5);
  const ca = Number(p.ca ?? p.defensa ?? 12);
  const ini = c.mod("destreza");
  const pasivaPerc = 10 + c.modHab("percepcion", "sabiduria").total;
  const pasivaInv = 10 + c.modHab("investigacion", "inteligencia").total;
  const pasivaIns = 10 + c.modHab("perspicacia", "sabiduria").total;

  const escudosStats = ORDEN_6_STATS.map(([k, lbl]) => `
    <button type="button" class="ddb-attr" data-ddb-roll="prueba" data-ddb-quien="${esc(nombre)}" data-ddb-attr="${k}" title="Tirar prueba de ${esc(ATRIBUTOS[k] || lbl)}">
      <span class="ddb-attr-lbl">${lbl}</span>
      <span class="ddb-attr-mod">${signo(c.mod(k))}</span>
      <span class="ddb-attr-score">${c.punt(k)}</span>
    </button>`).join("");

  const savesHtml = ORDEN_6_STATS.map(([k, , abbr]) => {
    const s = c.modSalv(k);
    return `<button type="button" class="ddb-save-item" data-ddb-roll="salvacion" data-ddb-quien="${esc(nombre)}" data-ddb-attr="${k}" title="Salvación de ${esc(ATRIBUTOS[k] || abbr)}">
      <span class="ddb-dot${s.comp ? " activo" : ""}"></span>
      <span class="ddb-save-abbr">${abbr}</span>
      <span class="ddb-mod-pill">${signo(s.total)}</span>
    </button>`;
  }).join("");

  const sensesHtml = `
    <div class="ddb-senses-list">
      <div class="ddb-sense-row"><span class="ddb-sense-val">${pasivaPerc}</span><span>Passive Perception</span></div>
      <div class="ddb-sense-row"><span class="ddb-sense-val">${pasivaInv}</span><span>Passive Investigation</span></div>
      <div class="ddb-sense-row"><span class="ddb-sense-val">${pasivaIns}</span><span>Passive Insight</span></div>
    </div>`;

  const skillsHtml = HABILIDADES_DDB.map(([clave, abbr, attr, etiqueta]) => {
    const h = c.modHab(clave, attr);
    return `<button type="button" class="ddb-skill-row" data-ddb-roll="prueba" data-ddb-quien="${esc(nombre)}" data-ddb-attr="${esc(clave)}" title="Tirar ${esc(etiqueta)}">
      <span class="ddb-dot${h.pericia ? " pericia" : h.comp ? " activo" : ""}" title="${h.pericia ? "Pericia (×2)" : h.comp ? "Competente" : "Sin competencia"}"></span>
      <span class="ddb-skill-mod">${abbr}</span>
      <span class="ddb-skill-name">${esc(etiqueta)}</span>
      <span class="ddb-mod-pill">${signo(h.total)}</span>
    </button>`;
  }).join("");

  const armas = (p.equipo || []).filter((x) => x.dano);
  const filasArmas = armas.map((a) => {
    const esSutil = (a.propiedades || []).map(sinTildes).some((x) => x === "sutil" || x === "finesse");
    const usaDes = a.distancia || (esSutil && c.mod("destreza") >= c.mod("fuerza"));
    const modArma = c.mod(usaDes ? "destreza" : "fuerza");
    // d20-simple no suma competencia al ataque ni el atributo al daño: se muestra lo que tira el motor.
    const hit = modArma + (c.moderno && a.competente !== false ? c.bonoComp : 0);
    const dmgTxt = `${a.dano}${c.moderno && modArma ? signo(modArma) : ""}`;
    const notas = [a.tipo_dano, ...(a.propiedades || []), a.maestria ? `Maestría: ${a.maestria}` : "", a.texto].filter(Boolean).join(" · ");
    return `<tr>
      <td><span class="ddb-atk-name">${esc(a.nombre)}</span><span class="ddb-atk-sub">${a.distancia ? "Ranged Weapon" : "Melee Weapon"}</span></td>
      <td>${a.distancia ? "24/96 m" : "1,5 m"}</td>
      <td><button type="button" class="ddb-roll-btn" data-ddb-roll="ataque" data-ddb-quien="${esc(nombre)}" data-ddb-arma="${esc(a.nombre)}">${signo(hit)}</button></td>
      <td><button type="button" class="ddb-roll-btn" data-ddb-roll="dano" data-ddb-quien="${esc(nombre)}" data-ddb-arma="${esc(a.nombre)}">${esc(dmgTxt)}</button></td>
      <td class="texto-3">${esc(notas)}</td>
    </tr>`;
  }).join("");

  const hitUnarmed = c.mod("fuerza") + c.bonoComp;
  const dmgUnarmed = Math.max(1, 1 + c.mod("fuerza"));
  const filaDesarmado = `<tr>
    <td><span class="ddb-atk-name">Unarmed Strike · Golpe desarmado</span><span class="ddb-atk-sub">Melee Attack</span></td>
    <td>1,5 m</td>
    <td><button type="button" class="ddb-roll-btn" data-ddb-roll="ataque" data-ddb-quien="${esc(nombre)}" data-ddb-subtipo="desarmado">${signo(hitUnarmed)}</button></td>
    <td><span class="ddb-mod-pill">${dmgUnarmed} cont.</span></td>
    <td class="texto-3">Damage, Grapple (DC ${8 + c.bonoComp + c.mod("fuerza")}) o Shove</td>
  </tr>`;

  const habsLista = (p.habilidades || []).map((h) => `
    <div class="ddb-prof-bloque">
      <b>${esc(h.nombre)} · ${h.disponible === false ? "Gastada" : "Disponible"} (${esc(h.recarga || "escena")})</b>
      <span>${esc(h.texto || "")}</span>
    </div>`).join("");

  let contenidoTab = "";
  if (tabActual === "actions") {
    contenidoTab = `
      <div class="ddb-selector-tabs" style="margin:4px 0 8px">
        ${[["all", "ALL"], ["attack", "ATTACK"], ["action", "ACTION"], ["bonus", "BONUS & TRAITS"]].map(([id, t]) => `<button type="button" class="mini${filtroAtk === id ? " activo" : ""}" data-ddb-filtro="${id}" data-ddb-quien="${esc(nombre)}">${t}</button>`).join("")}
      </div>
      ${(filtroAtk === "all" || filtroAtk === "attack") ? `
      <table class="ddb-tabla-ataques">
        <thead><tr><th>Attack</th><th>Range</th><th>Hit / DC</th><th>Damage</th><th>Notes</th></tr></thead>
        <tbody>${filasArmas}${filaDesarmado}</tbody>
      </table>` : ""}
      ${(filtroAtk === "all" || filtroAtk === "action") ? `
      <div class="ddb-prof-bloque" style="margin-top:8px">
        <b>Actions in Combat (SRD 5.2.1)</b>
        <span>Attack · Dash (Correr) · Disengage (Destrabarse) · Dodge (Esquivar) · Grapple · Help (Ayudar) · Hide (Esconderse) · Influence · Magic · Ready (Preparar) · Search (Buscar) · Shove · Study (Estudiar) · Utilize</span>
      </div>` : ""}
      ${(filtroAtk === "all" || filtroAtk === "bonus") && habsLista ? `<div style="margin-top:8px">${habsLista}</div>` : ""}`;
  } else if (tabActual === "spells") {
    const conjuros = (p.conjuros || []).map((cj) => `<li><b>${esc(cj.nombre)}</b> (niv. ${esc(cj.nivel ?? 0)}): ${esc(cj.texto || cj.referencia || "")}</li>`).join("");
    const slots = Object.entries(p.espacios_conjuro || {}).map(([n, s]) => `<span class="etiqueta">Nivel ${esc(n)}: ${esc(s.actual)}/${esc(s.max)}</span>`).join(" ");
    contenidoTab = `
      ${slots ? `<div class="etiquetas">${slots}</div>` : ""}
      ${conjuros ? `<ul>${conjuros}</ul>` : '<p class="texto-3">Sin conjuros preparados en la ficha. Puedes lanzar un ataque de conjuro desde 🎲 Tiradas.</p>'}`;
  } else if (tabActual === "inventory") {
    const items = (p.equipo || []).map((x) => `<li><b>${esc(x.nombre)}</b>${x.dano ? ` (${esc(x.dano)} ${esc(x.tipo_dano || "")})` : ""}${x.cantidad != null ? ` ×${esc(x.cantidad)}` : ""}${x.texto ? ` — <span class="texto-3">${esc(x.texto)}</span>` : ""}</li>`).join("");
    contenidoTab = items ? `<ul>${items}</ul>` : '<p class="texto-3">Sin equipo registrado.</p>';
  } else if (tabActual === "features") {
    const rasgos = (p.rasgos || []).map((r) => `<div class="ddb-prof-bloque"><b>${esc(r.nombre)}</b><span>${esc(r.texto)}</span></div>`).join("");
    contenidoTab = (habsLista + rasgos) || '<p class="texto-3">Sin rasgos especiales.</p>';
  } else {
    const notas = [["Rol / Clase", p.rol], ["Especie", p.especie], ["Aspecto", p.aspecto], ["Personalidad", p.personalidad], ["Bueno para", p.bueno_para]]
      .filter(([, v]) => v).map(([k, v]) => `<div class="ddb-prof-bloque"><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join("");
    // Construcción del personaje: el jugador cuenta de dónde viene y qué le sube o le baja por eso.
    const tf = p.trasfondo || {};
    const subeTf = Object.entries(tf.sube || {});
    const opcionesAttr = (sel) => '<option value="">—</option>' + ORDEN_6_STATS.map(([k, , abbr]) => `<option value="${k}"${sel === k ? " selected" : ""}>${abbr}</option>`).join("");
    const historia = tf.historia ? `<div class="ddb-prof-bloque"><b>${esc(tf.nombre || "Trasfondo")}</b><span>${esc(tf.historia)}</span></div>` : "";
    const formTf = app.escritura && c.moderno ? `
      <div class="ddb-prof-bloque" data-trasfondo-de="${esc(nombre)}">
        <b>Trasfondo · de dónde viene</b>
        <input type="text" data-tf="nombre" maxlength="60" placeholder="Ej.: Vendedor ambulante del centro" value="${esc(tf.nombre || "")}">
        <textarea data-tf="historia" rows="4" maxlength="1500" placeholder="De dónde viene, qué hizo, qué lo marcó…">${esc(tf.historia || "")}</textarea>
        <label>Le sube +2 <select data-tf="mas2">${opcionesAttr(subeTf.find(([, v]) => v === 2)?.[0] || "")}</select></label>
        <label>y +1 <select data-tf="mas1">${opcionesAttr(subeTf.find(([, v]) => v === 1)?.[0] || "")}</select></label>
        <label>Le baja −1 (regla de la casa, opcional) <select data-tf="menos1">${opcionesAttr(Object.keys(tf.baja || {})[0] || "")}</select></label>
        <input type="text" data-tf="habilidades" maxlength="90" placeholder="Dos habilidades, separadas por coma (p. ej. Persuasión, Perspicacia)" value="${esc((tf.habilidades || []).join(", "))}">
        <p><button type="button" class="principal" data-ddb-trasfondo="${esc(nombre)}">Guardar trasfondo</button>
        <button type="button" data-ddb-borrar-pj="${esc(nombre)}">🗑 Borrar personaje</button></p>
      </div>` : "";
    contenidoTab = (historia + notas || '<p class="texto-3">Sin notas de trasfondo.</p>') + formTf;
  }

  const defensasTxt = [
    ...(p.resistencias || []).map((x) => `Res.: ${x}`),
    ...(p.inmunidades || []).map((x) => `Inm.: ${x}`),
    ...(p.vulnerabilidades || []).map((x) => `Vuln.: ${x}`),
  ].join(" · ") || "Resistances, Immunities, or Vulnerabilities";
  const condsTxt = (p.condiciones || []).map((x) => `${x.nombre}${x.niveles > 1 ? ` ${x.niveles}` : ""}`).join(", ") || "Sin condiciones activas";
  const profSalvTxt = (p.competencias?.salvaciones || []).join(", ") || (p.oficio?.aplica ? `Oficio: ${p.oficio.aplica}` : "Según clase");
  const profHabTxt = (p.competencias?.habilidades || []).join(", ") || "Según trasfondo";
  const dgTxt = p.dados_golpe ? `${p.dados_golpe.actual ?? 1}/${p.dados_golpe.max ?? 1} (${p.dados_golpe.dado || "d8"})` : "1/1";

  const bloqueSaves = `<div class="ddb-caja"><div class="ddb-saves-grid">${savesHtml}</div><div class="ddb-caja-pie">Saving Throws</div></div>`;
  const bloqueSenses = `<div class="ddb-caja">${sensesHtml}<div class="ddb-caja-pie">Senses</div></div>`;
  const bloqueProfs = `<div class="ddb-caja">
    <div class="ddb-prof-bloque"><b>Saving Throws</b><span>${esc(profSalvTxt)}</span></div>
    <div class="ddb-prof-bloque"><b>Skills</b><span>${esc(profHabTxt)}</span></div>
    <div class="ddb-prof-bloque"><b>Hit Dice</b><span>${esc(dgTxt)}</span></div>
    <div class="ddb-caja-pie">Proficiencies & Training</div>
  </div>`;
  const bloqueSkills = `<div class="ddb-caja">
    <div class="ddb-skills-head"><span>Prof</span><span>Mod</span><span>Skill</span><span>Bonus</span></div>
    <div class="ddb-skills-list">${skillsHtml}</div>
    <div class="ddb-caja-pie">Skills</div>
  </div>`;
  const bloqueDerecho = `<div class="ddb-col-der">
    <div class="ddb-combat-strip">
      <button type="button" class="ddb-widget" data-ddb-roll="iniciativa" data-ddb-quien="${esc(nombre)}" title="Tirar Iniciativa">
        <span class="ddb-widget-lbl">Initiative</span>
        <span class="ddb-widget-val">${signo(ini)}</span>
        <span class="ddb-widget-lbl">Roll 1d20</span>
      </button>
      <div class="ddb-ac-shield" title="Clase de Armadura (Armor Class)">
        <span class="ddb-widget-lbl">Armor</span>
        <span class="ddb-widget-val">${esc(ca)}</span>
        <span class="ddb-widget-lbl">Class</span>
      </div>
      <div class="ddb-widget" style="flex:1 1 130px;text-align:left">
        <span class="ddb-widget-lbl">Defenses</span>
        <span style="font-size:0.72rem;color:var(--ddb-sub)">${esc(defensasTxt)}</span>
      </div>
      <div class="ddb-widget" style="flex:1 1 130px;text-align:left">
        <span class="ddb-widget-lbl">Conditions</span>
        <span style="font-size:0.72rem;color:var(--ddb-sub)">${esc(condsTxt)}</span>
      </div>
    </div>
    <div class="ddb-caja">
      <nav class="ddb-tabs-nav" aria-label="Secciones de la ficha">
        ${[["actions", "Actions"], ["spells", "Spells"], ["inventory", "Inventory"], ["features", "Features & Traits"], ["notes", "Background & Notes"]].map(([id, t]) => `<button type="button" class="${tabActual === id ? "activo" : ""}" data-ddb-tab="${id}" data-ddb-quien="${esc(nombre)}">${t}</button>`).join("")}
      </nav>
      <div>${contenidoTab}</div>
    </div>
  </div>`;

  return `
  <article class="ddb-hoja${completa ? " completa" : ""}" style="--color:${colorSeguro(p.color, "#1b9af7")}">
    <header class="ddb-banner">
      <div class="ddb-identidad">
        <div class="ddb-avatar">${esc(nombre.charAt(0).toUpperCase())}</div>
        <div>
          <h3>${esc(nombre)}</h3>
          <p>${esc([p.especie, p.rol || p.clase || "Aventurero", `Level ${c.nivel}`].filter(Boolean).join(" · "))}</p>
        </div>
      </div>
      <div class="ddb-banner-botones">
        <button type="button" class="ddb-btn-top" data-ddb-accion="descanso" data-ddb-clase="corto" data-ddb-quien="${esc(nombre)}" title="Descanso corto (1 hora; gasta Dado de Golpe si está herido y recarga habilidades de descanso corto)"><span class="ico">🔥</span> Short Rest</button>
        <button type="button" class="ddb-btn-top" data-ddb-accion="descanso" data-ddb-clase="largo" data-ddb-quien="${esc(nombre)}" title="Descanso largo (8 horas; restaura toda la vida, Dados de Golpe, conjuros y −1 Agotamiento)"><span class="ico">🌙</span> Long Rest</button>
        <button type="button" class="ddb-btn-top" data-ddb-abrir-tiradas="${esc(nombre)}" title="Abrir lanzador de dados">🎲 Roll</button>
        ${completa
          ? `<button type="button" class="ddb-btn-top" data-ddb-cerrar-modal="si">✕ Cerrar</button>`
          : `<button type="button" class="ddb-btn-top" data-ddb-expandir="${esc(nombre)}" title="Abrir hoja de personaje en vista completa de 3 columnas como D&D Beyond">⛶ Vista completa</button>`}
      </div>
    </header>
    <div class="ddb-cuerpo">
      <div class="ddb-fila-top">
        <div class="ddb-atributos">${escudosStats}</div>
        <div class="ddb-top-widgets">
          <div class="ddb-widget">
            <span class="ddb-widget-lbl">Proficiency</span>
            <span class="ddb-widget-val">${signo(c.bonoComp)}</span>
            <span class="ddb-widget-lbl">Bonus</span>
          </div>
          <div class="ddb-widget">
            <span class="ddb-widget-lbl">Walking</span>
            <span class="ddb-widget-val">${velPies}<small> ft.</small></span>
            <span class="ddb-widget-lbl">${cifra(velMetros)} m · Speed</span>
          </div>
          <button type="button" class="ddb-widget" data-ddb-accion="inspiracion" data-ddb-quien="${esc(nombre)}" title="Alternar Inspiración Heroica">
            <span class="ddb-widget-lbl">Heroic</span>
            <span class="ddb-widget-val">${p.inspiracion ? "★" : "☆"}</span>
            <span class="ddb-widget-lbl">Inspiration</span>
          </button>
          <div class="ddb-hp-box">
            <div class="ddb-hp-controles">
              <button type="button" class="heal" data-ddb-hp="heal" data-ddb-quien="${esc(nombre)}">Heal</button>
              <input type="number" min="1" max="999" value="1" aria-label="Cantidad de PG" data-ddb-hp-input="${esc(nombre)}">
              <button type="button" class="dmg" data-ddb-hp="dmg" data-ddb-quien="${esc(nombre)}">Damage</button>
            </div>
            <div>
              <div class="ddb-hp-nums">
                <div><span class="lbl">Current</span><span class="big">${esc(p.vida)}</span></div>
                <div><span class="lbl">&nbsp;</span><span class="big">/</span></div>
                <div><span class="lbl">Max</span><span class="big">${esc(p.vida_max)}</span></div>
                <div><span class="lbl">Temp</span><span class="big">${p.vida_temporal ? esc(p.vida_temporal) : "--"}</span></div>
              </div>
              <div class="ddb-hp-title">Hit Points</div>
            </div>
          </div>
        </div>
      </div>
      ${completa ? `
        <div class="ddb-columnas">
          <div class="ddb-col-izq">${bloqueSaves}${bloqueSenses}${bloqueProfs}</div>
          <div class="ddb-col-med">${bloqueSkills}</div>
          ${bloqueDerecho}
        </div>
      ` : `
        ${bloqueDerecho}
        ${bloqueSaves}
        ${bloqueSenses}
        <details class="ddb-caja"><summary style="cursor:pointer;font-weight:800;font-size:0.75rem;text-transform:uppercase">Skills (18 habilidades) & Proficiencies</summary><div style="margin-top:8px;display:flex;flex-direction:column;gap:8px">${bloqueSkills}${bloqueProfs}</div></details>
      `}
    </div>
  </article>`;
}

function pintarEnemigos(lista) {
  if (!lista?.length) return "";
  const filas = lista.map((e) => {
    const verStats = Boolean(e.revelar_stats);
    const nombreVis = e.nombre;  // el servidor ya cambia el nombre real de un desconocido por su apariencia
    const [, estVis] = estadoVida(e);
    const rasgosVis = [e.raza || e.especie, e.altura, e.aspecto].filter(Boolean).join(" · ") || "Sin detalles visibles";
    const armaVis = (e.armas || []).map((a) => a.nombre).join(", ") || (e.dano ? "Armado" : "Sin arma visible");
    if (verStats) {
      return `<tr><td><b>${esc(nombreVis)}</b></td><td>${esc(e.vida)}/${esc(e.vida_max)}</td><td>CA ${esc(e.defensa)}</td><td>${esc(armaVis)} (${esc(e.dano || "-")})</td></tr>`;
    }
    return `<tr><td><b>${esc(nombreVis)}</b><br><small class="texto-3">${esc(rasgosVis)}</small></td><td>${esc(estVis)}</td><td>?</td><td>${esc(armaVis)}</td></tr>`;
  }).join("");
  return `<div class="enemigos"><h3>Figuras y amenazas en escena</h3><table><thead><tr><th>Qué ves</th><th>Estado aparente</th><th>Def.</th><th>Equipo visible</th></tr></thead><tbody>${filas}</tbody></table></div>`;
}

function construirCatalogoCharacters(d) {
  const pjs = d.personajes || [];
  const observador = app.jugador && pjs.some((p) => p.nombre === app.jugador) ? app.jugador : (pjs[0]?.nombre || "");
  const obsKey = sinTildes(observador);
  const posPorNombre = {};
  for (const pos of d.escena?.posiciones || []) {
    if (pos.quien) posPorNombre[sinTildes(pos.quien)] = pos;
  }
  const items = [];
  const vistos = new Set();

  for (const p of pjs) {
    const clave = sinTildes(p.nombre);
    vistos.add(clave);
    const esPropio = clave === obsKey;
    // Los PJ que juega una persona se ven enteros; los que lleva el narrador, por el lore (como un PNJ).
    const humano = p.piloto !== "narrador";
    const conocidoPorLista = Array.isArray(p.conocido_por) ? p.conocido_por.map(sinTildes).includes(obsKey) : true;
    const conocido = esPropio || humano || (p.conocido !== false && conocidoPorLista);
    const verStats = esPropio || humano || Boolean(p.revelar_stats);
    const pos = posPorNombre[clave];
    const equipoVis = (p.equipo || []).filter((x) => x.equipado || x.dano).map((x) => x.nombre).join(", ") || "Ropas sencillas";
    items.push({
      id: `pj:${p.nombre}`,
      claveReal: p.nombre,
      tipo: "pj",
      esPropio,
      conocido,
      verStats,
      ficha: p,
      color: p.color || "#1b9af7",
      nombreVisible: p.nombre,  // el servidor ya manda el nombre público de quien no es conocido
      subVisible: conocido
        ? [p.especie || p.raza || "Humano", verStats ? (p.rol || p.clase || `Nivel ${p.nivel ?? 1}`) : (p.altura || "Compañero conocido")].filter(Boolean).join(" · ")
        : [p.raza || p.especie || "Raza aparente desconocida", p.altura || "Estatura media"].filter(Boolean).join(" · "),
      badge: esPropio ? ["player", "Player · Tú"] : !humano ? ["npc", "Lo lleva el narrador"] : (conocido ? ["party", "Conocido"] : ["unknown", "Unknown"]),
      raza: p.especie || p.raza || "Humano",
      altura: p.altura || "Estatura media (~1,75 m)",
      aspecto: p.aspecto || "Viste equipo de aventurero.",
      equipoVisible: equipoVis,
      estadoAparente: estadoVida(p)[1],
      posicion: pos ? `${pos.celda ? `Casilla ${pos.celda} · ` : ""}${pos.donde || ""}` : "En la escena",
      notasLore: conocido ? (p.bueno_para || p.rol || "") : "",
    });
  }

  for (const e of d.enemigos || []) {
    const clave = sinTildes(e.nombre);
    vistos.add(clave);
    const conocido = Boolean(e.conocido);
    const verStats = Boolean(e.revelar_stats);
    const pos = posPorNombre[clave];
    const armasVis = (e.armas || []).map((a) => a.nombre).join(", ") || (e.equipo_visible) || (e.dano ? "Arma empuñada a la vista" : "Sin armas visibles a simple vista");
    items.push({
      id: `ene:${e.nombre}`,
      claveReal: e.nombre,
      tipo: "enemigo",
      esPropio: false,
      conocido,
      verStats,
      ficha: e,
      color: "#dc2626",
      nombreVisible: e.nombre,
      subVisible: [e.raza || e.especie || "Humanoide", e.altura || "Estatura media"].filter(Boolean).join(" · "),
      badge: conocido ? ["npc", "Conocido"] : ["unknown", "Unknown"],
      raza: e.raza || e.especie || "Humanoide",
      altura: e.altura || "Estatura media",
      aspecto: e.aspecto || "Figura presente en la zona; solo distingues su silueta, postura y lo que lleva a simple vista.",
      equipoVisible: armasVis,
      estadoAparente: estadoVida(e)[1],
      posicion: pos ? `${pos.celda ? `Casilla ${pos.celda} · ` : ""}${pos.donde || ""}` : "En la escena",
      notasLore: conocido ? (e.nota || e.rol || "Identidad conocida por el grupo.") : "",
    });
  }

  for (const n of d.pnj || []) {
    const clave = sinTildes(n.nombre);
    if (vistos.has(clave)) continue;
    vistos.add(clave);
    const conocido = n.conocido !== false;
    const pos = posPorNombre[clave];
    items.push({
      id: `pnj:${n.nombre}`,
      claveReal: n.nombre,
      tipo: "pnj",
      esPropio: false,
      conocido,
      verStats: false,
      ficha: n,
      color: "#d97706",
      nombreVisible: n.nombre,
      subVisible: conocido
        ? [n.raza || n.especie || "", n.rol || `Actitud ${n.actitud || "indiferente"}`].filter(Boolean).join(" · ")
        : [n.raza || n.especie || "Humanoide", n.altura || "Estatura media"].filter(Boolean).join(" · "),
      badge: conocido ? ["npc", "NPC"] : ["unknown", "Unknown"],
      raza: n.raza || n.especie || "Humano",
      altura: n.altura || "Estatura media",
      aspecto: n.aspecto || n.estado || "Lo que recuerdas o ves de su apariencia física a simple vista.",
      equipoVisible: n.equipo_visible || "Ropas acordes a su oficio",
      estadoAparente: n.estado || "Presente",
      posicion: pos ? `${pos.celda ? `Casilla ${pos.celda} · ` : ""}${pos.donde || ""}` : (n.estado || "Conocido en el mundo"),
      notasLore: conocido ? (n.notas || []).join(" · ") : "",
    });
  }

  for (const pos of d.escena?.posiciones || []) {
    const clave = sinTildes(pos.quien);
    if (!clave || vistos.has(clave)) continue;
    vistos.add(clave);
    const conocido = Boolean(pos.conocido);
    items.push({
      id: `pos:${pos.quien}`,
      claveReal: pos.quien,
      tipo: "figura",
      esPropio: false,
      conocido,
      verStats: false,
      ficha: pos,
      color: "#64748b",
      nombreVisible: conocido ? pos.quien : (pos.apariencia_publica || "Persona desconocida"),
      subVisible: [pos.raza || "Raza aparente desconocida", pos.altura || "En el grid"].filter(Boolean).join(" · "),
      badge: conocido ? ["npc", "NPC"] : ["unknown", "Unknown"],
      raza: pos.raza || "Por identificar a simple vista",
      altura: pos.altura || "No determinada desde esta distancia",
      aspecto: pos.aspecto || pos.donde || "Figura avistada en la cuadrícula táctica.",
      equipoVisible: pos.equipo_visible || "No se distingue con claridad",
      estadoAparente: "Avistado en escena",
      posicion: `${pos.celda ? `Casilla ${pos.celda} · ` : ""}${pos.donde || ""}`,
      notasLore: "",
    });
  }

  return items;
}

function pintarTarjetaObservacion(item) {
  const inicial = item.conocido ? esc(item.nombreVisible.charAt(0).toUpperCase()) : "?";
  const observador = app.jugador || (app.datos?.personajes || [])[0]?.nombre || "";
  return `
  <article class="ff-observacion-card">
    <div class="ff-side-header">
      <div class="ff-char-mini-avatar${item.conocido ? "" : " desconocido"}" style="width:48px;height:48px;font-size:1.3rem;--c:${colorSeguro(item.color, "#475569")}">${inicial}</div>
      <div style="flex:1;min-width:0">
        <h3 style="margin:0;font-size:1.12rem;color:#f3eee3">${esc(item.nombreVisible)}</h3>
        <p style="margin:2px 0 0;font-size:0.8rem;color:#9ca7b4">${esc(item.subVisible)}</p>
      </div>
      <span class="ff-char-badge ${item.badge[0]}">${esc(item.badge[1])}</span>
    </div>

    <div class="ff-obs-aviso">
      ${item.conocido
        ? "Conoces quién es según el lore, pero sus estadísticas internas no son públicas: solo ves lo que percibes con tus ojos y lo que sabes por la historia."
        : "👁️ <b>Persona desconocida según el lore:</b> no conoces su nombre, clase, nivel ni estadísticas. Solo puedes ver las características físicas observables con tus ojos."}
    </div>

    <div class="ff-obs-grid">
      <div class="ff-obs-item"><span class="lbl">Raza / Especie visible</span><span class="val">${esc(item.raza)}</span></div>
      <div class="ff-obs-item"><span class="lbl">Altura / Complexión</span><span class="val">${esc(item.altura)}</span></div>
      <div class="ff-obs-item"><span class="lbl">Estado físico a la vista</span><span class="val">${esc(item.estadoAparente)}</span></div>
      <div class="ff-obs-item"><span class="lbl">Posición en la escena</span><span class="val">${esc(item.posicion)}</span></div>
    </div>

    <div class="ff-obs-item">
      <span class="lbl">Apariencia física (lo que ves con tus ojos)</span>
      <span class="val" style="font-weight:500;line-height:1.45;margin-top:4px">${esc(item.aspecto)}</span>
    </div>

    <div class="ff-obs-item">
      <span class="lbl">Vestimenta y armas visibles</span>
      <span class="val" style="font-weight:500;margin-top:4px">${esc(item.equipoVisible)}</span>
    </div>

    ${item.conocido && item.notasLore ? `
    <div class="ff-obs-item">
      <span class="lbl">Lo que sabes por el lore</span>
      <span class="val" style="font-weight:500;line-height:1.45;margin-top:4px">${esc(item.notasLore)}</span>
    </div>` : ""}

    <div class="ff-side-acciones-principales">
      <button type="button" class="ff-btn-accion oro" data-ddb-roll="prueba" data-ddb-quien="${esc(observador)}" data-ddb-attr="percepcion" title="Tirar Percepción para notar más detalles físicos">👁️ Tirar Percepción</button>
      <button type="button" class="ff-btn-accion" data-obs-preguntar="${esc(item.nombreVisible)}" data-obs-pos="${esc(item.posicion)}">💬 Preguntar al GM qué veo</button>
    </div>
  </article>`;
}

function pintarFichaLateral(p, d) {
  const c = calcDatosDdb(p, d);
  const nombre = p.nombre || "Personaje";
  const velMetros = Number(p.velocidad ?? 9);
  const velPies = Math.round((velMetros / 1.5) * 5);
  // La CA guardada ya incluye lo equipado (equipar la mueve en el servidor): es la que usa el motor.
  const caTotal = Number(p.ca ?? p.defensa ?? 12);
  const pct = p.vida_max ? Math.max(0, Math.min(100, (100 * p.vida) / p.vida_max)) : 0;

  const stats6 = ORDEN_6_STATS.map(([k, , abbr]) => `
    <button type="button" class="ff-stat-box clicable" data-ddb-roll="prueba" data-ddb-quien="${esc(nombre)}" data-ddb-attr="${k}" title="Tirar prueba de ${esc(ATRIBUTOS[k] || abbr)}">
      <span class="lbl">${abbr}</span>
      <span class="val">${c.punt(k)}</span>
      <span class="pill">${signo(c.mod(k))}</span>
    </button>`).join("");

  const equipados = (p.equipo || []).filter((x) => x.equipado || x.dano);
  const listaMini = (equipados.length ? equipados : (p.equipo || [])).slice(0, 6);
  const equipHtml = listaMini.map((x) => `
    <div class="ff-equip-mini" data-ddb-abrir-modal="${esc(nombre)}" data-ddb-modal-tab="inventory" title="Ver en Inventario">
      ${svgArteItem(x)}
      <b>${esc(x.nombre)}</b>
      <small>${esc(x.dano ? `${x.dano} ${x.tipo_dano || ""}` : x.bono_ca ? `+${x.bono_ca} AC` : x.efecto || "Equipado")}</small>
    </div>`).join("");

  return `
  <article class="ff-sidebar-card" style="--color:${colorSeguro(p.color, "#1b9af7")}">
    <div class="ff-side-header">
      <div class="ff-side-avatar">${esc(nombre.charAt(0).toUpperCase())}</div>
      <div style="flex:1;min-width:0">
        <h3>${esc(nombre)}</h3>
        <p>${esc([`Level ${c.nivel}`, p.especie, p.rol || p.clase || "Aventurero"].filter(Boolean).join(" · "))}</p>
      </div>
    </div>

    <div class="ff-side-bar">
      <div class="ff-side-bar-top">
        <span>♥ HP: ${esc(p.vida)}/${esc(p.vida_max)}${p.vida_temporal ? ` (+${esc(p.vida_temporal)} temp)` : ""}</span>
        <span>
          <button type="button" class="mini" data-ddb-accion="descanso" data-ddb-clase="corto" data-ddb-quien="${esc(nombre)}" title="Short Rest">🔥 Short</button>
          <button type="button" class="mini" data-ddb-accion="descanso" data-ddb-clase="largo" data-ddb-quien="${esc(nombre)}" title="Long Rest">🌙 Long</button>
        </span>
      </div>
      <div class="ff-side-pista"><div class="ff-side-relleno" style="width:${pct}%"></div></div>
    </div>

    <div class="ff-side-acciones-principales">
      <button type="button" class="ff-btn-accion oro" data-ddb-abrir-modal="${esc(nombre)}" data-ddb-modal-tab="sheet">📋 Character Sheet</button>
      <button type="button" class="ff-btn-accion" data-ddb-abrir-modal="${esc(nombre)}" data-ddb-modal-tab="inventory">🎒 Inventory (${(p.equipo || []).length})</button>
    </div>

    <div>
      <p class="ff-sec-titulo"><span>Stats (clic para tirar)</span> <button type="button" class="mini" data-ddb-roll="iniciativa" data-ddb-quien="${esc(nombre)}">⚡ Init ${signo(c.mod("destreza"))}</button></p>
      <div class="ff-stats-top" style="margin-top:6px">
        <div class="ff-stat-box"><span class="lbl">AC</span><span class="val" style="color:#34d399">${caTotal}</span></div>
        <div class="ff-stat-box"><span class="lbl">Speed</span><span class="val">${velPies}ft</span></div>
        <div class="ff-stat-box"><span class="lbl">PB</span><span class="val">${signo(c.bonoComp)}</span></div>
      </div>
      <div class="ff-stats-top" style="margin-top:8px">${stats6}</div>
    </div>

    <div>
      <p class="ff-sec-titulo"><span>Equipment</span></p>
      <div class="ff-equip-mini-grid" style="margin-top:6px">${equipHtml || '<p class="texto-3">Sin objetos</p>'}</div>
      <button type="button" class="ff-btn-accion" style="width:100%;margin-top:10px" data-ddb-abrir-modal="${esc(nombre)}" data-ddb-modal-tab="inventory">🎒 View Full Inventory</button>
    </div>
  </article>`;
}

function pintarVistaInventario(p, d) {
  const c = calcDatosDdb(p, d);
  const nombre = p.nombre || "Personaje";
  const equipo = p.equipo || [];
  const porRanura = {};
  for (const it of equipo) {
    const r = inferirRanuraItem(it);
    if (it.equipado && r && !porRanura[r]) porRanura[r] = it;
  }
  const paperdollHtml = RANURAS_PAPERDOLL.map((slot) => {
    if (!slot) return '<div class="ff-slot vacio-grid"></div>';
    const [idSlot, etiquetaSlot] = slot;
    const item = porRanura[idSlot];
    if (!item) return `<div class="ff-slot" title="Ranura vacía: ${esc(etiquetaSlot)}">${esc(etiquetaSlot)}</div>`;
    return `<button type="button" class="ff-slot ocupado" data-inv-equipar="${esc(item.nombre)}" data-ddb-quien="${esc(nombre)}" title="${esc(item.nombre)} (${esc(etiquetaSlot)}) — clic para desequipar">
      ${svgArteItem(item)}
      <span class="slot-nombre">${esc(item.nombre)}</span>
    </button>`;
  }).join("");

  // Las monedas de la campaña (las fija el servidor según la ambientación); sin dinero inventado.
  const tiposMoneda = d.ambientacion?.monedas?.length ? d.ambientacion.monedas : Object.keys(p.monedas || {}).length ? Object.keys(p.monedas) : ["dinero"];
  const mon = p.monedas || {};
  const caTotal = Number(p.ca ?? p.defensa ?? 12);  // ya incluye lo equipado: la misma que usa el motor
  const bonoCaEquip = equipo.filter((x) => x.equipado && x.bono_ca).reduce((s, x) => s + Number(x.bono_ca || 0), 0);
  const velPies = Math.round((Number(p.velocidad ?? 9) / 1.5) * 5);
  const pesoTotal = Math.round(equipo.reduce((s, x) => s + Number(x.peso ?? 1) * Number(x.cantidad ?? 1), 0) * 10) / 10;
  const capMax = c.punt("fuerza") * 15;
  const pctCarga = capMax ? Math.min(100, (100 * pesoTotal) / capMax) : 0;

  const q = sinTildes(filtroInvTexto);
  const filtrados = equipo.filter((x) => {
    if (filtroInvCategoria !== "all" && inferirCategoriaItem(x) !== filtroInvCategoria) return false;
    if (q && !sinTildes(`${x.nombre} ${x.texto || ""} ${x.tipo_dano || ""}`).includes(q)) return false;
    return true;
  });

  const tarjetasHtml = filtrados.map((x) => {
    const peso = Number(x.peso ?? (x.dano ? 3.0 : 1.0)).toFixed(2);
    const valor = Number(x.valor ?? (x.dano ? 15 : 5));
    const cant = Number(x.cantidad ?? 1);
    const eq = Boolean(x.equipado);
    return `
    <article class="ff-item-card${eq ? " equipado" : ""}">
      <div class="ff-card-head">
        <span class="ff-card-title" title="${esc(x.nombre)}">${esc(x.nombre)}</span>
        <span class="ff-card-qty">${cant}</span>
      </div>
      <div class="ff-card-art">
        ${svgArteItem(x)}
      </div>
      ${eq ? '<div class="ff-ribbon-equipped">Equipped</div>' : ""}
      <div class="ff-card-foot">
        <span>⚖️ ${peso} lb.</span>
        <span>🪙 ${valor}</span>
      </div>
      <div class="ff-card-actions">
        <button type="button" data-inv-equipar="${esc(x.nombre)}" data-ddb-quien="${esc(nombre)}">${eq ? "Unequip" : "Equip"}</button>
        ${x.consumible ? `<button type="button" data-inv-usar="${esc(x.nombre)}" data-ddb-quien="${esc(nombre)}">Use</button>` : ""}
        <button type="button" data-inv-quitar="${esc(x.nombre)}" data-ddb-quien="${esc(nombre)}" title="Descartar objeto" style="flex:0 0 auto">✕</button>
      </div>
    </article>`;
  }).join("");

  return `
    <div class="ff-inv-top">
      <div class="ff-panel-box">
        <h3>Equipped Items</h3>
        <div class="ff-paperdoll">${paperdollHtml}</div>
      </div>
      <div class="ff-inv-der">
        <div class="ff-panel-box">
          <h3>Currency</h3>
          <div class="ff-currency-row">
            ${tiposMoneda.map((k) => `<label class="ff-currency-item">
              <input type="number" min="0" value="${esc(mon[k] ?? 0)}" data-inv-moneda="${esc(k)}" data-ddb-quien="${esc(nombre)}">
              <span>${esc(k.charAt(0).toUpperCase() + k.slice(1))}</span>
            </label>`).join("")}
          </div>
        </div>
        <div class="ff-panel-box">
          <h3>Stats</h3>
          <div class="ff-inv-stats-grid">
            <div class="ff-inv-stat-cell"><span class="lbl">Strength</span><span class="val">${c.punt("fuerza")}</span></div>
            <div class="ff-inv-stat-cell"><span class="lbl">Dexterity</span><span class="val">${c.punt("destreza")}</span></div>
            <div class="ff-inv-stat-cell"><span class="lbl">Constitution</span><span class="val">${c.punt("constitucion")}</span></div>
            <div class="ff-inv-stat-cell"><span class="lbl">Intelligence</span><span class="val">${c.punt("inteligencia")}</span></div>
            <div class="ff-inv-stat-cell"><span class="lbl">Wisdom</span><span class="val">${c.punt("sabiduria")}</span></div>
            <div class="ff-inv-stat-cell"><span class="lbl">Charisma</span><span class="val">${c.punt("carisma")}</span></div>
            <div class="ff-inv-stat-cell">
              ${bonoCaEquip ? `<span class="ac-bonus" title="Incluye el bono de lo equipado">+${bonoCaEquip}</span>` : ""}
              <span class="lbl">Armor Class</span>
              <span class="val">${caTotal}</span>
            </div>
            <div class="ff-inv-stat-cell"><span class="lbl">Max HP</span><span class="val">${esc(p.vida_max)}</span></div>
            <div class="ff-inv-stat-cell"><span class="lbl">Speed</span><span class="val">${velPies}</span></div>
          </div>
        </div>
        <div class="ff-panel-box">
          <h3>Carrying Capacity</h3>
          <p style="margin:0;font-size:0.84rem;color:#cbd5e1">${pesoTotal} / ${capMax} lbs.</p>
          <div class="ff-carry-bar"><div class="ff-carry-fill" style="width:${pctCarga}%"></div></div>
        </div>
      </div>
    </div>

    <div class="ff-inv-filtros">
      ${[["all", "⊞ All"], ["weapon", "🗡️ Weapons"], ["armor", "🛡️ Armor"], ["gear", "🎒 Gear"]].map(([id, lbl]) => `<button type="button" class="${filtroInvCategoria === id ? "activo" : ""}" data-inv-cat="${id}">${lbl}</button>`).join("")}
    </div>

    <div class="ff-inv-barra">
      <div class="ff-inv-search">
        <span>⌕</span>
        <input type="search" id="inv-buscar-input" value="${esc(filtroInvTexto)}" placeholder="Search...">
      </div>
      <button type="button" class="ff-btn-accion oro" data-inv-toggle-add="si">⊕ Add Item</button>
    </div>

    ${mostrarFormNuevoItem ? `
    <div class="ff-add-item-form">
      <label>Nombre
        <input type="text" id="nuevo-item-nombre" placeholder="Ej.: Escudo de roble, Poción…">
      </label>
      <label>Categoría
        <select id="nuevo-item-cat">
          <option value="weapon">Weapon (Arma)</option>
          <option value="armor">Armor (Armadura/Escudo)</option>
          <option value="gear" selected>Gear (Equipo/Consumible)</option>
        </select>
      </label>
      <label>Ranura (Slot)
        <select id="nuevo-item-ranura">
          <option value="">Mochila (sin ranura)</option>
          <option value="main_hand">Main Hand (Arma)</option>
          <option value="off_hand">Off-Hand (Escudo/Mano izq.)</option>
          <option value="armor">Armor (Armadura)</option>
          <option value="chest">Torso (Ropa/Capa)</option>
          <option value="head">Head (Cabeza)</option>
          <option value="neck">Neck (Cuello)</option>
          <option value="gloves">Gloves (Guantes)</option>
          <option value="belt">Belt (Cinturón)</option>
          <option value="ring">Ring (Anillo)</option>
          <option value="legs">Trousers (Piernas)</option>
          <option value="boots">Boots (Botas)</option>
          <option value="ammo">Ammunition (Munición)</option>
        </select>
      </label>
      <label>Daño (si es arma)
        <input type="text" id="nuevo-item-dano" placeholder="Ej.: 1d8">
      </label>
      <label>Bono AC (si es armadura)
        <input type="number" id="nuevo-item-ca" placeholder="Ej.: 2">
      </label>
      <label>Peso (lb)
        <input type="number" id="nuevo-item-peso" step="0.5" value="2">
      </label>
      <label>Valor (monedas)
        <input type="number" id="nuevo-item-valor" value="10">
      </label>
      <button type="button" class="ff-btn-accion oro" data-inv-guardar-item="${esc(nombre)}">Guardar objeto</button>
    </div>` : ""}

    <div class="ff-cards-grid">${tarjetasHtml || '<p class="texto-3">No hay objetos en esta categoría.</p>'}</div>
    <p style="text-align:center;color:#64748b;font-size:0.78rem;margin:16px 0 0">You've reached the end</p>
  `;
}

function pintarModalPersonaje(p, d) {
  const c = calcDatosDdb(p, d);
  const nombre = p.nombre || "Personaje";
  const pjs = d.personajes || [];
  let cuerpoModal = "";
  if (tabModalPrincipal === "sheet") {
    cuerpoModal = pintarFicha(p, d, true);
  } else if (tabModalPrincipal === "inventory") {
    cuerpoModal = pintarVistaInventario(p, d);
  } else if (tabModalPrincipal === "progression") {
    const rasgos = (p.rasgos || []).map((r) => `<div class="ddb-prof-bloque"><b>${esc(r.nombre)}</b><span>${esc(r.texto)}</span></div>`).join("");
    const habs = (p.habilidades || []).map((h) => `<div class="ddb-prof-bloque"><b>${esc(h.nombre)} (${esc(h.recarga || "escena")})</b><span>${esc(h.texto)}</span></div>`).join("");
    cuerpoModal = `<div class="ff-panel-box"><h3>Level ${c.nivel} Progression & Features</h3>${habs}${rasgos || '<p class="texto-3">Sin rasgos adicionales.</p>'}</div>`;
  } else if (tabModalPrincipal === "relationships") {
    const pnjs = (d.pnj || []).map((n) => `<div class="ddb-prof-bloque"><b>${esc(n.nombre)} · ${esc(n.actitud || "indiferente")}</b><span>${esc((n.notas || []).join(" · ") || n.rol || "")}</span></div>`).join("");
    cuerpoModal = `<div class="ff-panel-box"><h3>Relationships (PNJ conocidos)</h3>${pnjs || '<p class="texto-3">Aún no han registrado PNJ en esta campaña.</p>'}</div>`;
  } else {
    const hechos = (d.memoria?.hechos || []).filter((h) => !h.archivado).map((h) => `<div class="ddb-prof-bloque"><b>${esc(h.id)} · ${esc(h.categoria)}</b><span>${esc(h.texto)}</span></div>`).join("");
    cuerpoModal = `<div class="ff-panel-box"><h3>Memories</h3><p>${esc(d.memoria?.hasta_ahora || "")}</p>${hechos || '<p class="texto-3">Sin recuerdos registrados todavía.</p>'}</div>`;
  }

  return `
  <div class="ff-modal-shell">
    <header class="ff-modal-top">
      ${pjs.length > 1 ? `<div class="ff-modal-pjs">${pjs.map((x) => `<button type="button" class="mini${x.nombre === nombre ? " activo" : ""}" data-ddb-cambiar-modal-pj="${esc(x.nombre)}">${esc(x.nombre)}</button>`).join("")}</div>` : ""}
      <h2>Level ${c.nivel} ${esc(p.especie || "Human")} ${esc(p.clase || p.rol || "Adventurer")} — ${esc(nombre)}</h2>
      <p class="bio">${esc(p.aspecto || p.personalidad || p.bueno_para || "")}</p>
      <button type="button" class="ff-modal-cerrar" data-ddb-cerrar-modal="si" title="Cerrar (Esc)">✕</button>
      <nav class="ff-modal-tabs">
        ${[
          ["sheet", "Character Sheet"],
          ["inventory", "Inventory"],
          ["progression", "Progression"],
          ["relationships", "Relationships"],
          ["memories", "Memories"],
        ].map(([id, lbl]) => `<button type="button" class="${tabModalPrincipal === id ? "activo" : ""}" data-ff-modal-tab="${id}">${lbl}</button>`).join("")}
      </nav>
    </header>
    <div class="ff-modal-body">${cuerpoModal}</div>
  </div>`;
}

// ¿Hay alguien escribiendo en un campo del modal? Entonces el sondeo no lo repinta (y no borra lo tecleado).
const editandoEnModal = () => {
  const foco = document.activeElement;
  return Boolean(foco && $("#contenido-ddb")?.contains(foco) && foco.matches("input, select, textarea"));
};

function pintarFichas(forzar = false) {
  const d = app.datos;
  const pjs = d.personajes || [];
  if (!pjs.length) {
    $("#fichas").innerHTML = '<p class="texto-3">Sin personajes.</p>';
    $("#enemigos").innerHTML = pintarEnemigos(d.enemigos);
    return;
  }
  const catalogo = construirCatalogoCharacters(d);
  const propio = catalogo.find((x) => x.esPropio) || catalogo[0];
  if (!pjActivoFicha || !catalogo.some((x) => x.id === pjActivoFicha)) {
    pjActivoFicha = propio.id;
  }
  const seleccionado = catalogo.find((x) => x.id === pjActivoFicha) || propio;

  const filasCharacters = catalogo.map((it) => {
    const ini = it.conocido ? esc(it.nombreVisible.charAt(0).toUpperCase()) : "?";
    return `<button type="button" class="ff-char-row${it.id === seleccionado.id ? " activo" : ""}" data-ddb-ver-pj="${esc(it.id)}">
      <span class="ff-char-row-izq">
        <span class="ff-char-mini-avatar${it.conocido ? "" : " desconocido"}" style="--c:${colorSeguro(it.color, "#475569")}">${ini}</span>
        <span class="ff-char-textos">
          <span class="ff-char-nombre">${esc(it.nombreVisible)}</span>
          <span class="ff-char-sub">${esc(it.subVisible)}</span>
        </span>
      </span>
      <span class="ff-char-badge ${it.badge[0]}">${esc(it.badge[1])}</span>
    </button>`;
  }).join("");

  const panelCharacters = `
    <section class="ff-characters-panel" aria-label="Personajes en la escena">
      <div class="ff-characters-head">
        <span>Characters (${catalogo.length})</span>
        <span class="texto-3" style="font-size:0.68rem;text-transform:none">Vista de: ${esc(propio.nombreVisible)}</span>
      </div>
      <div class="ff-characters-lista">${filasCharacters}</div>
    </section>`;

  const detalleHtml = seleccionado.verStats
    ? pintarFichaLateral(seleccionado.ficha, d)
    : pintarTarjetaObservacion(seleccionado);

  $("#fichas").innerHTML = panelCharacters + detalleHtml;
  $("#enemigos").innerHTML = pintarEnemigos(d.enemigos);
  if (modalDdbPj && !$("#modal-ddb")?.hidden && (forzar || !editandoEnModal())) {
    const itemModal = catalogo.find((x) => x.claveReal === modalDdbPj && x.verStats) || propio;
    if (itemModal && itemModal.verStats) {
      $("#contenido-ddb").innerHTML = pintarModalPersonaje(itemModal.ficha, d);
    } else {
      $("#modal-ddb").hidden = true;
      modalDdbPj = null;
    }
  }
}

async function manejarClickDdb(ev) {
  const verPj = ev.target.closest("[data-ddb-ver-pj]");
  if (verPj) {
    pjActivoFicha = verPj.dataset.ddbVerPj;
    pintarFichas();
    return;
  }
  const obsPreg = ev.target.closest("[data-obs-preguntar]");
  if (obsPreg) {
    const area = $("#mensaje");
    if (area) {
      app.modoOoc = true;
      area.value = `¿Qué detalles físicos veo a simple vista de ${obsPreg.dataset.obsPreguntar} (${obsPreg.dataset.obsPos})?`;
      pintarComposer();
      area.focus();
    }
    return;
  }
  const cambiarModalPj = ev.target.closest("[data-ddb-cambiar-modal-pj]");
  if (cambiarModalPj) {
    modalDdbPj = cambiarModalPj.dataset.ddbCambiarModalPj;
    pintarFichas();
    return;
  }
  const ffTab = ev.target.closest("[data-ff-modal-tab]");
  if (ffTab) {
    tabModalPrincipal = ffTab.dataset.ffModalTab;
    pintarFichas();
    return;
  }
  const abrirModal = ev.target.closest("[data-ddb-abrir-modal]");
  if (abrirModal) {
    modalDdbPj = abrirModal.dataset.ddbAbrirModal;
    tabModalPrincipal = abrirModal.dataset.ddbModalTab || "sheet";
    const modal = $("#modal-ddb");
    if (modal) {
      modal.hidden = false;
      pintarFichas();
    }
    return;
  }
  const invCat = ev.target.closest("[data-inv-cat]");
  if (invCat) {
    filtroInvCategoria = invCat.dataset.invCat;
    pintarFichas();
    return;
  }
  if (ev.target.closest("[data-inv-toggle-add]")) {
    mostrarFormNuevoItem = !mostrarFormNuevoItem;
    pintarFichas();
    return;
  }
  const tabBtn = ev.target.closest("[data-ddb-tab]");
  if (tabBtn) {
    tabDdbPorPj[tabBtn.dataset.ddbQuien] = tabBtn.dataset.ddbTab;
    pintarFichas();
    return;
  }
  const filtroBtn = ev.target.closest("[data-ddb-filtro]");
  if (filtroBtn) {
    filtroAccionPorPj[filtroBtn.dataset.ddbQuien] = filtroBtn.dataset.ddbFiltro;
    pintarFichas();
    return;
  }
  const expandir = ev.target.closest("[data-ddb-expandir]");
  if (expandir) {
    modalDdbPj = expandir.dataset.ddbExpandir;
    tabModalPrincipal = "sheet";
    const modal = $("#modal-ddb");
    if (modal) {
      modal.hidden = false;
      pintarFichas();
    }
    return;
  }
  if (ev.target.closest("[data-ddb-cerrar-modal]") || ev.target.id === "modal-ddb") {
    if ($("#modal-ddb")) $("#modal-ddb").hidden = true;
    modalDdbPj = null;
    return;
  }
  const abrirTir = ev.target.closest("[data-ddb-abrir-tiradas]");
  if (abrirTir) {
    if (app.anfitrion) app.jugador = abrirTir.dataset.ddbAbrirTiradas;  // un invitado tira solo con su PJ
    abrirModalTiradas();
    return;
  }
  if (!app.escritura) return;
  const tfBtn = ev.target.closest("[data-ddb-trasfondo]");
  if (tfBtn) {
    const caja = tfBtn.closest("[data-trasfondo-de]");
    const val = (k) => caja.querySelector(`[data-tf="${k}"]`)?.value.trim() || "";
    const sube = {};
    if (val("mas2")) sube[val("mas2")] = 2;
    if (val("mas1")) sube[val("mas1")] = (sube[val("mas1")] || 0) + 1;
    await enviarPost("/api/tirar", {
      accion: "trasfondo", quien: tfBtn.dataset.ddbTrasfondo, nombre: val("nombre"), historia: val("historia"), sube,
      baja: val("menos1") ? { [val("menos1")]: -1 } : {}, habilidades: val("habilidades").split(",").map((x) => x.trim()).filter(Boolean),
    });
    app.firmaEstado = "";
    await sondear();
    return;
  }
  const borrarPj = ev.target.closest("[data-ddb-borrar-pj]");
  if (borrarPj) {
    const quien = borrarPj.dataset.ddbBorrarPj;
    if (!confirm(`¿Borrar a ${quien} de la partida? Su ficha se elimina (lo jugado queda en la bitácora).`)) return;
    await enviarPost("/api/tirar", { accion: "borrar_pj", quien });
    if ($("#modal-ddb")) $("#modal-ddb").hidden = true;
    modalDdbPj = null;
    app.firmaEstado = "";
    await sondear();
    return;
  }
  const equiparBtn = ev.target.closest("[data-inv-equipar]");
  if (equiparBtn) {
    equiparBtn.disabled = true;
    try {
      await enviarPost("/api/tirar", { accion: "equipar", quien: equiparBtn.dataset.ddbQuien, nombre: equiparBtn.dataset.invEquipar });
      app.firmaEstado = "";
      await sondear();
    } finally {
      equiparBtn.disabled = false;
    }
    return;
  }
  const usarBtn = ev.target.closest("[data-inv-usar]");
  if (usarBtn) {
    usarBtn.disabled = true;
    try {
      await enviarPost("/api/tirar", { accion: "usar_item", quien: usarBtn.dataset.ddbQuien, nombre: usarBtn.dataset.invUsar });
      app.firmaEstado = "";
      await sondear();
    } finally {
      usarBtn.disabled = false;
    }
    return;
  }
  const quitarBtn = ev.target.closest("[data-inv-quitar]");
  if (quitarBtn) {
    quitarBtn.disabled = true;
    try {
      await enviarPost("/api/tirar", { accion: "quitar_item", quien: quitarBtn.dataset.ddbQuien, nombre: quitarBtn.dataset.invQuitar });
      app.firmaEstado = "";
      await sondear();
    } finally {
      quitarBtn.disabled = false;
    }
    return;
  }
  const guardarItemBtn = ev.target.closest("[data-inv-guardar-item]");
  if (guardarItemBtn) {
    const nombreObj = $("#nuevo-item-nombre")?.value.trim();
    if (!nombreObj) return;
    guardarItemBtn.disabled = true;
    try {
      await enviarPost("/api/tirar", {
        accion: "agregar_item",
        quien: guardarItemBtn.dataset.invGuardarItem,
        nombre: nombreObj,
        categoria: $("#nuevo-item-cat")?.value || "gear",
        ranura: $("#nuevo-item-ranura")?.value || "",
        dano: $("#nuevo-item-dano")?.value.trim() || undefined,
        bono_ca: $("#nuevo-item-ca")?.value ? Number($("#nuevo-item-ca").value) : undefined,
        peso: Number($("#nuevo-item-peso")?.value || 1),
        valor: Number($("#nuevo-item-valor")?.value || 5),
        equipado: Boolean($("#nuevo-item-ranura")?.value),
      });
      mostrarFormNuevoItem = false;
      app.firmaEstado = "";
      await sondear();
    } finally {
      guardarItemBtn.disabled = false;
    }
    return;
  }
  const rollBtn = ev.target.closest("[data-ddb-roll]");
  if (rollBtn) {
    const tipo = rollBtn.dataset.ddbRoll;
    const quien = rollBtn.dataset.ddbQuien;
    const cuerpo = { quien };
    if (tipo === "prueba" || tipo === "salvacion") {
      cuerpo.accion = "prueba";
      cuerpo.atributo = rollBtn.dataset.ddbAttr;
      cuerpo.salvacion = tipo === "salvacion";
    } else if (tipo === "iniciativa") {
      cuerpo.accion = "iniciativa";
    } else if (tipo === "ataque") {
      cuerpo.accion = "ataque";
      if (rollBtn.dataset.ddbArma) cuerpo.arma = rollBtn.dataset.ddbArma;
      if (rollBtn.dataset.ddbSubtipo) cuerpo.subtipo = rollBtn.dataset.ddbSubtipo;
      const objetivo = elegirObjetivo(quien);
      if (objetivo === null) return;  // el jugador canceló
      if (objetivo) cuerpo.objetivo = objetivo;
    } else if (tipo === "dano") {
      cuerpo.accion = "dano";
      if (rollBtn.dataset.ddbArma) cuerpo.arma = rollBtn.dataset.ddbArma;
    }
    rollBtn.disabled = true;
    try {
      await enviarPost("/api/tirar", cuerpo);
      if ($("#modal-ddb") && !$("#modal-ddb").hidden) {
        $("#modal-ddb").hidden = true;
        modalDdbPj = null;
      }
      app.firmaEstado = "";
      await sondear();
      $("#chat").scrollTop = $("#chat").scrollHeight;
    } finally {
      rollBtn.disabled = false;
    }
    return;
  }
  const accBtn = ev.target.closest("[data-ddb-accion]");
  if (accBtn) {
    accBtn.disabled = true;
    try {
      await enviarPost("/api/tirar", {
        accion: accBtn.dataset.ddbAccion,
        clase: accBtn.dataset.ddbClase,
        quien: accBtn.dataset.ddbQuien,
      });
      app.firmaEstado = "";
      await sondear();
    } finally {
      accBtn.disabled = false;
    }
    return;
  }
  const hpBtn = ev.target.closest("[data-ddb-hp]");
  if (hpBtn) {
    const quien = hpBtn.dataset.ddbQuien;
    const contenedor = hpBtn.closest(".ddb-hp-controles");
    const inp = contenedor?.querySelector("input");
    const cant = Math.max(1, Number(inp?.value || 1));
    const delta = hpBtn.dataset.ddbHp === "heal" ? cant : -cant;
    hpBtn.disabled = true;
    try {
      await enviarPost("/api/tirar", { accion: "vida", quien, delta });
      app.firmaEstado = "";
      await sondear();
    } finally {
      hpBtn.disabled = false;
    }
  }
}

// A quién ataca: el servidor no elige solo. Se pregunta con los nombres que ven los jugadores.
function elegirObjetivo(quien) {
  const enPie = (app.datos?.enemigos || [])
    .filter((e) => (e.estado_aparente ? !["fuera de combate", "muerto"].includes(e.estado_aparente) : Number(e.vida ?? 1) > 0))
    .map((e) => e.nombre);
  if (!enPie.length) return "";
  const respuesta = prompt(`¿A quién ataca ${quien}?\n${enPie.join(" · ")}`, enPie[0]);
  return respuesta === null ? null : respuesta.trim();
}

$("#fichas")?.addEventListener("click", (ev) => manejarClickDdb(ev).catch(mostrarError));
$("#modal-ddb")?.addEventListener("click", (ev) => manejarClickDdb(ev).catch(mostrarError));
$("#modal-ddb")?.addEventListener("input", (ev) => {
  if (ev.target.id === "inv-buscar-input") {
    filtroInvTexto = ev.target.value;
    pintarFichas(true);
    const inp = $("#inv-buscar-input");
    if (inp) {
      inp.focus();
      inp.setSelectionRange(inp.value.length, inp.value.length);
    }
  }
});
$("#modal-ddb")?.addEventListener("change", async (ev) => {
  const inp = ev.target.closest("input[data-inv-moneda]");
  if (!inp || !app.escritura) return;
  const quien = inp.dataset.ddbQuien;
  const campo = inp.dataset.invMoneda;
  try {
    await enviarPost("/api/tirar", { accion: "monedas", quien, [campo]: Number(inp.value || 0) });
  } catch (err) {
    mostrarError(err);
  }
  app.firmaEstado = "";
  await sondear();
});

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
  const firmaActual = JSON.stringify([PARAMETROS_ZONA().toString(), app.firmaZonaMapa]);
  if (!forzar && app.proyeccion && app.firmaZona === firmaActual && !app.zonaPendiente) {
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
  const catPorClave = {};
  for (const it of construirCatalogoCharacters(app.datos || {})) {
    catPorClave[sinTildes(it.claveReal)] = it;
  }
  for (const x of fichas) {
    const [c, f] = coordenada(x.celda);
    if (c == null || f == null) continue;
    const infoCat = catPorClave[sinTildes(x.quien)];
    const conocido = infoCat ? infoCat.conocido : true;
    const nombreVis = conocido ? x.quien : (infoCat?.nombreVisible || "Persona desconocida");
    const marcaVis = conocido ? x.marca : "?";
    const descVis = conocido ? (x.donde || "") : ([infoCat?.raza, infoCat?.altura, infoCat?.aspecto].filter(Boolean).join(" · ") || x.donde || "");
    const grupo = porCasilla[x.celda], i = grupo.indexOf(x), dx = (i - (grupo.length - 1) / 2) * 9;
    const relleno = x.clase === "personaje" ? colorSeguro(x.color, "var(--acento)") : x.clase === "amenaza" ? "var(--critico)" : "var(--texto-3)";
    svg += `<g class="ficha-zona ${x.clase}${x.quien === app.origenZona ? " origen" : ""}" data-quien="${esc(x.quien)}" data-c="${esc(x.celda)}" transform="translate(${c * T + T / 2 + dx} ${f * T + T / 2})" tabindex="0" role="button" aria-label="${esc(nombreVis)} en ${esc(x.celda)}"><circle r="12" fill="${relleno}"/><text y="5">${esc(marcaVis)}</text><title>${esc(nombreVis)} (${esc(x.celda)}): ${esc(descVis)}</title></g>`;
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
      const infoCat = catPorClave[sinTildes(x.quien)];
      const conocido = infoCat ? infoCat.conocido : true;
      const nombreVis = conocido ? x.quien : (infoCat?.nombreVisible || "Persona desconocida");
      const marcaVis = conocido ? x.marca : "?";
      const descVis = conocido ? (x.donde || "") : ([infoCat?.raza, infoCat?.altura, infoCat?.aspecto].filter(Boolean).join(" · ") || x.donde || "");
      const dist = origen && x !== origen && x.distancia_m != null ? ` · ${metros(x.distancia_m)}` : "";
      const fondo = x.clase === "personaje" ? colorSeguro(x.color, "var(--acento)") : x.clase === "amenaza" ? "var(--critico)" : "var(--texto-3)";
      return `<li><span class="marca-ficha" style="background:${fondo}">${esc(marcaVis)}</span><b>${esc(nombreVis)}</b> <span class="texto-3">${esc(x.celda)}${!conocido ? " · desconocido" : x.clase === "amenaza" ? " · amenaza" : ""}${dist}</span><br><span class="texto-2">${esc(descVis)}</span></li>`;
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

async function refrescarVisor() {
  const ruta = app.slug ? `/api/visor?p=${encodeURIComponent(app.slug)}` : "/api/visor";
  const visor = await api(ruta).catch(() => ({ escritura: false, token: null, chat: false, sala: false }));
  app.escritura = Boolean(visor.escritura && visor.token);
  app.token = visor.token;
  app.chatActivo = Boolean(visor.chat);
  app.autor = visor.autor;
  app.salaDisponible = Boolean(visor.sala);
  // Un servidor arrancado antes de los papeles no informa `anfitrion`: entonces vale lo de antes (quien escribe).
  app.anfitrion = Boolean(visor.anfitrion ?? visor.escritura);
  app.lectura = visor.lectura !== false;
  if (visor.pj) app.jugador = visor.pj;
  else if (!app.anfitrion && app.slug) app.reclamo = "";  // el reclamo guardado ya no vale (el servidor se reinició)
}

// Toda escritura del visor. El servidor exige el token de esta ejecución y, en la sala, el PJ reclamado.
async function enviarPost(ruta, cuerpo) {
  const enviar = () => fetch(`${ruta}?p=${encodeURIComponent(app.slug)}`, {
    method: "POST", cache: "no-store",
    headers: cabecerasSala({ "Content-Type": "application/json", "X-Mesa-Token": app.token || "" }),
    body: JSON.stringify(cuerpo),
  });
  let r = await enviar();
  let j = await r.json().catch(() => ({}));
  if (r.status === 403 && String(j.error || "").includes("token")) {
    await refrescarVisor();
    if (app.token) {
      r = await enviar();
      j = await r.json().catch(() => ({}));
    }
  }
  if (r.status === 403 && String(j.error || "").includes("elige tu personaje") && app.jugador && ruta !== "/api/reclamar" && await reclamarPj(app.jugador)) {
    r = await enviar();
    j = await r.json().catch(() => ({}));
  }
  if (!r.ok) throw new Error(j.error || `error ${r.status}`);
  return j;
}

// En la sala cada persona juega con un PJ: firma con su nombre y solo actúa con su ficha.
async function reclamarPj(nombre) {
  if (!nombre || !app.escritura) return false;
  try {
    const r = await enviarPost("/api/reclamar", { pj: nombre });
    app.reclamo = r.reclamo;
    app.jugador = r.pj;
    try { sessionStorage.setItem(`mesa-reclamo-${app.slug}`, r.reclamo); } catch { /* sin almacenamiento: dura lo que la pestaña */ }
    guardarLocal(`mesa-jugador-${app.slug}`, r.pj);
    return true;
  } catch (err) {
    mostrarError(err);
    return false;
  }
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
      location.reload();  // con la clave ya se puede leer la mesa entera: se carga de nuevo
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
    ev.target.dataset.opciones = "";  // vuelve a la elección anterior
    pintarComposer();
    return;
  }
  app.jugador = elegido;
  guardarLocal(`mesa-jugador-${app.slug}`, app.jugador);
  pjActivoFicha = `pj:${app.jugador}`;
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
  try { await enviarPost("/api/chat/sesion-nueva", {}); await sondear(); } catch (err) { $("#estado-narrador").textContent = `✕ ${err.message}`; }
});
$("#selector-agente")?.addEventListener("change", async (ev) => {
  try {
    await enviarPost("/api/chat/agente", { agente: ev.target.value });
    await sondear();
  } catch (err) {
    $("#estado-narrador").textContent = `✕ ${err.message}`;
    await sondear();
  }
});
const PRESETS_CAMPANA = {
  cripta: {
    titulo: "Cazadores de Ceniza",
    tono: "fantasía oscura, misterio, combate táctico, supervivencia",
    epoca: "Imperio caído tras la Noche de la Ceniza; magia prohibida y reliquias antiguas",
    lugar: "Las ruinas subterráneas bajo el Fuerte del Sello",
    personajes: "Kael (Guerrero), Lyra (Pícara)",
    idea: "Queremos una campaña de exploración de mazmorras y misterio oscuro. Nos contrataron para bajar a una cripta sellada hace siglos y recuperar un artefacto antes que una secta rival.",
  },
  intriga: {
    titulo: "Sombras de Corona",
    tono: "intriga política, robos, investigación, humor ácido",
    epoca: "Renacimiento mágico en una metrópoli mercantil dividida por gremios",
    lugar: "Posada El Grifo Dorado, distrito de los canales",
    personajes: "Vane (Bardo / Espía), Sera (Pícara / Daga)",
    idea: "Queremos golpes nocturnos, negociación con gremios peligrosos y traiciones. Empezamos recibiendo un encargo urgente en una taberna lluviosa a medianoche.",
  },
  piratas: {
    titulo: "Corsarios del Mar de Niebla",
    tono: "aventura, exploración naval, acción, camaradería",
    epoca: "Archipiélago de islas flotantes y arrecifes encantados",
    lugar: "Muelle de Puerto Tormenta, a bordo de una carabela dañada",
    personajes: "Darian (Guerrero corsario), Nami (Exploradora / Navegante)",
    idea: "Queremos navegar entre islas desconocidas, abordar barcos y buscar un tesoro legendario. Empezamos en el puerto defendiendo nuestro mapa de unos cazarrecompensas.",
  },
  isekai: {
    titulo: "Reencarnados en Aethermark",
    tono: "isekai, fantasía, aventura, comedia inteligente y momentos serios",
    epoca: "Era de los Contratos, año 847 del Reino de Aethermark",
    lugar: "Pueblo fronterizo de Valdris",
    personajes: "Cris (Mago / Estratega), Amigo (Guerrero / Vanguardia)",
    idea: "Despertamos juntos reencarnados en un mundo de fantasía donde la magia funciona por contratos y reglas que podemos aprovechar con nuestro ingenio del mundo moderno.",
  },
};

function abrirPanelCampana(modo = "nueva") {
  const panel = $("#panel-campana");
  if (!panel) return;
  panel.hidden = false;
  const radio = panel.querySelector(`input[name="campana-modo"][value="${modo}"]`);
  if (radio) radio.checked = true;
  if (modo === "configurar" && app.datos) {
    const amb = app.datos.ambientacion || {};
    $("#campana-titulo").value = app.datos.titulo || "";
    $("#campana-tono").value = (amb.tono || []).join(", ");
    $("#campana-epoca").value = amb.epoca || "";
    $("#campana-lugar").value = amb.lugar || "";
    $("#campana-personajes").value = "";  // solo se añaden PJ nuevos: los que ya existen no se tocan
  }
  $("#campana-titulo").focus();
}

$("#boton-campana")?.addEventListener("click", () => {
  const panel = $("#panel-campana");
  if (!panel) return;
  if (panel.hidden) abrirPanelCampana(app.chat.length === 0 ? "configurar" : "nueva");
  else panel.hidden = true;
});
$("#cerrar-campana")?.addEventListener("click", () => { $("#panel-campana").hidden = true; });
$("#panel-campana")?.addEventListener("click", (ev) => {
  const btn = ev.target.closest("button[data-preset]");
  if (!btn) return;
  const p = PRESETS_CAMPANA[btn.dataset.preset];
  if (!p) return;
  $("#campana-titulo").value = p.titulo;
  $("#campana-tono").value = p.tono;
  $("#campana-epoca").value = p.epoca;
  $("#campana-lugar").value = p.lugar;
  $("#campana-personajes").value = p.personajes;
  $("#campana-idea").value = p.idea;
});
$("#form-campana")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const aviso = $("#campana-aviso");
  const boton = ev.submitter;
  const iniciarChat = boton?.dataset?.iniciar !== "no";
  const modo = document.querySelector('input[name="campana-modo"]:checked')?.value || "nueva";
  aviso.dataset.tipo = "";
  aviso.textContent = "Guardando campaña y ambiente…";
  try {
    const r = await enviarPost("/api/campana", {
      modo,
      titulo: $("#campana-titulo").value.trim(),
      tono: $("#campana-tono").value.trim(),
      epoca: $("#campana-epoca").value.trim(),
      lugar: $("#campana-lugar").value.trim(),
      personajes: $("#campana-personajes").value.trim(),
      idea: $("#campana-idea").value.trim(),
      iniciar_chat: iniciarChat,
      autor: app.jugador || undefined,
    });
    $("#panel-campana").hidden = true;
    aviso.textContent = "";
    if (r.slug && r.slug !== app.slug) {
      const params = new URLSearchParams(location.search);
      params.set("p", r.slug);
      location.search = `?${params.toString()}`;
      return;
    }
    app.firmaEstado = "";
    await sondear();
  } catch (err) {
    aviso.dataset.tipo = "error";
    aviso.textContent = `✕ ${err.message}`;
  }
});

$("#chat").addEventListener("click", async (ev) => {
  const btnCampana = ev.target.closest("[data-abrir-campana]");
  if (btnCampana) {
    abrirPanelCampana(btnCampana.dataset.abrirCampana || "configurar");
    return;
  }
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

// ---------- modal de tiradas (estilo Friends & Fables) ----------
const CATALOGO_TIRADAS = [
  {
    seccion: "PRUEBAS DE CARACTERÍSTICA · ABILITY CHECKS",
    items: [
      { id: "chk-str", icono: "💪", titulo: "Fuerza", sub: "Strength Check", accion: "prueba", atributo: "fuerza", attrBase: "fuerza" },
      { id: "chk-dex", icono: "💨", titulo: "Destreza", sub: "Dexterity Check", accion: "prueba", atributo: "destreza", attrBase: "destreza" },
      { id: "chk-con", icono: "🛡️", titulo: "Constitución", sub: "Constitution Check", accion: "prueba", atributo: "constitucion", attrBase: "constitucion" },
      { id: "chk-int", icono: "🧠", titulo: "Inteligencia", sub: "Intelligence Check", accion: "prueba", atributo: "inteligencia", attrBase: "inteligencia" },
      { id: "chk-wis", icono: "🎓", titulo: "Sabiduría", sub: "Wisdom Check", accion: "prueba", atributo: "sabiduria", attrBase: "sabiduria" },
      { id: "chk-cha", icono: "⭐", titulo: "Carisma", sub: "Charisma Check", accion: "prueba", atributo: "carisma", attrBase: "carisma" },
    ],
  },
  {
    seccion: "HABILIDADES · SKILLS",
    items: [
      { id: "sk-acr", icono: "🤸", titulo: "Acrobacias", sub: "Acrobatics Check", accion: "prueba", atributo: "acrobacias", attrBase: "destreza" },
      { id: "sk-ani", icono: "🐾", titulo: "Trato con animales", sub: "Animal Handling Check", accion: "prueba", atributo: "trato con animales", attrBase: "sabiduria" },
      { id: "sk-arc", icono: "✨", titulo: "Arcanos", sub: "Arcana Check", accion: "prueba", atributo: "arcanos", attrBase: "inteligencia" },
      { id: "sk-ath", icono: "🏋️", titulo: "Atletismo", sub: "Athletics Check", accion: "prueba", atributo: "atletismo", attrBase: "fuerza" },
      { id: "sk-dec", icono: "🎭", titulo: "Engaño", sub: "Deception Check", accion: "prueba", atributo: "engano", attrBase: "carisma" },
      { id: "sk-his", icono: "📖", titulo: "Historia", sub: "History Check", accion: "prueba", atributo: "historia", attrBase: "inteligencia" },
      { id: "sk-ins", icono: "👁️", titulo: "Perspicacia", sub: "Insight Check", accion: "prueba", atributo: "perspicacia", attrBase: "sabiduria" },
      { id: "sk-int", icono: "⚡", titulo: "Intimidación", sub: "Intimidation Check", accion: "prueba", atributo: "intimidacion", attrBase: "carisma" },
      { id: "sk-inv", icono: "🔍", titulo: "Investigación", sub: "Investigation Check", accion: "prueba", atributo: "investigacion", attrBase: "inteligencia" },
      { id: "sk-med", icono: "➕", titulo: "Medicina", sub: "Medicine Check", accion: "prueba", atributo: "medicina", attrBase: "sabiduria" },
      { id: "sk-nat", icono: "🌿", titulo: "Naturaleza", sub: "Nature Check", accion: "prueba", atributo: "naturaleza", attrBase: "inteligencia" },
      { id: "sk-per", icono: "👁", titulo: "Percepción", sub: "Perception Check", accion: "prueba", atributo: "percepcion", attrBase: "sabiduria" },
      { id: "sk-prf", icono: "🎵", titulo: "Interpretación", sub: "Performance Check", accion: "prueba", atributo: "interpretacion", attrBase: "carisma" },
      { id: "sk-prs", icono: "💬", titulo: "Persuasión", sub: "Persuasion Check", accion: "prueba", atributo: "persuasion", attrBase: "carisma" },
      { id: "sk-rel", icono: "📜", titulo: "Religión", sub: "Religion Check", accion: "prueba", atributo: "religion", attrBase: "inteligencia" },
      { id: "sk-slt", icono: "🖐️", titulo: "Juego de manos", sub: "Sleight of Hand Check", accion: "prueba", atributo: "juego de manos", attrBase: "destreza" },
      { id: "sk-ste", icono: "🪶", titulo: "Sigilo", sub: "Stealth Check", accion: "prueba", atributo: "sigilo", attrBase: "destreza" },
      { id: "sk-sur", icono: "🧭", titulo: "Supervivencia", sub: "Survival Check", accion: "prueba", atributo: "supervivencia", attrBase: "sabiduria" },
    ],
  },
  {
    seccion: "COMBATE · COMBAT",
    items: [
      { id: "cb-ini", icono: "⚡", titulo: "Iniciativa", sub: "Initiative", accion: "iniciativa", attrBase: "destreza" },
      { id: "cb-atk", icono: "🎯", titulo: "Ataque", sub: "Attack", accion: "ataque", subtipo: "arma" },
      { id: "cb-mel", icono: "⚔️", titulo: "Ataque cuerpo a cuerpo", sub: "Melee Attack", accion: "ataque", subtipo: "cuerpo", attrBase: "fuerza" },
      { id: "cb-rng", icono: "🏹", titulo: "Ataque a distancia", sub: "Ranged Attack", accion: "ataque", subtipo: "distancia", attrBase: "destreza" },
      { id: "cb-spl", icono: "🪄", titulo: "Ataque de conjuro", sub: "Spell Attack", accion: "ataque", subtipo: "conjuro", attrBase: "inteligencia" },
      { id: "cb-dmg", icono: "🔥", titulo: "Daño", sub: "Damage", accion: "dano" },
      { id: "cb-hit", icono: "🎲", titulo: "Dados de Golpe", sub: "Hit Dice", accion: "dados_golpe" },
    ],
  },
  {
    seccion: "TIRADAS DE SALVACIÓN · SAVING THROWS",
    items: [
      { id: "sv-str", icono: "💪", titulo: "Salvación de Fuerza", sub: "Strength Save", accion: "prueba", atributo: "fuerza", attrBase: "fuerza", salvacion: true },
      { id: "sv-dex", icono: "💨", titulo: "Salvación de Destreza", sub: "Dexterity Save", accion: "prueba", atributo: "destreza", attrBase: "destreza", salvacion: true },
      { id: "sv-con", icono: "🛡️", titulo: "Salvación de Constitución", sub: "Constitution Save", accion: "prueba", atributo: "constitucion", attrBase: "constitucion", salvacion: true },
      { id: "sv-int", icono: "🧠", titulo: "Salvación de Inteligencia", sub: "Intelligence Save", accion: "prueba", atributo: "inteligencia", attrBase: "inteligencia", salvacion: true },
      { id: "sv-wis", icono: "🎓", titulo: "Salvación de Sabiduría", sub: "Wisdom Save", accion: "prueba", atributo: "sabiduria", attrBase: "sabiduria", salvacion: true },
      { id: "sv-cha", icono: "⭐", titulo: "Salvación de Carisma", sub: "Charisma Save", accion: "prueba", atributo: "carisma", attrBase: "carisma", salvacion: true },
      { id: "sv-dth", icono: "💀", titulo: "Salvación de Muerte", sub: "Death Save (1d20 vs 10)", accion: "salvacion_muerte" },
    ],
  },
];

let modoTiradaModal = "normal";

function modItemParaPj(pj, item) {
  if (!pj) return { texto: "", comp: false };
  const moderno = es2024(app.datos);
  const attrs = pj.atributos || {};
  const bonoComp = Number(pj.competencia_bono || (2 + Math.floor((Number(pj.nivel || 1) - 1) / 4)));
  const modDe = (attr) => {
    if (moderno) return Math.floor((Number(attrs[attr] ?? 10) - 10) / 2);
    const mapaLegacy = { fuerza: "fuerza", constitucion: "fuerza", destreza: "agilidad", inteligencia: "ingenio", sabiduria: "ingenio", carisma: "corazon" };
    return Number(attrs[mapaLegacy[attr] || attr] ?? 0);
  };
  if (item.accion === "dano") {
    const arma = (pj.equipo || []).find((a) => a.dano);
    if (!arma) return { texto: "—", comp: false };
    const sutil = (arma.propiedades || []).map(sinTildes).some((x) => x === "sutil" || x === "finesse");
    const mod = modDe(arma.distancia || (sutil && modDe("destreza") >= modDe("fuerza")) ? "destreza" : "fuerza");
    return { texto: `${arma.dano}${moderno && mod ? signo(mod) : ""}`, comp: false };
  }
  if (item.accion === "dados_golpe") {
    const dg = pj.dados_golpe?.dado || "1d8";
    return { texto: dg, comp: false };
  }
  if (item.accion === "salvacion_muerte") {
    return { texto: "d20", comp: false };
  }
  if (item.accion === "ataque") {
    const mod = modDe(item.attrBase || "fuerza") + (moderno ? bonoComp : 0);
    return { texto: signo(mod), comp: moderno };
  }
  const base = modDe(item.attrBase || "fuerza");
  if (!moderno) return { texto: signo(base), comp: false };
  const comp = pj.competencias || {};
  if (item.salvacion) {
    const tiene = (comp.salvaciones || []).map(sinTildes).includes(sinTildes(item.atributo));
    return { texto: signo(base + (tiene ? bonoComp : 0)), comp: tiene };
  }
  const claveHab = sinTildes(item.atributo);
  const pericia = (comp.pericia || comp.expertise || []).map(sinTildes).includes(claveHab);
  const habComp = (comp.habilidades || []).map(sinTildes).includes(claveHab);
  const extra = pericia ? bonoComp * 2 : habComp ? bonoComp : 0;
  return { texto: signo(base + extra), comp: pericia || habComp };
}

function pintarCatalogoTiradas() {
  const cont = $("#catalogo-tiradas");
  if (!cont) return;
  const filtro = sinTildes($("#buscar-tirada")?.value || "");
  const quienNombre = $("#tirada-quien")?.value || app.jugador;
  const pj = (app.datos?.personajes || []).find((p) => p.nombre === quienNombre) || (app.datos?.personajes || [])[0];
  const bloques = [];
  for (const sec of CATALOGO_TIRADAS) {
    const visibles = sec.items.filter((it) => !filtro || sinTildes(`${it.titulo} ${it.sub} ${it.atributo || ""}`).includes(filtro));
    if (!visibles.length) continue;
    const tarjetas = visibles.map((it) => {
      const m = modItemParaPj(pj, it);
      return `<button type="button" class="boton-tirada" data-tirada-id="${esc(it.id)}">
        <span class="boton-tirada-izq">
          <span class="boton-tirada-icono" aria-hidden="true">${it.icono}</span>
          <span class="boton-tirada-textos">
            <span class="boton-tirada-titulo">${esc(it.titulo)}</span>
            <span class="boton-tirada-sub">${esc(it.sub)}</span>
          </span>
        </span>
        ${m.texto ? `<span class="boton-tirada-mod${m.comp ? " comp" : ""}">${esc(m.texto)}</span>` : ""}
      </button>`;
    }).join("");
    bloques.push(`<section class="seccion-tiradas"><h3>${esc(sec.seccion)}</h3><div class="grilla-tiradas">${tarjetas}</div></section>`);
  }
  cont.innerHTML = bloques.join("") || '<p class="texto-3">No hay tiradas que coincidan con la búsqueda.</p>';
}

function abrirModalTiradas() {
  const modal = $("#modal-tiradas");
  if (!modal || !app.escritura) return;
  const todos = (app.datos?.personajes || []).map((p) => p.nombre).filter(Boolean);
  const pjs = app.anfitrion ? todos : todos.filter((n) => n === app.jugador);  // en la sala, solo el PJ propio
  const sel = $("#tirada-quien");
  if (sel) {
    const actual = app.jugador || pjs[0] || "";
    sel.innerHTML = pjs.map((n) => `<option value="${esc(n)}"${n === actual ? " selected" : ""}>${esc(n)}</option>`).join("");
    sel.disabled = !app.anfitrion;
  }
  if ($("#tirada-estado")) {
    $("#tirada-estado").hidden = pjs.length > 0;
    $("#tirada-estado").textContent = pjs.length ? "" : "Elige tu personaje («Juego como») antes de tirar.";
  }
  modal.hidden = false;
  pintarCatalogoTiradas();
  $("#buscar-tirada")?.focus();
}

function cerrarModalTiradas() {
  const modal = $("#modal-tiradas");
  if (modal) modal.hidden = true;
}

$("#abrir-tiradas")?.addEventListener("click", abrirModalTiradas);
$("#cerrar-tiradas")?.addEventListener("click", cerrarModalTiradas);
$("#modal-tiradas")?.addEventListener("click", (ev) => {
  if (ev.target.id === "modal-tiradas") cerrarModalTiradas();
});
$("#buscar-tirada")?.addEventListener("input", pintarCatalogoTiradas);
$("#tirada-quien")?.addEventListener("change", (ev) => {
  app.jugador = ev.target.value;
  guardarLocal(`mesa-jugador-${app.slug}`, app.jugador);
  if ($("#selector-jugador")) $("#selector-jugador").value = app.jugador;
  pintarCatalogoTiradas();
});
document.querySelectorAll("[data-modo-tirada]").forEach((btn) => {
  btn.addEventListener("click", () => {
    modoTiradaModal = btn.dataset.modoTirada;
    document.querySelectorAll("[data-modo-tirada]").forEach((b) => b.classList.toggle("activo", b === btn));
  });
});
document.addEventListener("keydown", (ev) => {
  const tiradasAbierto = Boolean($("#modal-tiradas") && !$("#modal-tiradas").hidden);
  const escribiendo = ev.target.closest?.("input, textarea, select, [contenteditable]");
  // Ctrl+K no le quita el atajo al navegador mientras se escribe ni a quien no puede tirar.
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k" && app.escritura && (tiradasAbierto || !escribiendo)) {
    ev.preventDefault();
    if (tiradasAbierto) cerrarModalTiradas();
    else abrirModalTiradas();
  } else if (ev.key === "Escape" && tiradasAbierto) {
    cerrarModalTiradas();
  } else if (ev.key === "Escape" && $("#modal-ddb") && !$("#modal-ddb").hidden) {
    $("#modal-ddb").hidden = true;
    modalDdbPj = null;
  }
});

$("#catalogo-tiradas")?.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button[data-tirada-id]");
  if (!btn) return;
  const item = CATALOGO_TIRADAS.flatMap((s) => s.items).find((x) => x.id === btn.dataset.tiradaId);
  if (!item) return;
  const estadoEl = $("#tirada-estado");
  if (estadoEl) {
    estadoEl.hidden = false;
    estadoEl.textContent = `Lanzando ${item.titulo}…`;
  }
  btn.disabled = true;
  try {
    const quien = $("#tirada-quien")?.value || app.jugador;
    const cdVal = $("#tirada-cd")?.value.trim();
    const objVal = $("#tirada-objetivo")?.value.trim();
    const narrar = Boolean($("#tirada-narrar")?.checked);
    const cuerpo = {
      accion: item.accion,
      quien,
      atributo: item.atributo,
      salvacion: Boolean(item.salvacion),
      subtipo: item.subtipo,
      modo: modoTiradaModal,
      cd: cdVal ? Number(cdVal) : undefined,
      objetivo: objVal || undefined,
      narrar,
    };
    await enviarPost("/api/tirar", cuerpo);
    cerrarModalTiradas();
    app.firmaEstado = "";
    await sondear();
    $("#chat").scrollTop = $("#chat").scrollHeight;
  } catch (err) {
    if (estadoEl) {
      estadoEl.hidden = false;
      estadoEl.textContent = `✕ ${err.message}`;
    }
  } finally {
    btn.disabled = false;
  }
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
    await refrescarVisor();
    if (app.salaDisponible && !app.lectura) {
      // Mesa privada: sin la clave no se lee nada; se pide en el compositor.
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
    if (!app.slug) { $("#nombre-historia").textContent = "No hay partidas"; return; }
    try { app.reclamo = sessionStorage.getItem(`mesa-reclamo-${app.slug}`) || ""; } catch { app.reclamo = ""; }
    await refrescarVisor();  // con la partida ya elegida: ¿sigue vigente el PJ reclamado?
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

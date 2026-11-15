// Núcleo del visor: estado compartido, helpers y el canal HTTP con el servidor local.
export const $ = (s) => document.querySelector(s);
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const signo = (n) => (n >= 0 ? `+${n}` : `${n}`);
export const leerLocal = (clave, defecto) => { try { return localStorage.getItem(clave) || defecto; } catch { return defecto; } };
export const guardarLocal = (clave, valor) => { try { localStorage.setItem(clave, valor); } catch { /* sin almacenamiento: no pasa nada */ } };
export const sinTildes = (s) => String(s ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
export const cifra = (n) => String(Math.round(Number(n) * 10) / 10).replace(".", ",");
export const metros = (n) => `${cifra(n)} m`;
export const colorSeguro = (c, defecto) => (/^#[0-9a-f]{3,8}$/i.test(String(c || "")) ? c : defecto);

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

export const app = {
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

export const ATRIBUTOS = {
  fuerza: "Fuerza", agilidad: "Agilidad", ingenio: "Ingenio", corazon: "Corazón",
  destreza: "Destreza", constitucion: "Constitución", inteligencia: "Inteligencia", sabiduria: "Sabiduría", carisma: "Carisma",
};
export const ABREVIATURA_2024 = { fuerza: "FUE", destreza: "DES", constitucion: "CON", inteligencia: "INT", sabiduria: "SAB", carisma: "CAR" };
export const ES_TIRADA = new Set(["prueba", "ataque", "tirada", "dano", "suerte"]);
export const CLASE_DOCUMENTO = { carta: "Carta", telegrama: "Telegrama", periodico: "Periódico", nota: "Nota", cartel: "Cartel", informe: "Informe", otro: "Documento" };
export const CATEGORIAS = ["personaje", "pnj", "lugar", "objeto", "promesa", "mundo", "trama", "otro"];
export const MOVIMIENTO_REDUCIDO = matchMedia("(prefers-reduced-motion: reduce)").matches;
export const VISTAS_IZQ = [["ficha", "Ficha"], ["hechos", "Hechos"], ["registro", "Registro"]];
export const VISTAS_DER = [["zona", "Zona"], ["mundo", "Mundo"], ["ambiente", "Ambientación"]];
export const VISTA_DE_EVENTO = {
  mapa: "zona", posicion: "zona", escena: "zona", mundo: "mundo", hecho: "hechos", memoria: "hechos",
  documento: "registro", pista: "registro", pnj: "registro", trama: "registro", misterio: "registro",
  vida: "ficha", condicion: "ficha", habilidad: "ficha", nivel: "ficha", enemigo: "ficha", vendaje: "ficha", descanso: "ficha", piloto: "ficha",
};
if (!VISTAS_IZQ.some(([id]) => id === app.izq)) app.izq = "ficha";
if (!VISTAS_DER.some(([id]) => id === app.der)) app.der = "zona";

if (new URLSearchParams(location.search).get("sala")) {
  guardarLocal("mesa-sala", app.sala);
  const sinClave = new URLSearchParams(location.search);
  sinClave.delete("sala");
  history.replaceState(null, "", `${location.pathname}${sinClave.toString() ? `?${sinClave}` : ""}${location.hash}`);
}

export function cabecerasSala(extra = {}) {
  const base = { "X-Mesa-Cliente": app.clienteId, ...extra };
  if (app.jugador) base["X-Mesa-Jugador"] = encodeURIComponent(app.jugador);
  if (app.sala) base["X-Mesa-Sala"] = app.sala;
  if (app.reclamo) base["X-Mesa-Reclamo"] = app.reclamo;
  return base;
}
export const mostrarError = (err) => { $("#estado-narrador").textContent = `✕ ${err.message}`; };

export async function api(ruta) {
  const r = await fetch(ruta, { cache: "no-store", headers: cabecerasSala() });
  if (!r.ok) throw new Error(`${ruta}: ${r.status}`);
  return r.json();
}

export function leerTema() { return leerLocal("mesa-tema", "auto"); }
export function aplicarTema(t) {
  if (t === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  $("#boton-tema").textContent = `Tema: ${t === "auto" ? "auto" : t === "dark" ? "oscuro" : "claro"}`;
  guardarLocal("mesa-tema", t);
}

// Callbacks que cierran ciclos entre módulos (ficha ↔ chat, memoria ↔ estado).
export const hooks = {
  pintarComposer() {},
  cargarEstado: async () => {},
  pintarVista() {},
  sondear: async () => {},
  elegirVista() {},
  ladoDe() { return "izq"; },
  abrirCajon() {},
  cerrarModalDdb() {},
};

export const ESTADOS_APARENTES = {
  "ileso": ["ileso", "✓ Ileso"], "herida leve": ["leve", "◐ Herida leve"], "herido": ["herido", "▲ Herido"],
  "grave": ["grave", "▲ Grave"], "fuera de combate": ["fuera", "✕ Fuera de combate"], "muerto": ["fuera", "✕ Muerto"],
};
export function estadoVida(p) {
  if (ESTADOS_APARENTES[p.estado_aparente]) return ESTADOS_APARENTES[p.estado_aparente];
  const r = p.vida_max ? p.vida / p.vida_max : 0;
  if (p.vida <= 0) return ["fuera", "✕ Fuera de combate"];
  if (r >= 1) return ["ileso", "✓ Ileso"];
  if (r > 0.5) return ["leve", "◐ Herida leve"];
  if (r > 0.25) return ["herido", "▲ Herido"];
  return ["grave", "▲ Grave"];
}
export const es2024 = (d) => Number(d?.schema_version) === 2 || d?.reglamento === "dnd-2024";

export async function refrescarVisor() {
  const ruta = app.slug ? `/api/visor?p=${encodeURIComponent(app.slug)}` : "/api/visor";
  const visor = await api(ruta).catch(() => ({ escritura: false, token: null, chat: false, sala: false }));
  app.escritura = Boolean(visor.escritura && visor.token);
  app.token = visor.token;
  app.chatActivo = Boolean(visor.chat);
  app.autor = visor.autor;
  app.salaDisponible = Boolean(visor.sala);
  app.anfitrion = Boolean(visor.anfitrion ?? visor.escritura);
  app.lectura = visor.lectura !== false;
  if (visor.pj) app.jugador = visor.pj;
  else if (!app.anfitrion && app.slug) app.reclamo = "";
}

export async function enviarPost(ruta, cuerpo) {
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

export async function reclamarPj(nombre) {
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

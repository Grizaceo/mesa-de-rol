// Modal de tiradas: catálogo SRD, atajos y POST /api/tirar.
import {
  $, app, enviarPost, esc, es2024, guardarLocal, hooks, signo, sinTildes,
} from "./nucleo.js";

const sondear = (...a) => hooks.sondear(...a);

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
    hooks.cerrarModalDdb();
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

export { abrirModalTiradas, cerrarModalTiradas, pintarCatalogoTiradas };

// Panel de campaña y ambiente: crear, configurar y presets.
import { $, app, enviarPost, hooks } from "./nucleo.js";

const sondear = (...a) => hooks.sondear(...a);

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
  if (panel.hidden) abrirPanelCampana(app.datos && app.chat.length === 0 ? "configurar" : "nueva");
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

$("#chat").addEventListener("click", (ev) => {
  const btnCampana = ev.target.closest("[data-abrir-campana]");
  if (btnCampana) abrirPanelCampana(btnCampana.dataset.abrirCampana || "configurar");
});

export { abrirPanelCampana };

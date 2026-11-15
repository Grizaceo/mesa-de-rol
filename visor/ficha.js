// Ficha D&D 2024 / d20-simple: lateral, modal y acciones sobre inventario.
import {
  $, ABREVIATURA_2024, ATRIBUTOS, app, cifra, colorSeguro, enviarPost, esc, es2024,
  estadoVida, ESTADOS_APARENTES, hooks, mostrarError, signo, sinTildes,
} from "./nucleo.js";
import { inv, pintarVistaInventario, svgArteItem } from "./inventario.js";
import { abrirModalTiradas } from "./tiradas.js";

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
export function elegirPjActivo(nombre) { pjActivoFicha = `pj:${nombre}`; }
export function cerrarModalDdb() {
  const modal = document.getElementById("modal-ddb");
  if (modal) modal.hidden = true;
  modalDdbPj = null;
}

let tabDdbPorPj = {};
let filtroAccionPorPj = {};
let modalDdbPj = null;
let tabModalPrincipal = "sheet";

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

export function construirCatalogoCharacters(d) {
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


function pintarModalPersonaje(p, d) {
  const c = calcDatosDdb(p, d);
  const nombre = p.nombre || "Personaje";
  const pjs = d.personajes || [];
  let cuerpoModal = "";
  if (tabModalPrincipal === "sheet") {
    cuerpoModal = pintarFicha(p, d, true);
  } else if (tabModalPrincipal === "inventory") {
    cuerpoModal = pintarVistaInventario(p, d, c);
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

export function pintarFichas(forzar = false) {
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
      hooks.pintarComposer();
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
    inv.categoria = invCat.dataset.invCat;
    pintarFichas();
    return;
  }
  if (ev.target.closest("[data-inv-toggle-add]")) {
    inv.formNuevo = !inv.formNuevo;
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
    await hooks.sondear();
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
    await hooks.sondear();
    return;
  }
  const equiparBtn = ev.target.closest("[data-inv-equipar]");
  if (equiparBtn) {
    equiparBtn.disabled = true;
    try {
      await enviarPost("/api/tirar", { accion: "equipar", quien: equiparBtn.dataset.ddbQuien, nombre: equiparBtn.dataset.invEquipar });
      app.firmaEstado = "";
      await hooks.sondear();
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
      await hooks.sondear();
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
      await hooks.sondear();
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
      inv.formNuevo = false;
      app.firmaEstado = "";
      await hooks.sondear();
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
      await hooks.sondear();
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
      await hooks.sondear();
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
      await hooks.sondear();
    } finally {
      hpBtn.disabled = false;
    }
  }
}

// A quién ataca: el servidor no elige solo. Se pregunta con los nombres que ven los jugadores.
export function elegirObjetivo(quien) {
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
    inv.texto = ev.target.value;
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
  await hooks.sondear();
});

hooks.cerrarModalDdb = cerrarModalDdb;

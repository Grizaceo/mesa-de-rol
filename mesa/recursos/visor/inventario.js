// Inventario del visor: ranuras, arte de objetos y la vista del modal.
import { esc, sinTildes } from "./nucleo.js";

export const inv = { categoria: "all", texto: "", formNuevo: false };

export const RANURAS_PAPERDOLL = [
  null, ["head", "Head"], null,
  ["ammo", "Ammunition"], ["neck", "Neck"], ["armor", "Armor"],
  ["off_hand", "Off-Hand"], ["chest", "Torso"], ["main_hand", "Weapon"],
  ["gloves", "Gloves"], ["belt", "Belt"], ["ring", "Ring"],
  null, ["legs", "Trousers"], null,
  null, ["boots", "Boots"], null,
];

export function inferirCategoriaItem(x) {
  if (x.categoria) return x.categoria;
  if (x.dano) return "weapon";
  const n = sinTildes(x.nombre || "");
  if (x.bono_ca || /armadura|cota|malla|cuero|escudo|casco|chaleco|shield|vest|armor/.test(n)) return "armor";
  return "gear";
}

export function inferirRanuraItem(x) {
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

export function svgArteItem(x) {
  const n = sinTildes(x.nombre || "");
  const cat = inferirCategoriaItem(x);
  if (/arco|bow|ballesta/.test(n)) {
    return `<svg viewBox="0 0 120 100"><defs><radialGradient id="g-bow" cx="50%" cy="50%" r="60%"><stop offset="0%" stop-color="#3b2d1f"/><stop offset="100%" stop-color="#11161f"/></radialGradient></defs><rect width="120" height="100" fill="url(#g-bow)"/><path d="M38 14 C78 30, 78 70, 38 86" fill="none" stroke="#c89b52" stroke-width="5" stroke-linecap="round"/><line x1="38" y1="14" x2="38" y2="86" stroke="#cbd5e1" stroke-width="1.6"/><line x1="24" y1="50" x2="88" y2="50" stroke="#e2b86b" stroke-width="3"/><polygon points="92,50 80,44 82,50 80,56" fill="#94a3b8"/></svg>`;
  }
  if (/flecha|virote|municion|carcaj|ammo/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#171411"/><path d="M40 34 L56 26 L78 76 L58 84 Z" fill="#78350f" stroke="#d97706" stroke-width="2.5"/><line x1="36" y1="18" x2="64" y2="74" stroke="#e2b86b" stroke-width="2.5"/><line x1="48" y1="14" x2="72" y2="70" stroke="#e2b86b" stroke-width="2.5"/><polygon points="34,14 42,18 36,24" fill="#cbd5e1"/><polygon points="46,10 54,14 48,20" fill="#cbd5e1"/></svg>`;
  }
  if (/escudo|rodela|shield/.test(n)) {
    return `<svg viewBox="0 0 120 100"><defs><radialGradient id="g-sh" cx="50%" cy="45%" r="60%"><stop offset="0%" stop-color="#2c3e55"/><stop offset="100%" stop-color="#0f141c"/></radialGradient></defs><rect width="120" height="100" fill="url(#g-sh)"/><path d="M36 18 H84 V50 C84 70, 60 84, 60 88 C60 84, 36 70, 36 50 Z" fill="#475569" stroke="#d8a657" stroke-width="4"/><circle cx="60" cy="48" r="9" fill="#d8a657"/></svg>`;
  }
  if (/casco|yelmo|corona|capucha|sombrero|head|helm/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#131922"/><path d="M34 62 V46 C34 26, 86 26, 86 46 V62 L76 76 H66 V52 H54 V76 H44 Z" fill="#64748b" stroke="#cbd5e1" stroke-width="3"/><line x1="60" y1="22" x2="60" y2="52" stroke="#d8a657" stroke-width="3.5"/></svg>`;
  }
  if (/amuleto|collar|medallon|relicario|neck/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#171321"/><path d="M38 22 C38 56, 82 56, 82 22" fill="none" stroke="#d8a657" stroke-width="3"/><polygon points="60,46 74,64 60,82 46,64" fill="#0ea5e9" stroke="#fde047" stroke-width="3"/></svg>`;
  }
  if (/anillo|sortija|sello|ring/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#18141c"/><circle cx="60" cy="56" r="20" fill="none" stroke="#eab308" stroke-width="7"/><polygon points="60,22 70,32 60,40 50,32" fill="#ef4444" stroke="#fef08a" stroke-width="2"/></svg>`;
  }
  if (/guante|manopla|brazal|gloves/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#171614"/><path d="M40 76 L36 46 C36 38, 44 38, 46 44 V30 C46 24, 56 24, 56 30 V26 C56 20, 66 20, 66 26 V32 C66 26, 76 26, 76 34 V56 L82 76 Z" fill="#78350f" stroke="#d97706" stroke-width="2.8"/></svg>`;
  }
  if (/pocion|elixir|frasco|vial|antidoto|potion/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#131922"/><rect x="52" y="16" width="16" height="12" rx="2" fill="#a16207"/><path d="M48 28 H72 L84 62 C86 76, 76 86, 60 86 C44 86, 34 76, 36 62 Z" fill="#dc2626" stroke="#fca5a5" stroke-width="3"/><path d="M44 58 Q60 52 76 58" fill="none" stroke="#fecaca" stroke-width="2"/></svg>`;
  }
  if (/venda|vendaje|botiquin|bandage/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#182026"/><ellipse cx="56" cy="54" rx="26" ry="18" fill="#e2e8f0" stroke="#94a3b8" stroke-width="3"/><ellipse cx="56" cy="46" rx="26" ry="12" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/><ellipse cx="56" cy="46" rx="9" ry="4" fill="#64748b"/><path d="M76 58 L98 70 L90 78 L66 66" fill="#e2e8f0" stroke="#94a3b8" stroke-width="2"/></svg>`;
  }
  if (/antorcha|farol|linterna|vela|torch|lantern/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#1c1510"/><path d="M60 14 C74 28, 76 44, 60 52 C44 44, 46 28, 60 14 Z" fill="#f97316" stroke="#fde047" stroke-width="2.5"/><path d="M60 24 C67 32, 67 42, 60 48 C53 42, 53 32, 60 24 Z" fill="#fef08a"/><rect x="55" y="50" width="10" height="36" rx="3" fill="#78350f" stroke="#d97706" stroke-width="2"/></svg>`;
  }
  if (/racion|comida|pan|queso|odre|vino|cerveza|ration|food/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#1a1612"/><path d="M30 62 C30 40, 90 40, 90 62 C90 74, 30 74, 30 62 Z" fill="#b45309" stroke="#f59e0b" stroke-width="3"/><line x1="48" y1="46" x2="44" y2="58" stroke="#fde68a" stroke-width="2.5"/><line x1="62" y1="45" x2="58" y2="57" stroke="#fde68a" stroke-width="2.5"/><line x1="76" y1="46" x2="72" y2="58" stroke="#fde68a" stroke-width="2.5"/></svg>`;
  }
  if (/llave|ganzua|herramienta|cuerda|key|lockpick|rope/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#14181f"/><circle cx="42" cy="50" r="14" fill="none" stroke="#eab308" stroke-width="5"/><line x1="56" y1="50" x2="90" y2="50" stroke="#eab308" stroke-width="5" stroke-linecap="round"/><line x1="76" y1="50" x2="76" y2="62" stroke="#eab308" stroke-width="4.5"/><line x1="86" y1="50" x2="86" y2="66" stroke="#eab308" stroke-width="4.5"/></svg>`;
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
  if (/carta|contrato|pergamino|libro|grimorio|mapa|scroll/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#181512"/><rect x="32" y="16" width="56" height="68" rx="4" fill="#dfd2b5" stroke="#a16207" stroke-width="3"/><line x1="42" y1="32" x2="78" y2="32" stroke="#57534e" stroke-width="2.5"/><line x1="42" y1="44" x2="78" y2="44" stroke="#57534e" stroke-width="2.5"/><line x1="42" y1="56" x2="68" y2="56" stroke="#57534e" stroke-width="2.5"/><circle cx="72" cy="70" r="7" fill="#9333ea"/></svg>`;
  }
  if (/baston|vara|varita|cetro|orbe|foco|wand|staff/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#151221"/><line x1="28" y1="82" x2="76" y2="34" stroke="#92400e" stroke-width="6" stroke-linecap="round"/><circle cx="82" cy="28" r="11" fill="#38bdf8" stroke="#bae6fd" stroke-width="3"/><circle cx="82" cy="28" r="4" fill="#f0f9ff"/></svg>`;
  }
  if (/hacha|maza|martillo|clava|barra|axe|mace|hammer/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#16181d"/><line x1="30" y1="82" x2="78" y2="26" stroke="#92400e" stroke-width="6" stroke-linecap="round"/><path d="M56 18 L92 38 L78 54 L46 32 Z" fill="#94a3b8" stroke="#e2e8f0" stroke-width="2.5"/></svg>`;
  }
  if (/daga|cuchillo|navaja|estilete|dagger/.test(n)) {
    return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#131720"/><polygon points="84,20 52,58 44,50" fill="#e2e8f0" stroke="#94a3b8" stroke-width="2"/><line x1="38" y1="44" x2="58" y2="64" stroke="#d8a657" stroke-width="4" stroke-linecap="round"/><line x1="32" y1="70" x2="46" y2="56" stroke="#78350f" stroke-width="5" stroke-linecap="round"/></svg>`;
  }
  if (cat === "weapon" || /espada|mandoble|estoque|cimitarra|rapier|jabalina|lanza|bichero|baton/.test(n)) {
    return `<svg viewBox="0 0 120 100"><defs><radialGradient id="g-wp" cx="50%" cy="50%" r="60%"><stop offset="0%" stop-color="#2a3441"/><stop offset="100%" stop-color="#0d1117"/></radialGradient></defs><rect width="120" height="100" fill="url(#g-wp)"/><line x1="28" y1="76" x2="88" y2="18" stroke="#e2e8f0" stroke-width="6" stroke-linecap="round"/><line x1="28" y1="76" x2="88" y2="18" stroke="#94a3b8" stroke-width="2"/><line x1="34" y1="56" x2="52" y2="74" stroke="#d8a657" stroke-width="5" stroke-linecap="round"/><line x1="22" y1="82" x2="36" y2="68" stroke="#78350f" stroke-width="6" stroke-linecap="round"/><circle cx="20" cy="84" r="4.5" fill="#d8a657"/></svg>`;
  }
  return `<svg viewBox="0 0 120 100"><rect width="120" height="100" fill="#141a22"/><rect x="34" y="26" width="52" height="48" rx="8" fill="#334155" stroke="#d8a657" stroke-width="3"/><path d="M48 26 V20 H72 V26" fill="none" stroke="#d8a657" stroke-width="3"/><circle cx="60" cy="50" r="6" fill="#f5d087"/></svg>`;
}


export function pintarVistaInventario(p, d, c) {
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

  const q = sinTildes(inv.texto);
  const filtrados = equipo.filter((x) => {
    if (inv.categoria !== "all" && inferirCategoriaItem(x) !== inv.categoria) return false;
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
      ${[["all", "⊞ All"], ["weapon", "🗡️ Weapons"], ["armor", "🛡️ Armor"], ["gear", "🎒 Gear"]].map(([id, lbl]) => `<button type="button" class="${inv.categoria === id ? "activo" : ""}" data-inv-cat="${id}">${lbl}</button>`).join("")}
    </div>

    <div class="ff-inv-barra">
      <div class="ff-inv-search">
        <span>⌕</span>
        <input type="search" id="inv-buscar-input" value="${esc(inv.texto)}" placeholder="Search...">
      </div>
      <button type="button" class="ff-btn-accion oro" data-inv-toggle-add="si">⊕ Add Item</button>
    </div>

    ${inv.formNuevo ? `
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

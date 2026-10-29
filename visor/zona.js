// Mapa de zona: el visor pinta la proyección que calcula el motor (`/api/zona`).
import { $, api, app, cifra, colorSeguro, esc, metros, sinTildes } from "./nucleo.js";
import { construirCatalogoCharacters } from "./ficha.js";

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

export function pintarZona(forzar = false) {
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
export function refrescarZona() {
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

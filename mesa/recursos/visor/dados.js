// Tarjetas de dados del visor: el chat y el historial pintan las tiradas de la bitácora.
import { $, app, ATRIBUTOS, esc, es2024, ES_TIRADA, MOVIMIENTO_REDUCIDO, signo } from "./nucleo.js";

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
export function svgDado(caras, valor) {
  const arista = caras === 20 ? '<polygon class="arista" points="50,24 75,66 25,66"/>' : caras === 8 ? '<line class="arista" x1="5" y1="50" x2="95" y2="50"/>' : "";
  const y = caras === 4 || caras === 3 ? 62 : 52;
  return `<svg viewBox="0 0 100 100" role="img" aria-label="d${caras}: ${esc(valor)}"><polygon class="cara" points="${FORMAS[caras] || FORMAS[20]}"/>${arista}<text class="valor" x="50" y="${y}">${esc(valor)}</text></svg>`;
}
function caras(dado) { return Number(String(dado).replace("d", "")) || 20; }

export function dadosDeEvento(e) {
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

export function nombreAccion(e) {
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

export function cuentaDano(d, moderno) {
  const valores = (d.tirada?.dados || []).flatMap((t) => t.valores).join(" + ") || esc(d.tirada?.total ?? "");
  const mod = d.bonus_mod ? ` ${signo(d.bonus_mod)} (${esc(d.fuente_mod || "mod")})` : "";
  const cabeza = `Daño ${esc(d.tirada?.expr || "")}${d.tirada?.critico ? " (crítico: dados dobles)" : ""}: ${valores}${mod} = ${esc(d.bruto)}`;
  if (moderno) return `${cabeza}${d.ajuste_resistencia ? ` [${esc(d.ajuste_resistencia)}]` : ""} → <b>${esc(d.final)}</b>${destinoDe(d)}`;
  return `${cabeza} − protección ${esc(d.proteccion ?? 0)} = <b>${esc(d.final)}</b>${destinoDe(d)}`;
}

export function cuentaDe(e) {
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

export function modoDe(e) {
  if (e.modo === "ventaja") return `Ventaja: ${esc(e.ventajas.join(", "))}`;
  if (e.modo === "desventaja") return `Desventaja: ${esc(e.desventajas.join(", "))}`;
  if (e.ventajas?.length && e.desventajas?.length) return `Ventaja y desventaja se anulan (${esc([...e.ventajas, ...e.desventajas].join(", "))})`;
  return "";
}

export function resultadoDe(e) {
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
export function tarjetaDados(e, animar) {
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

export function animarDados(raiz) {
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

export function listaTiradas() {
  const tiradas = app.eventos.filter((e) => ES_TIRADA.has(e.tipo)).slice(-60).reverse();
  return tiradas.length ? `<ol class="historial">${tiradas.map((e) => {
    const res = resultadoDe(e);
    const dado = e.tipo === "suerte" ? "d100" : e.tipo === "prueba" || e.tipo === "ataque" ? `${e.modo === "normal" ? "1" : "2"}d${e.caras || 20}` : esc(e.expr);
    const total = e.tipo === "suerte" ? e.valor : (e.final ?? e.total ?? e.elegido);
    return `<li><span class="mini-dado">${dado}</span><span><b>${esc(e.quien || "")}</b> ${esc(nombreAccion(e))} — ${esc(total)}${e.cd != null ? ` vs ${esc(e.cd)}` : ""}${e.etiqueta ? ` <span class="texto-3">· ${esc(e.etiqueta)}</span>` : ""}</span>${res ? `<span class="chip r-${res[0]}">${res[1].replace(/^\S+ /, "")}</span>` : ""}</li>`;
  }).join("")}</ol>` : '<p class="texto-3">Sin tiradas todavía.</p>';
}

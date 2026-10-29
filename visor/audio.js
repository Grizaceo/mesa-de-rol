// Motor de audio zero-asset (Web Audio API): efectos de dados/mesa y ambiente procedural reactivo.
import { $, app, guardarLocal, leerLocal, MOVIMIENTO_REDUCIDO, sinTildes } from "./nucleo.js";

const MODOS_SONIDO = ["efectos", "ambiente", "silencio"];
const ETIQUETAS_SONIDO = {
  efectos: "Sonido: efectos",
  ambiente: "Sonido: + música",
  silencio: "Sonido: no",
};

// Paletas de notas (Hz) y patrón determinista de arpegio por estado de la escena.
const PALETAS_AMBIENTE = {
  calma: [220.0, 246.94, 293.66, 329.63, 392.0, 440.0],       // La menor pentatónica / dórica suave
  misterio: [196.0, 207.65, 246.94, 293.66, 311.13, 392.0],   // Sol frigio oscuro
  combate: [146.83, 174.61, 196.0, 207.65, 220.0, 293.66],    // Re menor tenso con quinta disminuida
};
const PATRON_AMBIENTE = [0, 2, 4, 2, 1, 3, 5, 3, 0, 2, 3, 1];

let ctx = null;
let sfxGain = null;
let ambientMaster = null;
let timerAmbiente = null;
let nextNoteTime = 0;
let stepIndex = 0;
let moodActual = "calma";

export function leerModoSonido() {
  const defecto = MOVIMIENTO_REDUCIDO ? "silencio" : "efectos";
  const guardado = leerLocal("mesa-sonido", defecto);
  return MODOS_SONIDO.includes(guardado) ? guardado : defecto;
}

let modoSonido = leerModoSonido();

function obtenerContexto() {
  if (modoSonido === "silencio") return null;
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return null;
  if (!ctx) {
    ctx = new AudioCtx();
    sfxGain = ctx.createGain();
    sfxGain.gain.value = 0.22;
    sfxGain.connect(ctx.destination);
    ambientMaster = ctx.createGain();
    ambientMaster.gain.value = 0.0001;
    ambientMaster.connect(ctx.destination);
  }
  if (ctx.state === "suspended") {
    ctx.resume().catch(() => {});
  }
  return ctx;
}

function pulso(c, freq, freqFin, duracion, tipo = "sine", volumen = 0.25, retraso = 0) {
  const t0 = c.currentTime + retraso;
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = tipo;
  osc.frequency.setValueAtTime(freq, t0);
  if (freqFin && freqFin !== freq) {
    osc.frequency.exponentialRampToValueAtTime(Math.max(20, freqFin), t0 + duracion);
  }
  const ataque = Math.min(0.02, duracion * 0.25);
  gain.gain.setValueAtTime(0.0001, t0);
  gain.gain.linearRampToValueAtTime(volumen, t0 + ataque);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duracion);
  osc.connect(gain);
  gain.connect(sfxGain);
  osc.start(t0);
  osc.stop(t0 + duracion + 0.01);
  osc.onended = () => {
    osc.disconnect();
    gain.disconnect();
  };
}

export function sonarEfecto(tipo) {
  if (modoSonido === "silencio") return;
  const c = obtenerContexto();
  if (!c) return;
  switch (tipo) {
    case "rodar": {
      const base = 320 + Math.random() * 240;
      pulso(c, base, base * 0.65, 0.045, "triangle", 0.16);
      break;
    }
    case "critico":
      pulso(c, 523.25, 523.25, 0.11, "triangle", 0.28, 0.0);
      pulso(c, 659.25, 659.25, 0.11, "triangle", 0.28, 0.09);
      pulso(c, 783.99, 783.99, 0.14, "triangle", 0.3, 0.18);
      pulso(c, 1046.5, 1046.5, 0.28, "sine", 0.32, 0.28);
      break;
    case "uno_natural":
    case "fallo_automatico":
      pulso(c, 210, 98, 0.22, "sawtooth", 0.18, 0.0);
      pulso(c, 140, 62, 0.35, "sawtooth", 0.2, 0.16);
      break;
    case "exito":
    case "si":
      pulso(c, 440, 440, 0.1, "sine", 0.22, 0.0);
      pulso(c, 659.25, 659.25, 0.2, "sine", 0.24, 0.08);
      break;
    case "fallo":
    case "no":
      pulso(c, 293.66, 220, 0.18, "triangle", 0.18, 0.0);
      break;
    case "cura":
      pulso(c, 523.25, 783.99, 0.22, "sine", 0.2, 0.0);
      break;
    case "dano":
      pulso(c, 160, 55, 0.18, "triangle", 0.24, 0.0);
      break;
    case "ui":
      pulso(c, 660, 880, 0.06, "sine", 0.12, 0.0);
      break;
  }
}

function programarNotaAmbiente(c, tiempo, freq, duracion) {
  const osc = c.createOscillator();
  const lfo = c.createOscillator();
  const lfoGain = c.createGain();
  const gain = c.createGain();

  osc.type = moodActual === "combate" ? "triangle" : "sine";
  osc.frequency.setValueAtTime(freq, tiempo);

  lfo.type = "sine";
  lfo.frequency.setValueAtTime(4.5, tiempo);
  lfoGain.gain.setValueAtTime(1.2, tiempo);
  lfo.connect(lfoGain);
  lfoGain.connect(osc.frequency);

  gain.gain.setValueAtTime(0.0001, tiempo);
  gain.gain.linearRampToValueAtTime(0.12, tiempo + 0.08);
  gain.gain.exponentialRampToValueAtTime(0.0001, tiempo + duracion);

  osc.connect(gain);
  gain.connect(ambientMaster);

  osc.start(tiempo);
  lfo.start(tiempo);
  osc.stop(tiempo + duracion + 0.02);
  lfo.stop(tiempo + duracion + 0.02);
  osc.onended = () => {
    lfo.disconnect();
    lfoGain.disconnect();
    osc.disconnect();
    gain.disconnect();
  };
}

function planificarAmbiente() {
  if (modoSonido !== "ambiente" || !ctx) {
    timerAmbiente = null;
    return;
  }
  if (ctx.state === "running") {
    const bpm = moodActual === "combate" ? 112 : moodActual === "misterio" ? 72 : 84;
    const paso = 60 / bpm / 2;
    const notas = PALETAS_AMBIENTE[moodActual] || PALETAS_AMBIENTE.calma;
    if (nextNoteTime < ctx.currentTime) nextNoteTime = ctx.currentTime + 0.05;
    while (nextNoteTime < ctx.currentTime + 0.3) {
      const freq = notas[PATRON_AMBIENTE[stepIndex % PATRON_AMBIENTE.length] % notas.length];
      programarNotaAmbiente(ctx, nextNoteTime, freq, paso * 1.6);
      nextNoteTime += paso;
      stepIndex++;
    }
  }
  timerAmbiente = setTimeout(planificarAmbiente, 100);
}

function iniciarAmbiente() {
  const c = obtenerContexto();
  if (!c || !ambientMaster) return;
  const ahora = c.currentTime;
  ambientMaster.gain.cancelScheduledValues(ahora);
  ambientMaster.gain.setValueAtTime(Math.max(0.0001, ambientMaster.gain.value), ahora);
  ambientMaster.gain.linearRampToValueAtTime(0.32, ahora + 0.6);
  if (!timerAmbiente) {
    nextNoteTime = ahora + 0.08;
    planificarAmbiente();
  }
}

function detenerAmbiente() {
  if (timerAmbiente) {
    clearTimeout(timerAmbiente);
    timerAmbiente = null;
  }
  if (ctx && ambientMaster) {
    const ahora = ctx.currentTime;
    ambientMaster.gain.cancelScheduledValues(ahora);
    ambientMaster.gain.setValueAtTime(Math.max(0.0001, ambientMaster.gain.value), ahora);
    ambientMaster.gain.linearRampToValueAtTime(0.0001, ahora + 0.25);
  }
}

export function inferirMoodEscena(datos) {
  if (!datos) return "calma";
  const hayCombate = (datos.enemigos || []).some((e) => (e.estado_aparente ? !["fuera de combate", "muerto"].includes(e.estado_aparente) : Number(e.vida ?? 1) > 0));
  if (hayCombate) return "combate";
  const luz = datos.escena?.mapa?.luz || "";
  const texto = sinTildes([datos.escena?.titulo, datos.escena?.lugar, ...(datos.ambientacion?.tono || [])].join(" "));
  if (luz === "oscuridad" || /cripta|oscur|horror|misterio|sombra|tumba|ruina|niebla/.test(texto)) return "misterio";
  return "calma";
}

export function actualizarMoodAmbiente(datos) {
  const nuevo = inferirMoodEscena(datos);
  if (nuevo === moodActual) return;
  moodActual = nuevo;
  if (modoSonido === "ambiente" && ctx && ambientMaster) {
    const ahora = ctx.currentTime;
    ambientMaster.gain.cancelScheduledValues(ahora);
    ambientMaster.gain.setValueAtTime(Math.max(0.0001, ambientMaster.gain.value), ahora);
    ambientMaster.gain.linearRampToValueAtTime(0.04, ahora + 0.3);
    ambientMaster.gain.linearRampToValueAtTime(0.32, ahora + 0.9);
  }
}

export function aplicarModoSonido(modo) {
  modoSonido = MODOS_SONIDO.includes(modo) ? modo : "efectos";
  guardarLocal("mesa-sonido", modoSonido);
  const btn = $("#boton-sonido");
  if (btn) btn.textContent = ETIQUETAS_SONIDO[modoSonido];
  if (modoSonido === "ambiente") {
    actualizarMoodAmbiente(app.datos);
    iniciarAmbiente();
  } else {
    detenerAmbiente();
  }
}

export function alternarModoSonido() {
  const sig = MODOS_SONIDO[(MODOS_SONIDO.indexOf(modoSonido) + 1) % MODOS_SONIDO.length];
  aplicarModoSonido(sig);
  if (sig !== "silencio") sonarEfecto("ui");
}

document.addEventListener("pointerdown", () => {
  if (modoSonido === "ambiente" && (!ctx || ctx.state === "suspended")) iniciarAmbiente();
}, { passive: true });

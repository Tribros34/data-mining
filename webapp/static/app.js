/* Math Buddy workbench – client. Plain JS, no libraries. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (p) => (p * 100).toFixed(1) + "%";
const TOPIC_COLORS = { addition: "#1e1d1a", subtraction: "#b23a26", multiplication: "#2c5683", division: "#a77d1c", fractions: "#4a7446" };
let META = null;

async function api(path, body, isForm = false) {
  const res = await fetch(path, isForm ? { method: "POST", body } :
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({ error: "Server error (" + res.status + ")" }));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function showError(out, err) { out.innerHTML = `<p class="err">${esc(err.message || err)}</p>`; }

function bars(probabilities, { order = null, cls = "" } = {}) {
  const keys = order || Object.keys(probabilities).sort((a, b) => probabilities[b] - probabilities[a]);
  const best = Object.keys(probabilities).reduce((a, b) => (probabilities[a] >= probabilities[b] ? a : b));
  return `<div class="bars ${cls}">` + keys.map((k) => `
    <div class="bar ${k === best ? "best" : ""}"><span class="n">${esc(k)}</span>
      <span class="t"><span class="f" style="width:${(probabilities[k] * 100).toFixed(1)}%"></span></span>
      <span class="v">${pct(probabilities[k])}</span></div>`).join("") + "</div>";
}

function sheet(rows) {
  return `<dl class="sheet">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
}

function debounce(fn, ms = 160) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/* ------------------------------------------------------------ navigation */
function route() {
  const id = (location.hash || "#overview").slice(1);
  const target = document.getElementById(id) ? id : "overview";
  $$(".block").forEach((s) => s.classList.toggle("on", s.id === target));
  $$("nav.index a").forEach((a) => a.setAttribute("aria-current", a.getAttribute("href") === "#" + target));
  window.scrollTo(0, 0);
  if (target === "b4") runB4(); if (target === "b5b") runB5b(); if (target === "b8") runB8();
  if (target === "b6") renderB6();
}
window.addEventListener("hashchange", route);

/* ------------------------------------------------------------ slider fields */
function fieldValues(root) {
  const v = {};
  $$(".field", root).forEach((f) => {
    const range = $("input[type=range]", f); const off = $(".off input", f);
    v[f.dataset.key] = off && off.checked ? null : parseFloat(range.value);
  });
  return v;
}
function wireFields(root, onChange) {
  $$(".field", root).forEach((f) => {
    const range = $("input[type=range]", f); const out = $("output", f); const off = $(".off input", f);
    const show = () => {
      const missing = off && off.checked;
      f.classList.toggle("disabled", !!missing);
      out.textContent = missing ? "—" : range.value;
    };
    range.addEventListener("input", () => { show(); onChange(); });
    if (off) off.addEventListener("change", () => { show(); onChange(); });
    show();
  });
}
function setFields(root, keys, values) {
  keys.forEach((k, i) => {
    const f = $(`.field[data-key="${k}"]`, root); const range = $("input[type=range]", f); const off = $(".off input", f);
    range.value = values[i]; if (off) off.checked = false;
    range.dispatchEvent(new Event("input"));
  });
}
// Used by camera.js: set the three B4 sliders from a camera measurement (null = missing value) and run B4
window.b4FromCamera = (values) => {
  Object.entries(values).forEach(([k, v]) => {
    const f = $(`#b4-in .field[data-key="${k}"]`); const range = $("input[type=range]", f); const off = $(".off input", f);
    off.checked = v == null; if (v != null) range.value = v;
    f.classList.toggle("disabled", v == null); $("output", f).textContent = v == null ? "—" : range.value;
  });
  runB4();
};

/* ------------------------------------------------------------ B1 / B2 */
async function runB1() {
  const out = $("#b1-out");
  try {
    const d = await api("/api/b1", { message: $("#b1-msg").value });
    const r = d.result;
    out.innerHTML = `<span class="label">Output</span>
      <p class="verdict">${esc(r.interest)}<span class="p">${pct(r.probability)}</span></p>
      ${bars(d.probabilities)}
      ${sheet([["sentiment", esc(r.sentiment)], ["use for word problems", r.use_for_problems ? "yes" : "no"]])}
      ${bars(d.sentiment_probabilities, { order: ["positive", "neutral", "negative"] })}
      ${d.word_problem ? `<div class="callout blue"><span class="label">What the tutor does with it</span>${esc(d.word_problem)}</div>`
        : `<div class="callout"><span class="label">What the tutor does with it</span>The child is negative about this interest, so the tutor does not build word problems around it.</div>`}`;
  } catch (e) { showError(out, e); }
}
async function runB2() {
  const out = $("#b2-out");
  try {
    const d = await api("/api/b2", { message: $("#b2-msg").value });
    const r = d.result;
    out.innerHTML = `<span class="label">Output</span>
      <p class="verdict">${esc(r.topic)}<span class="p">${pct(r.probability)}</span></p>
      ${bars(d.probabilities)}
      ${sheet([["sentiment", esc(r.sentiment)], ["start with easy questions", r.start_easy ? "yes" : "no"]])}
      ${bars(d.sentiment_probabilities, { order: ["positive", "neutral", "negative"] })}`;
  } catch (e) { showError(out, e); }
}

/* ------------------------------------------------------------ B3 */
const pad = $("#pad"); const ctx = pad.getContext("2d");
let drawing = false; let last = null; let hasInk = false;
function padPoint(e) {
  const r = pad.getBoundingClientRect();
  return [(e.clientX - r.left) * (pad.width / r.width), (e.clientY - r.top) * (pad.height / r.height)];
}
function clearPad() {
  ctx.clearRect(0, 0, pad.width, pad.height); hasInk = false;
  $("#b3-out").innerHTML = `<p class="empty">Draw one digit, 0–9.</p>`;
}
pad.addEventListener("pointerdown", (e) => { drawing = true; last = padPoint(e); pad.setPointerCapture(e.pointerId); stroke(last); });
pad.addEventListener("pointermove", (e) => { if (drawing) stroke(padPoint(e)); });
const endStroke = () => { if (!drawing) return; drawing = false; last = null; if ($("#pad-auto").checked) runB3(); };
pad.addEventListener("pointerup", endStroke); pad.addEventListener("pointercancel", endStroke);
function stroke(p) {
  ctx.strokeStyle = "#1e1d1a"; ctx.fillStyle = "#1e1d1a"; ctx.lineWidth = 16; ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.beginPath(); ctx.moveTo(last[0], last[1]); ctx.lineTo(p[0], p[1]); ctx.stroke();
  last = p; hasInk = true;
}
$("#pad-clear").addEventListener("click", clearPad);

function padInk() {
  // alpha channel at half resolution (140 x 140): 0 = paper, 255 = ink
  const small = document.createElement("canvas"); small.width = small.height = 140;
  small.getContext("2d").drawImage(pad, 0, 0, 140, 140);
  const px = small.getContext("2d").getImageData(0, 0, 140, 140).data;
  const rows = [];
  for (let y = 0; y < 140; y++) { const row = []; for (let x = 0; x < 140; x++) row.push(px[(y * 140 + x) * 4 + 3]); rows.push(row); }
  return rows;
}
function drawPixels(canvas, image, max) {
  const n = image.length; canvas.width = canvas.height = n;
  const c = canvas.getContext("2d"); const img = c.createImageData(n, n);
  image.forEach((row, y) => row.forEach((v, x) => {
    const shade = 251 - Math.round((v / max) * 222); const i = (y * n + x) * 4;
    img.data[i] = shade; img.data[i + 1] = shade - 1; img.data[i + 2] = shade - 5; img.data[i + 3] = 255;
  }));
  c.putImageData(img, 0, 0);
}
async function runB3() {
  const out = $("#b3-out");
  if (!hasInk) { out.innerHTML = `<p class="err">Draw a digit first.</p>`; return; }
  try {
    const d = await api("/api/b3", { ink: padInk() });
    out.innerHTML = `<span class="label">Output · MNIST model (used by the app)</span>
      <p class="verdict">${d.mnist.result.digit}<span class="p">${pct(d.mnist.result.probability)}</span></p>
      ${bars(d.mnist.probabilities, { order: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], cls: "digits" })}
      <span class="label" style="margin-top:16px">What each model saw</span>
      <div class="previews">
        <figure><canvas id="pv28"></canvas><figcaption>28×28 → ${d.mnist.result.digit}</figcaption></figure>
        <figure><canvas id="pv8"></canvas><figcaption>8×8 → ${d.small.result.digit} (${pct(d.small.result.probability)})</figcaption></figure>
      </div>
      <p class="muted">The 8×8 model is the first B3 model (load_digits). It is kept for comparison only.</p>`;
    drawPixels($("#pv28"), d.mnist.image, 255); drawPixels($("#pv8"), d.small.image, 16);
  } catch (e) { showError(out, e); }
}

/* ------------------------------------------------------------ B4 */
const runB4 = debounce(async () => {
  const out = $("#b4-out");
  try {
    const d = await api("/api/b4", fieldValues($("#b4-in")));
    const r = d.result;
    document.dispatchEvent(new CustomEvent("b4result", { detail: r }));
    out.innerHTML = `<span class="label">Output</span>
      <p class="verdict">${esc(r.state)}<span class="p">${pct(r.probabilities[r.state])}</span></p>
      ${bars(r.probabilities, { order: ["attentive", "distracted", "tired"] })}
      <span class="label" style="margin-top:18px">How much the forest relies on each feature</span>
      ${bars({ "gaze": d.importance.screen_gaze_ratio, "head angle": d.importance.head_angle, "blink rate": d.importance.blink_rate },
        { order: ["gaze", "head angle", "blink rate"] })}`;
  } catch (e) { showError(out, e); }
});

/* ------------------------------------------------------------ B5a */
let recording = false;
function encodeWav(samples, rate) {
  const buf = new ArrayBuffer(44 + samples.length * 2); const v = new DataView(buf);
  const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data");
  v.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Blob([buf], { type: "audio/wav" });
}
async function record() {
  if (recording) return;
  const msg = $("#rec-msg"); const btn = $("#rec-btn");
  if (!navigator.mediaDevices || !window.MediaRecorder) { msg.textContent = "This browser cannot record audio here (use localhost or https)."; return; }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch { msg.textContent = "Microphone permission was refused."; return; }
  recording = true; btn.disabled = true; $("#rec").classList.add("live");
  const chunks = []; const rec = new MediaRecorder(stream);
  rec.ondataavailable = (e) => chunks.push(e.data);
  rec.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    recording = false; btn.disabled = false; $("#rec").classList.remove("live");
    msg.textContent = "Processing…";
    try {
      const actx = new (window.AudioContext || window.webkitAudioContext)();
      const audio = await actx.decodeAudioData(await new Blob(chunks).arrayBuffer());
      const wav = encodeWav(audio.getChannelData(0), audio.sampleRate); actx.close();
      const form = new FormData(); form.append("audio", wav, "recording.wav");
      msg.textContent = "Recorded " + audio.duration.toFixed(1) + " s.";
      showB5a(await api("/api/b5a", form, true), "your recording");
    } catch (e) { msg.textContent = ""; showError($("#b5a-out"), e); }
  };
  msg.textContent = "Speak now…"; rec.start();
  setTimeout(() => rec.state !== "inactive" && rec.stop(), 1500);
}
function waveSvg(points) {
  const w = 400, h = 70, n = points.length; const max = Math.max(0.01, ...points.map(Math.abs));
  const d = points.map((p, i) => `${((i / (n - 1)) * w).toFixed(1)},${(h / 2 - (p / max) * (h / 2 - 3)).toFixed(1)}`).join(" ");
  return `<svg class="wave" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${d}" fill="none" stroke="#1e1d1a" stroke-width="1"/></svg>`;
}
function showB5a(d, source) {
  const r = d.result;
  $("#b5a-out").innerHTML = `<span class="label">Output · ${esc(source)}</span>
    <p class="verdict">${r.digit}<span class="p">${pct(r.probability)}</span></p>
    ${waveSvg(d.waveform)}
    <p class="muted">${d.duration} s recorded${d.duration_trimmed !== d.duration ? `, ${d.duration_trimmed} s after cutting the silence` : ""}</p>
    ${bars(d.probabilities, { order: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], cls: "digits" })}`;
}
$("#rec-btn").addEventListener("click", record);
$("#wav-file").addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file) return;
  const form = new FormData(); form.append("audio", file, file.name);
  try { showB5a(await api("/api/b5a", form, true), file.name); } catch (err) { showError($("#b5a-out"), err); }
});

/* ------------------------------------------------------------ B5b */
const runB5b = debounce(async () => {
  const out = $("#b5b-out");
  try {
    const r = (await api("/api/b5b", fieldValues($("#b5b-in")))).result;
    out.innerHTML = `<span class="label">Output</span>
      <p class="verdict">${esc(r.state)}<span class="p">P(hesitant) = ${r.p_hesitant.toFixed(3)}</span></p>
      ${bars({ confident: 1 - r.p_hesitant, hesitant: r.p_hesitant }, { order: ["confident", "hesitant"] })}
      <div class="callout blue"><span class="label">What the tutor does with it</span>${r.state === "hesitant"
        ? "A correct but hesitant answer may have been a guess. The tutor gives one more question of the same kind before moving on, and B6 counts the hesitation in the history."
        : "The answer sounded sure. The tutor can move on."}</div>`;
  } catch (e) { showError(out, e); }
});

/* B5b from the microphone: show a question, record until the child is quiet, let the server measure the features */
const QUESTIONS = [["3 + 4", 7], ["9 − 5", 4], ["2 × 3", 6], ["8 ÷ 2", 4], ["6 + 2", 8], ["7 − 6", 1], ["3 × 3", 9], ["10 ÷ 2", 5]];
let asking = false;

function setB5bSliders(f) {                // write measured values into the sliders without re-running B5b
  Object.entries(f).forEach(([k, v]) => {
    const field = $(`#b5b-in .field[data-key="${k}"]`); const range = $("input[type=range]", field);
    range.value = v; $("output", field).textContent = v;
  });
}

function voiceSvg(d) {
  const W = 560, H = 120, T = 14, B = 26; const total = d.duration;
  const x = (t) => (t / total) * W; const y = (v) => T + (1 - v) * (H - T - B);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Loudness of the recording">`;
  s += `<rect x="0" y="${T}" width="${x(d.speech_start)}" height="${H - T - B}" fill="#2c5683" opacity="0.16"/>`;
  s += `<text x="${x(d.speech_start) / 2}" y="${T - 3}" font-size="10" text-anchor="middle" fill="#2c5683">delay ${d.speech_start.toFixed(2)} s</text>`;
  d.pauses.forEach(([a, b]) => { s += `<rect x="${x(a)}" y="${T}" width="${x(b) - x(a)}" height="${H - T - B}" fill="#b23a26" opacity="0.14"/>`; });
  d.segments.forEach(([a, b]) => { s += `<line x1="${x(a)}" x2="${x(b)}" y1="${H - B + 6}" y2="${H - B + 6}" stroke="#1e1d1a" stroke-width="3"/>`; });
  const pts = d.envelope.map((v, i) => `${x(i * d.envelope_step).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  s += `<polyline points="${pts}" fill="none" stroke="#1e1d1a" stroke-width="1"/>`;
  s += `<line x1="0" x2="${W}" y1="${y(d.threshold)}" y2="${y(d.threshold)}" stroke="#8a8476" stroke-dasharray="3 3"/>`;
  for (let t = 0; t <= total; t += 1) s += `<text x="${x(t)}" y="${H - 4}" font-size="10" fill="#8a8476" text-anchor="${t === 0 ? "start" : "middle"}">${t}s</text>`;
  return s + "</svg>";
}

async function askQuestion() {
  if (asking) return;
  const msg = $("#ask-msg"); const btn = $("#ask-btn");
  if (!navigator.mediaDevices || !window.MediaRecorder) { msg.textContent = "This browser cannot record audio here (use localhost or https)."; return; }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } }); }
  catch { msg.textContent = "Microphone permission was refused."; return; }
  asking = true; btn.disabled = true;
  const [question, answer] = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];

  // Loudness monitor: stop 1.5 s after the voice ends, or after 10 s
  const actx = new (window.AudioContext || window.webkitAudioContext)();
  const analyser = actx.createAnalyser(); analyser.fftSize = 1024;
  actx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  const chunks = []; const rec = new MediaRecorder(stream);
  rec.ondataavailable = (e) => chunks.push(e.data);
  let noise = null, spoke = false, quietSince = null, started = 0, timer = null;
  const level = () => { analyser.getFloatTimeDomainData(buf); return Math.sqrt(buf.reduce((s, v) => s + v * v, 0) / buf.length); };
  rec.onstart = () => {
    started = performance.now();
    $("#ask-q").textContent = question + " = ?"; $("#ask-state").textContent = "listening…"; $("#ask-box").hidden = false;
    const samples = [];
    timer = setInterval(() => {
      const t = performance.now() - started; const v = level();
      if (t < 300) { samples.push(v); return; }
      if (noise === null) noise = Math.max(0.004, samples.reduce((a, b) => a + b, 0) / Math.max(1, samples.length));
      if (v > noise * 4) { spoke = true; quietSince = null; $("#ask-state").textContent = "hearing you…"; }
      else if (spoke && quietSince === null) quietSince = t;
      if ((spoke && quietSince !== null && t - quietSince > 1500) || t > 10000) { clearInterval(timer); rec.stop(); }
    }, 50);
  };
  rec.onstop = async () => {
    clearInterval(timer); stream.getTracks().forEach((t) => t.stop());
    $("#ask-state").textContent = "measuring…";
    try {
      const audio = await actx.decodeAudioData(await new Blob(chunks).arrayBuffer());
      const form = new FormData(); form.append("audio", encodeWav(audio.getChannelData(0), audio.sampleRate), "answer.wav");
      const d = await api("/api/b5b/audio", form, true);
      setB5bSliders(d.features);
      const r = d.result; const f = d.features;
      const heard = d.b5a ? `${d.b5a.digit} (${pct(d.b5a.probability)}) – ${d.b5a.digit === answer ? "correct" : "the correct answer is " + answer}` : "—";
      $("#b5b-out").innerHTML = `<span class="label">Output · your answer to ${esc(question)}</span>
        <p class="verdict">${esc(r.state)}<span class="p">P(hesitant) = ${r.p_hesitant.toFixed(3)}</span></p>
        ${bars({ confident: 1 - r.p_hesitant, hesitant: r.p_hesitant }, { order: ["confident", "hesitant"] })}
        <span class="label" style="margin-top:16px">What was measured</span>
        ${voiceSvg(d.details)}
        <p class="muted">Line = loudness, dashed = speech threshold, black bars = speech, red = pauses, blue = time before answering.</p>
        ${sheet([["time before answering", f.response_delay.toFixed(2) + " s"], ["pauses", f.pause_count],
          ["speech rate", `${f.speech_rate.toFixed(2)} /s (${d.details.syllables} syllables)`], ["pitch variation", f.pitch_variation.toFixed(2) + " semitones"],
          ["B5a heard the digit", heard]])}`;
      msg.textContent = "Done. Try again and hesitate on purpose (“umm… seven?”).";
    } catch (e) { showError($("#b5b-out"), e); msg.textContent = ""; }
    finally { actx.close(); $("#ask-box").hidden = true; asking = false; btn.disabled = false; }
  };
  rec.start();
}
$("#ask-btn").addEventListener("click", askQuestion);

/* ------------------------------------------------------------ B6 */
let b6Answers = [];
const PLACEMENT = 5;                       // placement-test questions per topic
const topicCounts = () => Object.fromEntries(META.topics.map((t) => [t, b6Answers.filter((a) => a.topic === t).length]));
function coldStatus(n) {
  if (n === 0) return `<span class="st cold">cold start · class average</span>`;
  if (n < PLACEMENT) return `<span class="st warm">placement ${n}/${PLACEMENT}</span>`;
  return `<span class="st done">personal · ${n} answers</span>`;
}
function masteryBars(m) {
  const counts = topicCounts();
  return `<div class="bars status">` + META.topics.map((t) => `
    <div class="bar best"><span class="n">${t}</span><span class="t"><span class="f" style="width:${m[t]}%;background:${TOPIC_COLORS[t]}"></span></span>
    <span class="v">${m[t].toFixed(1)}%</span>${coldStatus(counts[t])}</div>`).join("") + "</div>";
}
function coldChart() {
  const curve = META.b6_cold_start; const ks = Object.keys(curve).map(Number).filter((k) => k <= 30).sort((a, b) => a - b);
  if (!ks.length) return `<p class="err">Cold start data missing – re-run export_models.py.</p>`;
  const W = 560, H = 290, L = 40, R = 14, T = 16, B = 36; const maxK = ks[ks.length - 1];
  const ymax = Math.ceil(Math.max(...ks.map((k) => Math.max(curve[k].model, curve[k].formula))) / 5) * 5;
  const x = (k) => L + (k / maxK) * (W - L - R); const y = (v) => T + (1 - v / ymax) * (H - T - B);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mastery error by number of answers">`;
  s += `<rect x="${x(0)}" y="${T}" width="${x(PLACEMENT) - x(0)}" height="${H - T - B}" fill="#a77d1c" opacity="0.12"/>
    <text x="${x(PLACEMENT / 2)}" y="${T - 4}" font-size="10" text-anchor="middle" fill="#a77d1c">placement test</text>`;
  for (let v = 0; v <= ymax; v += 5) s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#d6cfbd"/>
    <text x="${L - 6}" y="${y(v) + 4}" font-size="10" text-anchor="end" fill="#8a8476">${v}</text>`;
  for (let k = 0; k <= maxK; k += 5) s += `<text x="${x(k)}" y="${H - 20}" font-size="10" text-anchor="middle" fill="#8a8476">${k}</text>`;
  s += `<text x="${(L + W - R) / 2}" y="${H - 4}" font-size="10" text-anchor="middle" fill="#57534a">answers of this topic so far</text>`;
  s += `<text x="10" y="${(T + H - B) / 2}" font-size="10" text-anchor="middle" fill="#57534a" transform="rotate(-90 10 ${(T + H - B) / 2})">error (pp)</text>`;
  const line = (key) => ks.map((k) => `${x(k).toFixed(1)},${y(curve[k][key]).toFixed(1)}`).join(" ");
  s += `<polyline points="${line("formula")}" fill="none" stroke="#8a8476" stroke-width="1.5" stroke-dasharray="4 3"/>`;
  s += `<polyline points="${line("model")}" fill="none" stroke="#1e1d1a" stroke-width="2"/>`;
  const counts = topicCounts();                      // where is the student of the first tab on the curve?
  META.topics.forEach((t, i) => {
    const k = Math.min(counts[t], maxK); const v = curve[k] ? curve[k].model : curve[maxK].model;
    s += `<circle cx="${x(k)}" cy="${y(v) - i * 0.01}" r="5" fill="${TOPIC_COLORS[t]}" stroke="#f5f2ea" stroke-width="1.5"><title>${t}: ${counts[t]} answers</title></circle>`;
  });
  return s + "</svg>";
}
function renderCold() {
  if (!META) return;
  const c = META.b6_cold_start; const counts = topicCounts();
  $("#b6-cold-status").innerHTML = `<div class="bars status">` + META.topics.map((t) =>
    `<div class="bar"><span class="n">${t}</span><span class="t"><span class="f" style="width:${Math.min(100, (counts[t] / PLACEMENT) * 100)}%;background:${TOPIC_COLORS[t]}"></span></span>
     <span class="v">${counts[t]}</span>${coldStatus(counts[t])}</div>`).join("") + "</div>";
  $("#b6-cold-out").innerHTML = `<span class="label">Average error of the mastery estimate vs. answers seen (notebook B6.7)</span>
    ${coldChart()}
    <div class="legend"><span><i style="border-color:#1e1d1a"></i>B6 model</span><span><i class="dot" style="border-color:#8a8476"></i>simple formula (correct ÷ total)</span>
      <span>dots = your student's topics</span></div>
    ${sheet([["0 answers (cold start)", `${c[0].model.toFixed(1)} pp`], ["after 5 (placement test)", `${c[5].model.toFixed(1)} pp`],
      ["after 20", `${c[20].model.toFixed(1)} pp`], ["simple formula after 5", `${c[5].formula.toFixed(1)} pp`]])}
    <p class="muted">At 0 answers the model is not guessing blindly: it uses what it knows about the average student and the topic (fractions are harder than addition). The simple formula has nothing and starts at 50%.</p>`;
}
$("#b6-placement").addEventListener("click", () => {
  // 5 medium answers per topic; a typical new student: good at addition, weaker at fractions
  const p = { addition: 0.8, subtraction: 0.7, multiplication: 0.5, division: 0.5, fractions: 0.4 };
  const qs = META.topics.flatMap((t) => Array(PLACEMENT).fill(t)).sort(() => Math.random() - 0.5);
  qs.forEach((t) => b6Answers.push({ topic: t, difficulty: 2, attention: "attentive", answer_mode: "handwriting", is_hesitant: false, is_correct: Math.random() < p[t] }));
  renderB6();
});
async function renderB6() {
  renderCold();
  if (!META) return;
  const log = $("#b6-log");
  log.innerHTML = b6Answers.slice().reverse().map((a, i) => `<tr><td>${b6Answers.length - i}</td><td>${a.topic}</td><td>${a.difficulty}</td>
    <td>${a.attention}</td><td>${a.answer_mode}${a.is_hesitant ? " (hes.)" : ""}</td>
    <td class="${a.is_correct ? "ok" : "no"}">${a.is_correct ? "correct" : "wrong"}</td></tr>`).join("") ||
    `<tr><td colspan="6" class="muted">No answers yet – a brand-new student.</td></tr>`;
  const out = $("#b6-out");
  try {
    const d = await api("/api/b6/mastery", { answers: b6Answers });
    out.innerHTML = `<span class="label">Output · mastery after ${b6Answers.length} answer${b6Answers.length === 1 ? "" : "s"}</span>
      ${masteryBars(d.mastery)}
      <p class="muted">${b6Answers.length === 0 ? "<b>Cold start:</b> no history yet, so every topic shows the average student. Fractions start lowest because they are the hardest topic for everybody. Add about 5 answers to a topic (or run the placement test in the Cold start tab) and that topic becomes personal."
        : "Each bar is P(correct) for a medium question while attentive. A topic with fewer than 5 answers still leans on the class average (see the Cold start tab)."}</p>`;
  } catch (e) { showError(out, e); }
}
function addB6(correct, n = 1) {
  for (let i = 0; i < n; i++) {
    const mode = $("#b6-mode").value;
    b6Answers.push({ topic: $("#b6-topic").value, difficulty: +$("#b6-diff").value, attention: $("#b6-att").value,
      answer_mode: mode, is_hesitant: mode === "speech" && $("#b6-hes").checked, is_correct: correct });
  }
  renderB6();
}
$$("[data-b6]").forEach((b) => b.addEventListener("click", () => addB6(b.dataset.b6 === "1")));
$("#b6-burst").addEventListener("click", () => addB6(true, 5));
$("#b6-reset").addEventListener("click", () => { b6Answers = []; renderB6(); });
$("#b6-mode").addEventListener("change", (e) => { const s = e.target.value === "speech"; $("#b6-hes").disabled = !s; if (!s) $("#b6-hes").checked = false; });
$$(".tabs button").forEach((t) => t.addEventListener("click", () => {
  $$(".tabs button").forEach((x) => x.setAttribute("aria-selected", x === t));
  $$("#b6 .panel").forEach((p) => (p.hidden = p.id !== t.dataset.tab));
}));

let b6Seed = 7;
function chart(d) {
  const W = 560, H = 300, L = 40, R = 12, T = 12, B = 34;
  const maxDay = Math.max(...d.days, 1);
  const x = (day) => L + (day / maxDay) * (W - L - R); const y = (v) => T + (1 - v / 100) * (H - T - B);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mastery over 28 days">`;
  for (let v = 0; v <= 100; v += 25) s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#d6cfbd" stroke-width="1"/>
    <text x="${L - 6}" y="${y(v) + 4}" font-size="10" text-anchor="end" fill="#8a8476">${v}</text>`;
  for (let day = 0; day <= maxDay; day += 7) s += `<text x="${x(day)}" y="${H - 14}" font-size="10" text-anchor="middle" fill="#8a8476">${day}</text>`;
  s += `<text x="${(L + W - R) / 2}" y="${H - 1}" font-size="10" text-anchor="middle" fill="#57534a">day (0 = placement test)</text>`;
  META.topics.forEach((t) => {
    const line = (key) => d.days.map((day, i) => `${x(day).toFixed(1)},${y(d[key][i][t]).toFixed(1)}`).join(" ");
    s += `<polyline points="${line("true")}" fill="none" stroke="${TOPIC_COLORS[t]}" stroke-width="1.5" stroke-dasharray="2 3" opacity="0.8"/>`;
    s += `<polyline points="${line("estimated")}" fill="none" stroke="${TOPIC_COLORS[t]}" stroke-width="2"/>`;
  });
  return s + "</svg>";
}
async function runB6Sim() {
  const out = $("#b6-sim-out"); $("#b6-seed-v").textContent = "seed " + b6Seed;
  out.innerHTML = `<p class="empty">Simulating…</p>`;
  try {
    const d = await api("/api/b6/simulate", { ...fieldValues($("#b6-sim-in")), seed: b6Seed });
    const lastE = d.estimated[d.estimated.length - 1]; const lastT = d.true[d.true.length - 1];
    const err = META.topics.reduce((s, t) => s + Math.abs(lastE[t] - lastT[t]), 0) / META.topics.length;
    out.innerHTML = `<span class="label">Output · ${d.answers} answers, ${pct(d.accuracy)} correct</span>
      ${chart(d)}
      <div class="legend">${META.topics.map((t) => `<span><i style="border-color:${TOPIC_COLORS[t]}"></i>${t}</span>`).join("")}
        <span><i class="dot" style="border-color:#57534a"></i>true (hidden)</span></div>
      <table class="compare"><tr><th>topic</th><th>estimated</th><th>true</th></tr>
        ${META.topics.map((t) => `<tr><td>${t}</td><td class="mono">${lastE[t].toFixed(1)}%</td><td class="mono">${lastT[t].toFixed(1)}%</td></tr>`).join("")}</table>
      <p class="muted">Average distance after 28 days: ${err.toFixed(1)} percentage points (notebook, 40 test students: ${META.b6_mae_model} pp; simple correct ÷ total formula: ${META.b6_mae_formula} pp).</p>`;
  } catch (e) { showError(out, e); }
}
$("#b6-run").addEventListener("click", runB6Sim);
$("#b6-seed").addEventListener("click", () => { b6Seed = Math.floor(Math.random() * 100000); runB6Sim(); });

/* ------------------------------------------------------------ B7 */
const ERROR_LABELS = { forgot_carry: "forgot to carry", careless_slip: "careless slip", wrong_operation: "wrong operation", fraction_rule: "fraction rule" };
async function runB7() {
  const out = $("#b7-out");
  try {
    const d = await api("/api/b7", { operation: $("#b7-op").value, a: $("#b7-a").value, b: $("#b7-b").value, given: $("#b7-given").value });
    if (!d.result) {
      out.innerHTML = `<span class="label">Output</span><p class="verdict small">That answer is correct.</p>
        <p class="muted">B7 only looks at wrong answers. Correct result: <span class="mono">${esc(d.correct)}</span></p>`;
      return;
    }
    const f = d.features;
    out.innerHTML = `<span class="label">Output · cluster</span>
      <p class="verdict">${esc(ERROR_LABELS[d.result.error_type])}</p>
      <div class="callout"><span class="label">Hint for the teacher</span>${esc(d.result.hint)}</div>
      <span class="label" style="margin-top:16px">Shape of the mistake (what K-Means sees, before scaling)</span>
      ${sheet([["correct answer", esc(d.correct)], ["question needs a carry", d.needs_carry ? "yes" : "no"],
        ["size_ratio_log  |log₂(given ÷ correct)|", f.size_ratio_log.toFixed(3)],
        ["error_steps_log  log₁₀ of steps off", f.error_steps_log.toFixed(3)],
        ["diff_is_tens  off by 10, 20, 100 …", f.diff_is_tens],
        ["same_denominator", f.same_denominator]])}`;
  } catch (e) { showError(out, e); }
}
function setB7(op, a, b, given) { $("#b7-op").value = op; $("#b7-a").value = a; $("#b7-b").value = b; $("#b7-given").value = given; }
$("#b7-random").addEventListener("click", async () => {
  try {
    const d = await api("/api/b7/random", {});
    setB7(d.operation, d.a, d.b, d.given);
    $("#b7-truth").textContent = "generator used: " + ERROR_LABELS[d.hidden_type] + " (hidden from B7)";
    runB7();
  } catch (e) { showError($("#b7-out"), e); }
});
$$("#b7 input, #b7 select").forEach((el) => el.addEventListener("input", () => ($("#b7-truth").textContent = "")));
$$("#b7 input").forEach((el) => el.addEventListener("keydown", (e) => e.key === "Enter" && runB7()));

/* ------------------------------------------------------------ B8 */
const B8_LABELS = { avg_accuracy: "accuracy", learning_speed: "learning speed", avg_attention: "attention", spoken_answer_ratio: "spoken answers" };
function zRow(label, z, center) {
  const clamp = (v) => Math.max(-2.5, Math.min(2.5, v)); const pos = (v) => 50 + (clamp(v) / 2.5) * 50;
  const left = Math.min(pos(0), pos(z)); const width = Math.abs(pos(z) - pos(0));
  return `<div class="z"><span>${label}</span><span class="axis"><span class="s" style="left:${left}%;width:${width}%"></span>
    <span class="c" style="left:calc(${pos(center)}% - 1px)" title="profile centre"></span></span><span class="v">${z >= 0 ? "+" : ""}${z.toFixed(2)}</span></div>`;
}
const runB8 = debounce(async () => {
  const out = $("#b8-out");
  try {
    const d = await api("/api/b8", { ...fieldValues($("#b8-in")), characteristic_error: $("#b8-err").value });
    const r = d.result; const center = META.b8_centers_z[String(r.profile_id)];
    out.innerHTML = `<span class="label">Output · profile ${r.profile_id}</span>
      <p class="verdict small">${esc(r.profile)}</p>
      <span class="label" style="margin-top:14px">Recommendations</span>
      <ol class="recs">${r.recommendations.map((x) => `<li>${esc(x)}</li>`).join("")}<li>${esc(r.error_hint)} <span class="muted">(from B7)</span></li></ol>
      <span class="label" style="margin-top:16px">This student vs. the class average (black bar, in standard deviations) · red tick = profile centre</span>
      <div class="zbars">${Object.keys(B8_LABELS).map((k) => zRow(B8_LABELS[k], d.student_z[k], center[k])).join("")}</div>
      <table class="profiles"><tr><th>id</th><th>profile</th><th>students</th></tr>
        ${Object.entries(META.profiles).map(([id, p]) => `<tr class="${+id === r.profile_id ? "me" : ""}"><td class="mono">${id}</td>
        <td>${esc(p.name)}</td><td class="mono">${META.b8_sizes[id]}</td></tr>`).join("")}</table>`;
  } catch (e) { showError(out, e); }
});

/* ------------------------------------------------------------ wiring */
$$("[data-run]").forEach((b) => b.addEventListener("click", () => ({ b1: runB1, b2: runB2, b3: runB3, b7: runB7 }[b.dataset.run])()));
$$("[data-fill]").forEach((b) => b.addEventListener("click", () => {
  $("#" + b.dataset.fill).value = b.textContent; (b.dataset.fill === "b1-msg" ? runB1 : runB2)();
}));
$("#b1-msg").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); runB1(); } });
$("#b2-msg").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); runB2(); } });
$$("[data-b4]").forEach((b) => b.addEventListener("click", () => setFields($("#b4-in"), ["screen_gaze_ratio", "head_angle", "blink_rate"], b.dataset.b4.split(","))));
$$("[data-b5b]").forEach((b) => b.addEventListener("click", () => setFields($("#b5b-in"), ["speech_rate", "pause_count", "response_delay", "pitch_variation"], b.dataset.b5b.split(","))));
$$("[data-b7]").forEach((b) => b.addEventListener("click", () => { setB7(...b.dataset.b7.split(",")); $("#b7-truth").textContent = ""; runB7(); }));
$$("[data-b8]").forEach((b) => b.addEventListener("click", () => {
  const v = b.dataset.b8.split(","); $("#b8-err").value = v[4];
  setFields($("#b8-in"), ["avg_accuracy", "learning_speed", "avg_attention", "spoken_answer_ratio"], v.slice(0, 4));
}));
wireFields($("#b4-in"), runB4); wireFields($("#b5b-in"), runB5b); wireFields($("#b6-sim-in"), () => {}); wireFields($("#b8-in"), runB8);
$("#b8-err").addEventListener("change", runB8);

async function init() {
  try {
    META = await (await fetch("/api/meta")).json();
  } catch { $("#status").textContent = "server not reachable"; return; }
  $("#status").textContent = "models loaded";
  $("#b6-topic").innerHTML = META.topics.map((t) => `<option>${t}</option>`).join("");
  $("#b8-err").innerHTML = META.error_types.map((t) => `<option value="${t}">${ERROR_LABELS[t]}</option>`).join("");
  $("#b8-err").value = "forgot_carry";
  $$("[data-metric]").forEach((el) => { const v = META.metrics[el.dataset.metric]; if (v != null) el.textContent = "test accuracy " + pct(v); });
  $("#b6-metric").textContent = `mean error ${META.b6_mae_model} pp`;
  $("#samples").innerHTML = META.samples.map((s) => `<button data-sample="${esc(s)}">${esc(s.split("_")[0])}</button>`).join("");
  $$("[data-sample]").forEach((b) => b.addEventListener("click", async () => {
    try { showB5a(await api("/api/b5a/sample", { name: b.dataset.sample }), "sample " + b.dataset.sample); } catch (e) { showError($("#b5a-out"), e); }
  }));
  const m = META.metrics;
  const rows = [["B1 Interest", "test accuracy", pct(m["B1"])], ["B2 Struggle topic", "test accuracy", pct(m["B2"])],
    ["B3 Handwritten digit", "test accuracy (MNIST / 8×8)", `${pct(m["B3 (MNIST)"])} / ${pct(m["B3 (8x8)"])}`],
    ["B4 Attention", "test accuracy", pct(m["B4"])], ["B5a Spoken digit", "test accuracy (seen speakers)", pct(m["B5a"])],
    ["B5b Confidence", "test accuracy", pct(m["B5b"])],
    ["B6 Mastery", "mean error vs. true mastery", `${META.b6_mae_model} pp (formula ${META.b6_mae_formula} pp)`],
    ["B7 Error types", "adjusted Rand index vs. hidden types", "0.77"], ["B8 Profiles", "silhouette (k = 4)", "≈ 0.19"]];
  $("#metrics").innerHTML += rows.map(([a, b, c]) => `<tr><td>${a}</td><td>${b}</td><td class="mono">${c}</td></tr>`).join("");
  route();
}
init();

/* Math Buddy – the lesson page: the whole learning loop. All decisions are made on the server (webapp/lesson.py),
   which calls the notebook's block functions; this file only shows the conversation and collects the answers.
   The server also decides HOW each question is answered (prompt.mode): one digit -> voice (B5a + B5b),
   more digits -> handwriting (B3), fractions and chat -> keyboard.
   Uses $, $$, esc, api, pct, bars, encodeWav, drawPixels, TOPIC_COLORS from app.js. */
"use strict";

const LS = { id: null, prompt: null, state: null, mode: "keyboard", read: null, hesitant: -1, busy: false, side: null };
const MODES = {
  keyboard: "⌨  Type your answer", speech: "🎤  Say your answer", handwriting: "✎  Write your answer", break: "☕  Short break",
};
const VIA = { keyboard: "typed", handwriting: "written · B3", speech: "spoken · B5a + B5b" };
const CHAT_EXAMPLES = {
  chat_interest: ["I played football with my friends, it was awesome!", "I fed my rabbit and played with my puppy",
    "We baked cookies with grandma", "I hate football, it's so boring"],
  chat_topic: ["I don't understand addition at all", "Multiplication is so hard for me",
    "Fractions are confusing", "Taking away numbers is hard"],
};

/* ------------------------------------------------------------ conversation and trace */
function speak(text) {
  if (!$("#ls-tts").checked || !window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text.replace(/\(.*?\)/g, "").replace(/×/g, " times ").replace(/÷/g, " divided by "));
  u.lang = "en-US"; u.rate = 0.95;
  const voice = speechSynthesis.getVoices().find((v) => v.lang === "en-US");
  if (voice) u.voice = voice;
  speechSynthesis.speak(u);
}

function addEvents(events) {
  const chat = $("#ls-chat"); const trace = $("#ls-trace");
  events.forEach((e) => {
    const div = document.createElement("div");
    if (e.type === "tutor" || e.type === "child" || e.type === "tip") {
      if (e.type === "tutor") {
        div.className = "msg tutor"; div.textContent = e.text;
        if (e.image) { const c = document.createElement("canvas"); c.className = "digit-img"; drawPixels(c, e.image, 255); div.appendChild(c); }
        speak(e.text);
      } else if (e.type === "child") {
        div.className = "msg child"; div.innerHTML = `${esc(e.text)}<small>${esc(VIA[e.via] || e.via)}</small>`;
      } else {
        div.className = "msg tip"; div.innerHTML = `<b>Let's practise: ${esc(e.name)}.</b> ${esc(e.text)}`;
      }
      chat.appendChild(div);
    } else {
      div.className = e.type === "arrow" ? "trace" : "trace note";
      div.innerHTML = e.type === "arrow"
        ? `<b>${esc(e.from)} → ${esc(e.to)}</b> ${esc(e.message)}${e.fn ? ` <code>${esc(e.fn)}</code>` : ""}`
        : esc(e.text);
      trace.appendChild(div);
    }
  });
  chat.scrollTop = chat.scrollHeight; trace.scrollTop = trace.scrollHeight;
}

/* ------------------------------------------------------------ one answer area, chosen by the server */
function render(d) {
  LS.id = d.id; LS.prompt = d.prompt; LS.state = d.state;
  addEvents(d.events);
  const chatting = d.state.startsWith("chat");
  const mode = d.state === "break" ? "break" : chatting ? "keyboard" : (d.prompt && d.prompt.mode) || "keyboard";
  showMode(mode, d.prompt ? d.prompt.why : "");
  $("#ls-examples").innerHTML = chatting
    ? (CHAT_EXAMPLES[d.state] || []).map((t) => `<button class="link" data-ls-msg="${esc(t)}">${esc(t)}</button>`).join("") : "";
  $$("[data-ls-msg]").forEach((b) => b.addEventListener("click", () => { $("#ls-text").value = b.dataset.lsMsg; sendText(); }));
  $("#ls-text").placeholder = chatting ? "Write to Math Buddy…" : d.prompt && d.prompt.fraction ? "e.g. 5/6" : "your answer";
  $("#ls-skip").hidden = d.state !== "practice" && d.state !== "placement";
  $("#ls-skip").textContent = d.state === "placement" ? "skip the rest of the placement test" : "skip this practice step";
  const pl = d.panel.placement;
  $("#ls-banner").hidden = !pl;
  if (pl) {
    $("#ls-banner-text").textContent = `· ${pl.topic} · question ${pl.done + 1} of ${pl.total} · which parts of ${pl.topic} do you already know?`;
    $("#ls-banner-bar").style.width = (pl.done / pl.total) * 100 + "%";
  }
  renderSide(d.panel, d.state);
}

function showMode(mode, why) {
  LS.mode = mode === "break" ? "keyboard" : mode; LS.read = null; LS.hesitant = -1;
  $("#ls-mode").textContent = MODES[mode];
  $("#ls-why").textContent = why || "";
  ["keyboard", "speech", "handwriting", "break"].forEach((m) => { $("#pane-" + m).hidden = m !== mode; });
  $("#ls-readback").hidden = true; $("#ls-value").value = ""; $("#ls-text").value = "";
  $("#ls-type-instead").hidden = mode !== "speech" && mode !== "handwriting";
  $("#ls-rec-state").textContent = "Press, then say one English digit (zero … nine).";
  clearBoxes();
  if (mode === "keyboard") $("#ls-text").focus({ preventScroll: true });
}

function showReading(html, value) {
  // B3 / B5a have read the answer: show it, let the child fix a misreading, then send
  $("#ls-read-text").innerHTML = html; $("#ls-value").value = value; $("#ls-readback").hidden = false;
  $("#ls-send").focus({ preventScroll: true });
}

/* ------------------------------------------------------------ side panel: progress / diagnosis / code trace */
function selectSide(name) {
  LS.side = name;
  $$("[data-side]").forEach((b) => b.setAttribute("aria-selected", b.dataset.side === name));
  ["progress", "diagnosis", "trace"].forEach((n) => { $("#side-" + n).hidden = n !== name; });
}

function renderSide(p, state) {
  const stateNames = { chat_interest: "chatting (B1)", chat_topic: "chatting (B2)", question: "question",
    retest: "re-test after practice", probe: "B9 follow-up question", placement: "placement test (cold start)", practice: "practising the missing skill", break: "short break" };
  $("#ls-facts").innerHTML = [["now", (stateNames[state] || state) + (p.placement ? ` · ${p.placement.done + 1} of ${p.placement.total}` : "")], ["interest (B1)", p.interest || "—"],
    ["topic · difficulty", p.topic ? `${p.topic} · ${p.difficulty} of 3` : "—"], ["graded answers", p.answers],
    ["diagnoses (B9)", p.diagnoses]].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  if (!$("#ls-topic").options.length) $("#ls-topic").innerHTML = Object.keys(p.mastery).map((t) => `<option>${t}</option>`).join("");
  if (p.topic) $("#ls-topic").value = p.topic;
  $("#ls-topic").disabled = !(state === "question" && p.topic);

  const result = p.placement_result || [];
  $("#ls-placement").hidden = !result.length;
  $("#ls-skills").innerHTML = result.map((r) => `<li class="${r.result === null ? "todo" : r.result ? "yes" : "no"}">
    <span>${r.result === null ? "·" : r.result === 1 ? "✓" : r.result ? "✓?" : "✗"}</span> ${esc(r.name)}</li>`).join("");
  const counts = p.topic_answers || {};
  $("#ls-mastery").innerHTML = Object.keys(p.mastery).map((t) => {
    const now = p.mastery[t], start = p.mastery_start[t], diff = now - start, n = counts[t] || 0;
    if (!n) return `<div class="bar mbar unknown ${t === p.topic ? "best" : ""}"><span class="n">${t}</span>
      <span class="t"><span class="g" style="width:${start}%"></span></span>
      <span class="v">? <small>avg ${start.toFixed(0)}%</small></span></div>`;
    return `<div class="bar mbar ${t === p.topic ? "best" : ""}"><span class="n">${t} <small>${n}</small></span>
      <span class="t"><span class="g" style="width:${start}%"></span><span class="f" style="width:${now}%"></span></span>
      <span class="v">${now.toFixed(0)}%${Math.abs(diff) >= 0.5 ? ` <small class="${diff > 0 ? "ok" : "no"}">${diff > 0 ? "+" : ""}${diff.toFixed(0)}</small>` : ""}</span></div>`;
  }).join("") + `<p class="muted">? = no answers in this topic yet: B6 knows only the class average (grey) – the cold start.
    The small number is the child's answers in the topic; after about 5 the estimate is personal (error 12.4 → 8.9 points, notebook B6.7).
    A topic counts as learned at ${p.mastered_at} %.</p>`;

  const pace = p.pace || {}; const cost = p.last_cost;
  $("#ls-pace").innerHTML = [["profile (B8)", p.profile || "not yet (6 answers + 1 error)"],
    ["level up after", `${pace.level_up_after} correct in a row`], ["break when distraction costs", `≥ ${pace.break_cost} points`],
    ["attention now (B4 → B6)", cost ? `${cost.attention}: −${cost.cost} points` : "attentive"]]
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");

  const diagnosing = !!p.belief; const practising = !!p.path;
  $("#ls-diag").hidden = !diagnosing; $("#ls-path").hidden = !practising;
  $("#ls-diag-empty").hidden = diagnosing || practising;
  $("#ls-diag-dot").textContent = diagnosing || practising ? "●" : "";
  if (diagnosing) {
    $("#ls-belief").innerHTML = bars(Object.fromEntries(p.belief.map((b) => [b.cause, b.p])), { order: p.belief.map((b) => b.cause) });
    $("#ls-asked").textContent = p.asked.length
      ? "answers so far: " + p.asked.map(([s, v]) => `${s} ${v === 1 ? "✓" : v === 0.5 ? "✓ unsure" : "✗"}`).join(", ")
      : "first guess of the decision tree · B9 stops at 80 %";
  }
  if (practising) {
    $("#ls-steps").innerHTML = p.path.map((s) => `<li class="${s.status}">${esc(s.name)}
      ${s.status === "now" ? `<span class="mono">${"●".repeat(p.streak)}${"○".repeat(Math.max(0, 3 - p.streak))}</span>` : s.status === "done" ? "✓" : ""}</li>`).join("")
      + `<li class="next">the first kind of question again</li>`;
  }
  if (LS.side !== "trace") selectSide(diagnosing || practising ? "diagnosis" : "progress");
  $("#ls-arrows-bar").style.width = (p.arrows_used / p.arrows_total) * 100 + "%";
  $("#ls-arrows").textContent = `${p.arrows_used} of ${p.arrows_total} diagram arrows used`;
  $("#ls-arrows-n").textContent = `${p.arrows_used}/${p.arrows_total}`;
}

/* ------------------------------------------------------------ talking to the server */
async function call(path, body) {
  if (LS.busy) return; LS.busy = true;
  try { render(await api(path, { id: LS.id, ...body })); }
  catch (e) { $("#ls-why").textContent = "⚠ " + (e.message || e); }
  finally { LS.busy = false; }
}
async function startLesson() {
  $("#ls-chat").innerHTML = ""; $("#ls-trace").innerHTML = ""; LS.id = null; LS.side = null;
  showView("lesson");
  if (window.speechSynthesis) speechSynthesis.cancel();
  await call("/api/lesson/start", {});
}
function camera() {
  const choice = $("#ls-cam").value;
  if (choice === "live" && window.cameraRunning && window.cameraRunning() && window.lastCameraFeatures) return { features: window.lastCameraFeatures };
  return { preset: choice === "live" ? "attentive" : choice };
}
function sendAnswer(value) {
  value = String(value).trim(); if (!value) return;
  if (window.speechSynthesis) speechSynthesis.cancel();
  call("/api/lesson/answer", { value, mode: LS.mode, hesitant: LS.hesitant, read: LS.read, camera: camera() });
}
function sendText() {
  const text = $("#ls-text").value.trim(); if (!text) return;
  if (LS.state && LS.state.startsWith("chat")) { $("#ls-text").value = ""; call("/api/lesson/chat", { message: text }); }
  else sendAnswer(text);
}

/* ------------------------------------------------------------ handwriting: one B3 reading per box */
const BOXES = 4;
function makeBoxes() {
  const row = $("#ls-boxes"); row.innerHTML = "";
  for (let i = 0; i < BOXES; i++) {
    const c = document.createElement("canvas"); c.width = c.height = 160; c.className = "box-pad";
    const g = c.getContext("2d"); let down = false, last = null;
    const pt = (e) => { const r = c.getBoundingClientRect(); return [(e.clientX - r.left) * (160 / r.width), (e.clientY - r.top) * (160 / r.height)]; };
    const draw = (p) => {
      g.strokeStyle = "#1e1d1a"; g.lineWidth = 11; g.lineCap = "round"; g.lineJoin = "round";
      g.beginPath(); g.moveTo(last[0], last[1]); g.lineTo(p[0], p[1]); g.stroke(); last = p; c.dataset.ink = "1";
    };
    c.addEventListener("pointerdown", (e) => { down = true; last = pt(e); c.setPointerCapture(e.pointerId); draw(last); });
    c.addEventListener("pointermove", (e) => { if (down) draw(pt(e)); });
    const up = () => { down = false; };
    c.addEventListener("pointerup", up); c.addEventListener("pointercancel", up);
    row.appendChild(c);
  }
}
function clearBoxes() { $$("#ls-boxes canvas").forEach((c) => { c.getContext("2d").clearRect(0, 0, 160, 160); delete c.dataset.ink; }); }
function boxInk(c) {
  const small = document.createElement("canvas"); small.width = small.height = 140;
  small.getContext("2d").drawImage(c, 0, 0, 140, 140);
  const px = small.getContext("2d").getImageData(0, 0, 140, 140).data; const rows = [];
  for (let y = 0; y < 140; y++) { const row = []; for (let x = 0; x < 140; x++) row.push(px[(y * 140 + x) * 4 + 3]); rows.push(row); }
  return rows;
}
async function readWriting() {
  const used = $$("#ls-boxes canvas").filter((c) => c.dataset.ink);
  if (!used.length) { $("#ls-why").textContent = "Write the answer in the boxes first (one digit per box)."; return; }
  try {
    const d = await api("/api/lesson/read/handwriting", { boxes: used.map(boxInk) });
    LS.read = { read: d.value, boxes: used.length, p: d.digits.map((x) => x.probability.toFixed(2)).join(", ") };
    showReading(`B3 read <b>${esc(d.value)}</b> <span class="muted">(${d.digits.map((x) => `${x.digit}: ${pct(x.probability)}`).join(", ")})</span>`, d.value);
  } catch (e) { $("#ls-why").textContent = "⚠ " + e.message; }
}

/* ------------------------------------------------------------ voice: B5a reads the digit, B5b the hesitation */
let listening = false;
function recordUntilQuiet(setState) {
  // Records from the moment it is called until 1.2 s after the voice stops (max 10 s); resolves with a WAV blob
  return new Promise(async (resolve, reject) => {
    if (!navigator.mediaDevices || !window.MediaRecorder) { reject(new Error("This browser cannot record audio here – type instead.")); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } }); }
    catch { reject(new Error("Microphone permission was refused – type instead.")); return; }
    if (window.speechSynthesis) speechSynthesis.cancel();
    const actx = new (window.AudioContext || window.webkitAudioContext)();
    const analyser = actx.createAnalyser(); analyser.fftSize = 1024; actx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize); const chunks = []; const rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => chunks.push(e.data);
    let noise = null, spoke = false, quietSince = null, started = 0, timer = null; const samples = [];
    const level = () => { analyser.getFloatTimeDomainData(buf); return Math.sqrt(buf.reduce((s, v) => s + v * v, 0) / buf.length); };
    rec.onstart = () => {
      started = performance.now(); setState("listening…");
      timer = setInterval(() => {
        const t = performance.now() - started; const v = level();
        if (t < 300) { samples.push(v); return; }
        if (noise === null) noise = Math.max(0.004, samples.reduce((a, b) => a + b, 0) / Math.max(1, samples.length));
        if (v > noise * 4) { spoke = true; quietSince = null; setState("hearing you…"); }
        else if (spoke && quietSince === null) quietSince = t;
        if ((spoke && quietSince !== null && t - quietSince > 1200) || t > 10000) { clearInterval(timer); rec.stop(); }
      }, 50);
    };
    rec.onstop = async () => {
      clearInterval(timer); stream.getTracks().forEach((t) => t.stop());
      try {
        const audio = await actx.decodeAudioData(await new Blob(chunks).arrayBuffer());
        resolve(encodeWav(audio.getChannelData(0), audio.sampleRate));
      } catch (e) { reject(e); } finally { actx.close(); }
    };
    rec.start();
  });
}

async function sayAnswer() {
  if (listening) return;
  listening = true; $("#ls-rec").classList.add("live"); $("#ls-mic").disabled = true;
  try {
    const wav = await recordUntilQuiet((t) => { $("#ls-rec-state").textContent = t; });
    $("#ls-rec-state").textContent = "B5a and B5b are listening…";
    const form = new FormData(); form.append("audio", wav, "answer.wav");
    const d = await api("/api/lesson/read/voice", form, true);
    LS.hesitant = d.state === "hesitant" ? 1 : 0;
    LS.read = { read: d.value, p: d.probability.toFixed(2), p_hesitant: d.p_hesitant, personal: d.personal };
    $("#ls-rec-state").textContent = "Press again to repeat." + (d.personal ? "" : " Misheard? Use “Teach me your voice” above.");
    showReading(`B5a${d.personal ? " (your voice model)" : ""} heard <b>${esc(d.value)}</b> <span class="muted">(${pct(d.probability)})</span> · B5b: <b>${esc(d.state)}</b>
      <span class="muted">(P(hesitant) ${d.p_hesitant.toFixed(2)}, delay ${d.features.response_delay} s, ${d.features.pause_count} pauses)</span>`, d.value);
  } catch (e) { $("#ls-rec-state").textContent = "⚠ " + (e.message || e); }
  finally { listening = false; $("#ls-rec").classList.remove("live"); $("#ls-mic").disabled = false; }
}

/* ------------------------------------------------------------ teacher dashboard (its own view) */
function showView(name) {
  $("#ls-view").hidden = name !== "lesson"; $("#ls-dash").hidden = name !== "dashboard"; $("#ls-voice").hidden = name !== "voice";
  $("#ls-dash-btn").textContent = name === "dashboard" ? "← Back to the lesson" : "Teacher dashboard";
  $("#ls-voice-btn").textContent = name === "voice" ? "← Back to the lesson" : "🎤 Teach me your voice";
}

/* ------------------------------------------------------------ voice calibration (B5a.9b) */
const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];
const ROUNDS = 3;
const VC = { counts: Array(10).fill(0), digit: 0, busy: false };
function nextDigit() {
  // the digit with the fewest recordings, lowest first
  const least = Math.min(...VC.counts); VC.digit = VC.counts.indexOf(least);
  $("#vc-digit").textContent = VC.digit; $("#vc-word").textContent = `“${WORDS[VC.digit]}”`;
}
function renderVoice(status) {
  $("#vc-grid").innerHTML = VC.counts.map((n, d) => `<div class="${n >= ROUNDS ? "full" : n ? "some" : ""}"><b>${d}</b><span>${"●".repeat(Math.min(n, ROUNDS))}${"○".repeat(Math.max(0, ROUNDS - n))}</span></div>`).join("");
  $("#vc-train").disabled = VC.counts.some((n) => n === 0);
  const total = VC.counts.reduce((a, b) => a + b, 0);
  if (status) $("#vc-status").textContent = status;
  else $("#vc-status").textContent = total ? `${total} recordings. ${VC.counts.every((n) => n >= ROUNDS) ? "Done – press “Train B5a with my voice”." : `Aim: ${ROUNDS} per digit.`}` : "";
  nextDigit();
}
async function openVoice() {
  if (!$("#ls-voice").hidden) { showView("lesson"); return; }
  const d = await (await fetch("/api/voice")).json();
  VC.counts = d.counts; renderVoice(d.personal ? `B5a already uses your voice (${d.recordings} recordings). You can add more and train again.` : "");
  showView("voice");
}
async function recordCalibration() {
  if (VC.busy) return; VC.busy = true;
  $("#vc-recst").classList.add("live"); $("#vc-rec").disabled = true;
  try {
    const wav = await recordUntilQuiet((t) => { $("#vc-state").textContent = t; });
    $("#vc-state").textContent = "saving…";
    const form = new FormData(); form.append("audio", wav, "digit.wav"); form.append("digit", VC.digit);
    const d = await api("/api/voice/sample", form, true);
    $("#vc-heard").textContent = `You said ${VC.digit}; B5a${d.heard.personal ? " (your model)" : ""} heard ${d.heard.digit} (${pct(d.heard.probability)}) ${d.heard.digit === VC.digit ? "✓" : "✗ – now it learns this one"}`;
    VC.counts = d.counts; $("#vc-state").textContent = "Press, say the digit once, then wait."; renderVoice();
  } catch (e) { $("#vc-state").textContent = "⚠ " + (e.message || e); }
  finally { VC.busy = false; $("#vc-recst").classList.remove("live"); $("#vc-rec").disabled = false; }
}
async function trainVoice() {
  $("#vc-status").textContent = "Training B5a with your voice…";
  try {
    const d = await api("/api/voice/train", {});
    renderVoice(`B5a now uses your voice: FSDD + your ${d.recordings} recordings, each counted ${d.weight}× (b5a_calibrate). Back to the lesson and try it!`);
  } catch (e) { $("#vc-status").textContent = "⚠ " + e.message; }
}
function masteryChart(history, start, counts) {
  if (!history.length) return `<p class="empty">No graded answers yet.</p>`;
  const W = 560, H = 170, L = 34, R = 10, T = 10, B = 24; const n = history.length; const topics = Object.keys(start).filter((t) => counts[t] > 0);
  const x = (i) => L + (i / Math.max(1, n)) * (W - L - R); const y = (v) => T + (1 - v / 100) * (H - T - B);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mastery after every answer">`;
  [0, 25, 50, 75, 100].forEach((v) => { s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#d6cfbd"/><text x="${L - 6}" y="${y(v) + 4}" font-size="10" text-anchor="end" fill="#8a8476">${v}</text>`; });
  topics.forEach((t) => {
    const pts = [[0, start[t]], ...history.map((h, i) => [i + 1, h.mastery[t]])];
    s += `<polyline fill="none" stroke="${TOPIC_COLORS[t]}" stroke-width="2" points="${pts.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}"/>`;
  });
  history.forEach((h, i) => { s += `<circle cx="${x(i + 1)}" cy="${y(h.mastery[h.topic])}" r="3.5" fill="${h.correct ? "#4a7446" : "#b23a26"}"/>`; });
  s += `<text x="${(W + L) / 2}" y="${H - 4}" font-size="10" text-anchor="middle" fill="#8a8476">graded answers →</text></svg>`;
  return s + `<p class="muted">${topics.map((t) => `<span style="color:${TOPIC_COLORS[t]}">■</span> ${t}`).join(" &nbsp;")} · dots: green = correct, red = wrong · only topics with answers are drawn</p>`;
}
async function toggleDashboard() {
  if (!$("#ls-dash").hidden || !$("#ls-voice").hidden) { showView("lesson"); return; }
  try {
    const d = await api("/api/lesson/dashboard", { id: LS.id });
    addEvents(d.events); renderSide(d.panel, d.state);
    const topics = Object.keys(d.mastery);
    const rows = topics.map((t) => { const c = d.mastery[t] - d.mastery_start[t]; const n = d.topic_answers[t];
      return n ? `<tr><td>${t}</td><td class="mono">${n}</td><td class="mono">${d.mastery_start[t].toFixed(1)}%</td><td class="mono">${d.mastery[t].toFixed(1)}%</td><td class="mono ${c > 0 ? "ok" : c < 0 ? "no" : ""}">${c > 0 ? "+" : ""}${c.toFixed(1)}</td></tr>`
        : `<tr class="unknown"><td>${t}</td><td class="mono">0</td><td class="mono">${d.mastery_start[t].toFixed(1)}%</td><td colspan="2">not measured yet – only the class average is known</td></tr>`; }).join("");
    const diag = d.diagnoses.map((g) => `<tr><td class="mono">${esc(g.question)}</td><td>${esc(g.error_type)}</td><td>${esc(g.attention)}</td>
      <td>${g.probes.map(([s, v]) => `${esc(s)} ${v === 1 ? "✓" : v === 0.5 ? "✓?" : "✗"}`).join("<br>")}</td><td><b>${esc(g.root_cause)}</b> ${pct(g.probability)}</td></tr>`).join("");
    $("#ls-dash").innerHTML = `
      <div class="dash">
        <div class="card"><span class="label">B6 · mastery after every answer</span>${masteryChart(d.history, d.mastery_start, d.topic_answers)}
          <table class="compare"><tr><th>topic</th><th>answers</th><th>class average (start)</th><th>this child now</th><th>change</th></tr>${rows}</table>
          <p class="muted">A new child starts with the class average of all simulated children: B6 has nothing else yet (cold start). Every graded answer moves the estimate towards this child.
          ${d.answers} graded answers${d.accuracy != null ? `, ${pct(d.accuracy)} correct` : ""}; follow-up probes and practice items are not counted (as in the notebook demo).</p></div>
        <div class="card"><span class="label">B7 · error types</span>
          ${d.error_share ? bars(d.error_share) + `<p>Characteristic error (share ÷ class average): <b>${esc(d.characteristic)}</b></p>` : `<p class="empty">No wrong answers yet.</p>`}
          <span class="label" style="margin-top:14px">B8 · learning profile</span>
          ${d.profile ? `<p class="verdict small">${esc(d.profile.profile)}</p><ul>${d.profile.recommendations.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : `<p class="empty">${esc(d.profile_note)}</p>`}
          <p class="muted mono">pace used by the tutor: level up after ${d.pace.level_up_after}, break at ≥ ${d.pace.break_cost} points</p>
        </div>
      </div>
      <div class="card"><span class="label">B9 · root causes found in this lesson</span>
        ${diag ? `<table class="compare"><tr><th>question</th><th>B7 said</th><th>B4</th><th>probes asked</th><th>B9 root cause</th></tr>${diag}</table>` : `<p class="empty">No diagnosis yet – answer a question wrongly.</p>`}</div>
      <div class="card"><span class="label">B10 · learning patterns of the class (1,500 placement tests)</span>
        <ul>${d.patterns.map((r) => `<li>Only ${(r.without_rate * 100).toFixed(0)}% of the children who do not know <b>${esc(r.prerequisite)}</b> know <b>${esc(r.skill)}</b> → teach ${esc(r.prerequisite)} first</li>`).join("")}</ul></div>
      <p class="muted mono">Diagram arrows used in this lesson: ${d.arrows_used} of ${d.arrows_total}${d.unused.length ? ` · not yet: ${esc(d.unused.join(", "))}` : " – all of them"}</p>`;
    showView("dashboard");
  } catch (e) { $("#ls-why").textContent = "⚠ " + e.message; }
}

/* ------------------------------------------------------------ wiring */
makeBoxes();
$("#ls-text-send").addEventListener("click", sendText);
$("#ls-text").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sendText(); } });
$("#ls-send").addEventListener("click", () => sendAnswer($("#ls-value").value));
$("#ls-value").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sendAnswer($("#ls-value").value); } });
$("#ls-mic").addEventListener("click", sayAnswer);
$("#ls-read").addEventListener("click", readWriting);
$("#ls-clear").addEventListener("click", () => { clearBoxes(); $("#ls-readback").hidden = true; });
$("#ls-type-instead").addEventListener("click", () => showMode("keyboard", "typed instead (the reading blocks are skipped)"));
$("#ls-back").addEventListener("click", () => call("/api/lesson/resume", {}));
$("#ls-skip").addEventListener("click", () => call("/api/lesson/skip", {}));
$("#ls-topic").addEventListener("change", () => call("/api/lesson/topic", { topic: $("#ls-topic").value }));
$("#ls-new").addEventListener("click", startLesson);
$("#ls-dash-btn").addEventListener("click", toggleDashboard);
$("#ls-voice-btn").addEventListener("click", openVoice);
$("#vc-rec").addEventListener("click", recordCalibration);
$("#vc-train").addEventListener("click", trainVoice);
$("#vc-reset").addEventListener("click", async () => { await api("/api/voice/reset", {}); VC.counts = Array(10).fill(0); renderVoice("Your recordings were deleted; B5a uses the dataset model again."); });
$$("[data-side]").forEach((b) => b.addEventListener("click", () => selectSide(b.dataset.side)));

// The live camera of the B4 page is moved into the lesson while the lesson is open (one camera, one face model)
function placeCamera() {
  const onLesson = (location.hash || "#lesson") === "#lesson";
  (onLesson ? $("#ls-cam-slot") : $("#cam-home")).appendChild($("#cam-widget"));
}
window.addEventListener("hashchange", placeCamera);
placeCamera();
setInterval(() => {                                       // the "live camera" option is usable while the camera runs
  const live = !!(window.cameraRunning && window.cameraRunning());
  const option = $('#ls-cam option[value="live"]');
  option.disabled = !live; option.textContent = live ? "live camera" : "live camera (off)";
  if (!live && $("#ls-cam").value === "live") $("#ls-cam").value = "attentive";
}, 1000);
startLesson();

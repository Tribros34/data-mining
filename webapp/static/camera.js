/* B4 live camera: measures the three attention features with MediaPipe Face Landmarker, in the browser.
   The video never leaves the computer; only three numbers per second are sent to the B4 model.

   screen_gaze_ratio : share of frames in the last 10 s where a face is found, turned less than 20° away from the
                       calibrated "looking at the screen" direction, and the eyes are not looking sideways
   head_angle        : average angle (degrees) between the face direction and the calibrated direction, last 10 s
   blink_rate        : blinks per minute, counted over the last 30 s (10 s holds too few blinks to be stable)
*/
const VERSION = "0.10.14";
const LIB = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}`;
const MODEL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

const GAZE_WINDOW = 10_000;      // ms, like one row of the B4 training data
const BLINK_WINDOW = 30_000;     // ms
const CALIBRATION = 2_000;       // ms of "look at the screen" at the start
const AWAY_DEGREES = 20;         // turned further than this = not looking at the screen
const EYES_SIDEWAYS = 0.6;       // blendshape score: eyes looking far left/right/up/down
const BLINK_CLOSED = 0.45, BLINK_OPEN = 0.25;   // hysteresis on the eye-closure score

const $ = (s) => document.querySelector(s);
const video = $("#cam-video");
const button = $("#cam-btn");
const msg = $("#cam-msg");
const live = $("#cam-live");

let landmarker = null, stream = null, running = false;
let frames = [];                 // {t, face, angle, sideways}
let blinks = [];                 // timestamps of blinks
let eyesClosed = false, baseline = null, calibrationFrames = [], startTime = 0, lastSent = 0, lastVideoTime = -1;
let timeline = [];

async function loadLandmarker() {
  msg.textContent = "Loading the face model (first time ~4 MB)…";
  const { FaceLandmarker, FilesetResolver } = await import(`${LIB}/vision_bundle.mjs`);
  const files = await FilesetResolver.forVisionTasks(`${LIB}/wasm`);
  const options = (delegate) => ({
    baseOptions: { modelAssetPath: MODEL, delegate },
    runningMode: "VIDEO", numFaces: 1,
    outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
  });
  try { return await FaceLandmarker.createFromOptions(files, options("GPU")); }
  catch { return await FaceLandmarker.createFromOptions(files, options("CPU")); }
}

function faceDirection(matrix) {
  // 4x4 column-major transformation matrix; the face looks along its local z axis = third column
  const m = matrix.data; const v = [m[8], m[9], m[10]];
  const n = Math.hypot(...v); return v.map((x) => x / n);
}
const angleBetween = (a, b) => (Math.acos(Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))) * 180) / Math.PI;

function score(shapes, name) { const c = shapes.find((s) => s.categoryName === name); return c ? c.score : 0; }

function processFrame(result, now) {
  const face = result.faceLandmarks.length > 0 && result.facialTransformationMatrixes.length > 0;
  if (!face) { frames.push({ t: now, face: false }); return; }
  const dir = faceDirection(result.facialTransformationMatrixes[0]);
  const shapes = result.faceBlendshapes[0].categories;

  if (!baseline) {                                 // calibration: average direction while looking at the screen
    calibrationFrames.push(dir);
    if (now - startTime >= CALIBRATION && calibrationFrames.length > 5) {
      const avg = [0, 1, 2].map((i) => calibrationFrames.reduce((s, d) => s + d[i], 0) / calibrationFrames.length);
      const n = Math.hypot(...avg); baseline = avg.map((x) => x / n);
      msg.textContent = "Calibrated. Now behave normally – look away, close your eyes, turn your head…";
    }
    return;
  }

  const closure = (score(shapes, "eyeBlinkLeft") + score(shapes, "eyeBlinkRight")) / 2;
  if (!eyesClosed && closure > BLINK_CLOSED) { eyesClosed = true; blinks.push(now); }
  else if (eyesClosed && closure < BLINK_OPEN) eyesClosed = false;

  const sideways = Math.max(...["eyeLookOutLeft", "eyeLookOutRight", "eyeLookInLeft", "eyeLookInRight",
    "eyeLookUpLeft", "eyeLookUpRight"].map((n) => score(shapes, n)));
  frames.push({ t: now, face: true, angle: angleBetween(dir, baseline), sideways, closure });
}

function measure(now) {
  frames = frames.filter((f) => now - f.t <= GAZE_WINDOW);
  blinks = blinks.filter((t) => now - t <= BLINK_WINDOW);
  const withFace = frames.filter((f) => f.face);
  const looking = withFace.filter((f) => f.angle < AWAY_DEGREES && f.sideways < EYES_SIDEWAYS).length;
  const seconds = Math.min(BLINK_WINDOW, now - startTime - CALIBRATION) / 1000;
  const faceShare = frames.length ? withFace.length / frames.length : 0;
  return {
    screen_gaze_ratio: frames.length ? +(looking / frames.length).toFixed(2) : null,
    // the camera "lost the face" for most of the window -> missing value, as in the training data
    head_angle: faceShare >= 0.3 ? +Math.min(60, withFace.reduce((s, f) => s + f.angle, 0) / withFace.length).toFixed(0) : null,
    blink_rate: faceShare >= 0.3 && seconds >= 5 ? +Math.min(45, (blinks.length / seconds) * 60).toFixed(0) : null,
    closure: withFace.length ? withFace[withFace.length - 1].closure : null,
    faceShare,
  };
}

function loop() {
  if (!running) return;
  const now = performance.now();
  if (video.readyState >= 2 && video.currentTime !== lastVideoTime) {
    lastVideoTime = video.currentTime;
    processFrame(landmarker.detectForVideo(video, now), now);
  }
  if (baseline && now - lastSent > 1000) {          // send the current window once per second
    lastSent = now;
    const m = measure(now);
    live.innerHTML = `face found ${(m.faceShare * 100).toFixed(0)}% of the last 10 s · eye closure ${m.closure == null ? "—" : m.closure.toFixed(2)} · blinks in window ${blinks.length}`;
    window.b4FromCamera({ screen_gaze_ratio: m.screen_gaze_ratio, head_angle: m.head_angle, blink_rate: m.blink_rate });
  }
  requestAnimationFrame(loop);
}

function drawTimeline() {
  const colors = { attentive: "#1e1d1a", distracted: "#b23a26", tired: "#a77d1c" };
  $("#cam-timeline").innerHTML = timeline.map((s) => `<i title="${s}" style="background:${colors[s]}"></i>`).join("");
  const counts = Object.fromEntries(Object.keys(colors).map((k) => [k, timeline.filter((s) => s === k).length]));
  $("#cam-share").textContent = timeline.length
    ? Object.entries(counts).map(([k, n]) => `${k} ${((n / timeline.length) * 100).toFixed(0)}%`).join(" · ") : "";
}
document.addEventListener("b4result", (e) => {
  if (!running || !baseline) return;
  timeline.push(e.detail.state); if (timeline.length > 120) timeline.shift(); drawTimeline();
});

async function start() {
  button.disabled = true;
  try {
    landmarker = landmarker || (await loadLandmarker());
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } });
  } catch (e) {
    msg.textContent = e && e.name === "NotAllowedError" ? "Camera permission was refused."
      : "Could not start the camera or load the face model (internet needed for the model).";
    button.disabled = false; return;
  }
  video.srcObject = stream; await video.play();
  $("#cam-box").hidden = false;
  frames = []; blinks = []; calibrationFrames = []; baseline = null; timeline = []; eyesClosed = false;
  startTime = performance.now(); lastSent = 0; running = true;
  msg.textContent = "Calibrating: look at the screen for 2 seconds…";
  button.textContent = "Stop camera"; button.disabled = false;
  drawTimeline(); requestAnimationFrame(loop);
}

function stop() {
  running = false;
  if (stream) stream.getTracks().forEach((t) => t.stop());
  stream = null; video.srcObject = null;
  $("#cam-box").hidden = true;
  button.textContent = "Turn on camera";
  msg.textContent = "Camera off. The sliders keep the last measurement.";
}

button.addEventListener("click", () => (running ? stop() : start()));
window.addEventListener("hashchange", () => { if (running && location.hash !== "#b4") stop(); });

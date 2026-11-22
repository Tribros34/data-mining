"""Math Buddy – block workbench.

A small Flask server that lets you try every block of the notebook on its own, with your own input.
All predictions come from the block functions of math_buddy_its.ipynb (exported by export_models.py).

    python webapp/app.py            # http://localhost:8000
"""
import os
import tempfile
import zlib

import cloudpickle
import librosa
import numpy as np
import pandas as pd
import soundfile
from flask import Flask, jsonify, render_template, request

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.environ.get("MODEL_PATH", os.path.join(HERE, "models", "blocks.pkl"))

with open(MODEL_PATH, "rb") as f:
    BUNDLE = cloudpickle.load(f)
F = BUNDLE["functions"]          # block functions from the notebook
M = BUNDLE["models"]             # trained models (used only to show the full probability lists)
C = BUNDLE["constants"]
X = BUNDLE["extra"]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024        # 5 MB uploads


class BadInput(Exception):
    pass


@app.errorhandler(BadInput)
def bad_input(error):
    return jsonify({"error": str(error)}), 400


def number(data, key, low=None, high=None, allow_none=False):
    raw = data.get(key)
    if raw in (None, ""):
        if allow_none:
            return None
        raise BadInput(f"'{key}' is missing")
    try:
        val = float(raw)
    except (TypeError, ValueError):
        raise BadInput(f"'{key}' must be a number") from None
    if (low is not None and val < low) or (high is not None and val > high):
        raise BadInput(f"'{key}' must be between {low} and {high}")
    return val


def all_probabilities(model, x):
    probabilities = model.predict_proba(x)[0]
    return {str(c): round(float(p), 3) for c, p in zip(model.classes_, probabilities)}


# ---------------------------------------------------------------- pages
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/meta")
def meta():
    return jsonify({"metrics": BUNDLE["metrics"], "topics": C["TOPICS"], "error_types": C["ERROR_TYPES"],
                    "b6_mae_model": X["b6_mae_model"], "b6_mae_formula": X["b6_mae_formula"],
                    "b6_cold_start": X.get("b6_cold_start", {}),
                    "b4_importance": X["b4_importance"],
                    "profiles": {str(k): v for k, v in C["B8_PROFILES"].items()},
                    "b8_centers_z": {str(k): v for k, v in X["b8_centers_z"].items()},
                    "b8_sizes": {str(k): v for k, v in X["b8_sizes"].items()},
                    "b8_mean": X["b8_mean"], "b8_std": X["b8_std"],
                    "samples": sorted(os.listdir(os.path.join(HERE, "static", "samples")))})


# ---------------------------------------------------------------- B1 / B2 – text
WORD_PROBLEMS = {
    "sports": "Your team scored {a} goals this season and {b} more in the last match. How many goals is that?",
    "animals": "The zoo has {a} penguins. {b} more penguins arrive. How many penguins are there now?",
    "food": "You bake {a} cookies in the morning and {b} in the afternoon. How many cookies did you bake?",
    "games": "You have {a} points in your game and win {b} more. How many points do you have?",
}


def text_input(data):
    message = str(data.get("message", "")).strip()
    if not message:
        raise BadInput("Please type a message.")
    return message[:500]


@app.post("/api/b1")
def b1():
    message = text_input(request.get_json(force=True))
    result = F["b1_analyze_message"](message)
    rng = np.random.default_rng(zlib.crc32(message.encode()))
    problem = WORD_PROBLEMS[result["interest"]].format(a=int(rng.integers(12, 40)), b=int(rng.integers(5, 30)))
    return jsonify({"result": result,
                    "probabilities": all_probabilities(M["b1_model"], [message]),
                    "sentiment_probabilities": all_probabilities(M["sentiment_model"], [message]),
                    "word_problem": problem if result["use_for_problems"] else None})


@app.post("/api/b2")
def b2():
    message = text_input(request.get_json(force=True))
    return jsonify({"result": F["b2_analyze_message"](message),
                    "probabilities": all_probabilities(M["b2_model"], [message]),
                    "sentiment_probabilities": all_probabilities(M["sentiment_model"], [message])})


# ---------------------------------------------------------------- B3 – handwriting
@app.post("/api/b3")
def b3():
    data = request.get_json(force=True)
    try:
        ink = np.asarray(data["ink"], dtype=float)
    except (KeyError, TypeError, ValueError):
        raise BadInput("Send the drawing as a 2-D array 'ink'.") from None
    if ink.ndim != 2 or ink.size > 400 * 400 or (ink > 60).sum() < 5:
        raise BadInput("Draw a digit first.")
    mnist_image = F["drawing_to_mnist"](ink)
    small_image = F["drawing_to_8x8"](ink)
    return jsonify({
        "mnist": {"result": F["b3_read_drawing"](ink),
                  "probabilities": all_probabilities(M["b3_mnist_model"], mnist_image.reshape(1, -1)),
                  "image": np.round(mnist_image).astype(int).tolist()},
        "small": {"result": F["b3_read_handwriting"](small_image.ravel()),
                  "image": small_image.astype(int).tolist()},
    })


# ---------------------------------------------------------------- B4 – attention
@app.post("/api/b4")
def b4():
    data = request.get_json(force=True)
    gaze = number(data, "screen_gaze_ratio", 0, 1, allow_none=True)
    head = number(data, "head_angle", 0, 90, allow_none=True)
    blink = number(data, "blink_rate", 0, 80, allow_none=True)
    return jsonify({"result": F["b4_detect_attention"](gaze, head, blink),
                    "importance": X["b4_importance"]})


# ---------------------------------------------------------------- B5a – spoken digit
def recognize(path, trim):
    signal, sr = librosa.load(path, sr=8000)
    duration_before = len(signal) / sr
    if trim:      # FSDD recordings are cut tightly around the word; a browser recording has silence around it
        signal, _ = librosa.effects.trim(signal, top_db=30)
    if len(signal) < 0.15 * sr:
        raise BadInput("The recording is too short or silent. Say one digit clearly.")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        soundfile.write(tmp.name, signal, sr)
    try:
        features = pd.DataFrame([F["extract_mfcc_features"](tmp.name)], columns=M["b5a_model"].feature_names_in_)
        result = F["b5a_recognize_speech"](tmp.name)
    finally:
        os.remove(tmp.name)
    step = max(1, len(signal) // 400)
    return {"result": result, "probabilities": all_probabilities(M["b5a_model"], features),
            "waveform": np.round(signal[::step], 3).tolist(),
            "duration": round(duration_before, 2), "duration_trimmed": round(len(signal) / sr, 2)}


@app.post("/api/b5a")
def b5a():
    upload = request.files.get("audio")
    if upload is None:
        raise BadInput("No audio received.")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        upload.save(tmp.name)
    try:
        return jsonify(recognize(tmp.name, trim=True))
    except BadInput:
        raise
    except Exception:
        raise BadInput("Could not read this file. Use a .wav recording.") from None
    finally:
        os.remove(tmp.name)


@app.post("/api/b5a/sample")
def b5a_sample():
    name = os.path.basename(str(request.get_json(force=True).get("name", "")))
    path = os.path.join(HERE, "static", "samples", name)
    if not os.path.isfile(path):
        raise BadInput("Unknown sample.")
    return jsonify(recognize(path, trim=False))


# ---------------------------------------------------------------- B5b – confidence
@app.post("/api/b5b")
def b5b():
    data = request.get_json(force=True)
    return jsonify({"result": F["b5b_detect_confidence"](
        number(data, "speech_rate", 0, 8), number(data, "pause_count", 0, 15),
        number(data, "response_delay", 0, 15), number(data, "pitch_variation", 0, 10))})


def voice_features(signal, sr):
    """Measure the four B5b features in a recording that starts when the question is shown.

    response_delay  : seconds from the start of the recording to the first speech
    pause_count     : silences longer than 0.25 s between the first and the last speech
    speech_rate     : syllables per second between the first and the last speech (syllable = peak of loudness)
    pitch_variation : standard deviation of the voice pitch, in semitones (librosa pyin)
    """
    hop = int(0.01 * sr)                                                   # one frame = 10 ms
    rms = librosa.feature.rms(y=signal, frame_length=int(0.025 * sr), hop_length=hop)[0]
    noise = np.percentile(rms, 10)
    threshold = max(noise * 3, rms.max() * 0.08)
    voiced = rms > threshold

    # Speech segments: merge gaps shorter than 0.15 s, drop blips shorter than 0.08 s
    segments, start = [], None
    for i, v in enumerate(np.append(voiced, False)):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segments.append([start, i]); start = None
    merged = []
    for s, e in segments:
        if merged and s - merged[-1][1] < 15:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    merged = [[s, e] for s, e in merged if e - s >= 8]
    if not merged:
        raise BadInput("No speech found. Say the answer a bit louder.")

    first, last = merged[0][0], merged[-1][1]
    pauses = [(e1, s2) for (_, e1), (s2, _) in zip(merged, merged[1:]) if s2 - e1 >= 25]
    span = (last - first) / 100

    envelope = np.convolve(rms, np.ones(5) / 5, mode="same")              # smoothed loudness
    from scipy.signal import find_peaks
    peaks, _ = find_peaks(envelope[first:last], height=threshold * 1.5, distance=12,
                          prominence=envelope[first:last].max() * 0.1)
    syllables = max(1, len(peaks))

    part = signal[first * hop:last * hop]
    f0, voiced_flag, _ = librosa.pyin(part, fmin=75, fmax=500, sr=sr, frame_length=1024)
    f0 = f0[voiced_flag & ~np.isnan(f0)]
    pitch = float(np.std(12 * np.log2(f0 / np.median(f0)))) if len(f0) >= 5 else None

    step = max(1, len(rms) // 300)
    return {
        "features": {"response_delay": round(first / 100, 2), "pause_count": len(pauses),
                     "speech_rate": round(syllables / max(span, 0.2), 2),
                     "pitch_variation": round(pitch, 2) if pitch is not None else None},
        "details": {"duration": round(len(signal) / sr, 2), "speech_start": first / 100, "speech_end": last / 100,
                    "segments": [[s / 100, e / 100] for s, e in merged], "pauses": [[a / 100, b / 100] for a, b in pauses],
                    "syllables": syllables, "voiced_pitch_frames": int(len(f0)),
                    "envelope": np.round(rms[::step] / rms.max(), 3).tolist(), "envelope_step": step / 100,
                    "threshold": round(float(threshold / rms.max()), 3)},
        "answer_audio": signal[merged[-1][0] * hop:merged[-1][1] * hop],    # last word = the answer, for B5a
    }


# Voice calibration (notebook B5a.9b): the child's own recordings, and the personal B5a model trained with them
VOICE = {"features": [], "digits": [], "model": None}


def last_word_features(measured, sr):
    # MFCC features (B5a input) of the last spoken word of a recording, prepared like the dataset (8 kHz, cut tightly)
    answer = librosa.resample(measured["answer_audio"], orig_sr=sr, target_sr=8000)
    if len(answer) < 0.15 * 8000:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        soundfile.write(tmp.name, answer, 8000)
    try:
        return F["extract_mfcc_features"](tmp.name)
    finally:
        os.remove(tmp.name)


def read_digit(features):
    # B5a on one word: the personal model if the voice was calibrated, otherwise the notebook model
    model = VOICE["model"] or M["b5a_model"]
    probabilities = model.predict_proba(pd.DataFrame([features], columns=M["b5a_model"].feature_names_in_))[0]
    best = int(np.argmax(probabilities))
    return {"digit": int(model.classes_[best]), "probability": round(float(probabilities[best]), 3),
            "personal": VOICE["model"] is not None}


def analyse_voice(upload):
    """B5b + B5a on one spoken answer: the four voice features, confident / hesitant, and the digit of the last word."""
    if upload is None:
        raise BadInput("No audio received.")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        upload.save(tmp.name)
    try:
        signal, sr = librosa.load(tmp.name, sr=16000)
    except Exception:
        raise BadInput("Could not read the recording.") from None
    finally:
        os.remove(tmp.name)
    measured = voice_features(signal, sr)
    f = measured["features"]
    if f["pitch_variation"] is None:
        raise BadInput("Could not hear a voiced sound to measure the pitch. Speak a bit longer.")
    result = F["b5b_detect_confidence"](min(f["speech_rate"], 7), min(f["pause_count"], 10),
                                        min(f["response_delay"], 15), min(f["pitch_variation"], 8))
    features = last_word_features(measured, sr)          # B5a on the last word (the answer), like the tutor would
    digit = read_digit(features) if features is not None else None
    return {"result": result, "features": f, "details": measured["details"], "b5a": digit}


@app.post("/api/b5b/audio")
def b5b_audio():
    return jsonify(analyse_voice(request.files.get("audio")))


# ---------------------------------------------------------------- B6 – mastery
@app.post("/api/b6/mastery")
def b6_mastery():
    answers = request.get_json(force=True).get("answers", [])
    if not isinstance(answers, list) or len(answers) > 2000:
        raise BadInput("'answers' must be a list.")
    rows = []
    for i, a in enumerate(answers):
        if a.get("topic") not in C["TOPICS"] or a.get("attention") not in ("attentive", "distracted", "tired"):
            raise BadInput(f"Answer {i + 1}: unknown topic or attention.")
        spoken = a.get("answer_mode") == "speech"
        rows.append({"student_id": "WEB", "seq": i, "day": 0, "topic": a["topic"],
                     "difficulty": int(number(a, "difficulty", 1, 3)), "attention": a["attention"],
                     "answer_mode": "speech" if spoken else "handwriting",
                     "is_hesitant": float(bool(a.get("is_hesitant"))) if spoken else np.nan,
                     "is_correct": int(bool(a.get("is_correct")))})
    log = pd.DataFrame(rows, columns=["student_id", "seq", "day", "topic", "difficulty", "attention",
                                      "answer_mode", "is_hesitant", "is_correct"])
    return jsonify({"mastery": F["b6_mastery"](log)})


@app.post("/api/b6/simulate")
def b6_simulate():
    data = request.get_json(force=True)
    ability = number(data, "ability", -2, 2)
    profile = {"start_skill": {t: C["TOPIC_START"][t] + ability for t in C["TOPICS"]},
               "learning_rate": number(data, "learning_rate", 0.005, 0.15),
               "distractibility": number(data, "distractibility", 0, 0.8),
               "speech_preference": number(data, "speech_preference", 0, 1)}
    seed = int(number(data, "seed", 0, 10**6))
    log = pd.DataFrame(F["simulate_student"]("SIM", profile, np.random.default_rng(seed)))
    days = sorted(log["day"].unique())
    estimated, true = [], []
    for day in days:
        upto = log[log["day"] <= day]
        estimated.append(F["b6_mastery"](upto))
        true.append({t: round(float(F["true_mastery_from_skill"](
            profile["start_skill"][t] + profile["learning_rate"] * (upto["topic"] == t).sum())) * 100, 1)
            for t in C["TOPICS"]})
    by_day = log.groupby("day").agg(answers=("is_correct", "size"), correct=("is_correct", "sum")).reset_index()
    return jsonify({"days": [int(d) for d in days], "estimated": estimated, "true": true,
                    "answers": len(log), "accuracy": round(float(log["is_correct"].mean()), 3),
                    "per_day": by_day.astype(int).to_dict(orient="records")})


# ---------------------------------------------------------------- B7 – error type
def parse_operand(raw, operation):
    text = str(raw).strip().replace(" ", "")
    try:
        if operation == "fractions":
            top, bottom = (int(p) for p in text.split("/"))
            if top < 0 or bottom <= 0:
                raise ValueError
            return f"{top}/{bottom}"
        val = int(text)
        if val < 0:
            raise ValueError
        return val
    except ValueError:
        kind = "a fraction like 3/4" if operation == "fractions" else "a whole number ≥ 0"
        raise BadInput(f"'{raw}' must be {kind}.") from None


@app.post("/api/b7")
def b7():
    data = request.get_json(force=True)
    operation = data.get("operation")
    if operation not in C["TOPICS"]:
        raise BadInput("Unknown operation.")
    a, b, given = (parse_operand(data.get(k, ""), operation) for k in ("a", "b", "given"))
    if operation == "subtraction" and a < b:
        raise BadInput("For subtraction the first number must be at least the second.")
    if operation == "division" and (b == 0 or a % b):
        raise BadInput("Use a division that has no remainder (e.g. 56 ÷ 7).")
    parse = (lambda x: tuple(int(p) for p in x.split("/"))) if operation == "fractions" else (lambda x: x)
    correct = F["correct_answer"](operation, parse(a), parse(b))
    if F["value"](parse(given)) <= 0:
        raise BadInput("B7 only sorts answers greater than 0.")
    result = F["b7_error_type"](operation, a, b, given)
    answer = {"correct": F["as_text"](correct), "needs_carry": int(F["needs_carry"](operation, parse(a), parse(b)))
              if operation != "fractions" else 0}
    if result is not None:
        g, cv = parse(given), correct
        row = pd.DataFrame([{"operation": operation, "correct_answer": F["value"](cv), "given_answer": F["value"](g),
                             "correct_denominator": cv[1] if isinstance(cv, tuple) else 1,
                             "given_denominator": g[1] if isinstance(g, tuple) else 1}])
        row["difference"] = row["given_answer"] - row["correct_answer"]
        row["ratio"] = row["given_answer"] / row["correct_answer"]
        answer["features"] = {k: round(float(v), 3) for k, v in F["b7_features"](row).iloc[0].items()}
    return jsonify({"result": result, **answer})


@app.post("/api/b7/random")
def b7_random():
    data = request.get_json(force=True)
    rng = np.random.default_rng()
    operation = data.get("operation") if data.get("operation") in C["TOPICS"] else str(rng.choice(C["TOPICS"]))
    for _ in range(100):
        difficulty = int(rng.integers(1, 4))
        a, b = F["make_question"](operation, difficulty, rng)
        options = (["careless_slip", "fraction_rule"] if operation == "fractions" else
                   ["careless_slip", "wrong_operation"] + (["forgot_carry"] if F["needs_carry"](operation, a, b) else []))
        error_type = str(rng.choice(options))
        given = F["wrong_answer"](operation, a, b, error_type, rng)
        if given != F["correct_answer"](operation, a, b) and F["value"](given) > 0:
            return jsonify({"operation": operation, "a": F["as_text"](a), "b": F["as_text"](b),
                            "given": F["as_text"](given), "hidden_type": error_type})
    raise BadInput("Could not make a question, try again.")


# ---------------------------------------------------------------- B8 – profile
@app.post("/api/b8")
def b8():
    data = request.get_json(force=True)
    values = {"avg_accuracy": number(data, "avg_accuracy", 0, 1), "learning_speed": number(data, "learning_speed", -1, 2),
              "avg_attention": number(data, "avg_attention", 0, 1),
              "spoken_answer_ratio": number(data, "spoken_answer_ratio", 0, 1)}
    error = data.get("characteristic_error")
    if error not in C["ERROR_TYPES"]:
        raise BadInput("Unknown error type.")
    result = F["b8_student_profile"](**values, characteristic_error=error)
    z = {k: round((v - X["b8_mean"][k]) / X["b8_std"][k], 2) for k, v in values.items()}
    return jsonify({"result": result, "student_z": z})


# ---------------------------------------------------------------- Lesson – the whole learning loop
from lesson import BadAnswer, Lesson  # noqa: E402

LESSONS = {}                     # lesson id -> Lesson (in memory; one server = a few children at a time)


@app.errorhandler(BadAnswer)
def bad_answer(error):
    return jsonify({"error": str(error)}), 400


def lesson_from(data):
    lesson = LESSONS.get(str(data.get("id", "")))
    if lesson is None:
        raise BadInput("This lesson has expired. Start a new one.")
    return lesson


@app.post("/api/lesson/start")
def lesson_start():
    if len(LESSONS) >= 50:
        LESSONS.pop(next(iter(LESSONS)))
    lesson = Lesson(F, C, X)
    LESSONS[lesson.id] = lesson
    return jsonify(lesson.respond())


@app.post("/api/lesson/chat")
def lesson_chat():
    data = request.get_json(force=True)
    lesson = lesson_from(data)
    lesson.chat(data.get("message", ""))
    return jsonify(lesson.respond())


@app.post("/api/lesson/answer")
def lesson_answer():
    data = request.get_json(force=True)
    lesson = lesson_from(data)
    lesson.answer(data)
    return jsonify(lesson.respond())


@app.post("/api/lesson/topic")
def lesson_topic():
    data = request.get_json(force=True)
    lesson = lesson_from(data)
    lesson.set_topic(data.get("topic"))
    return jsonify(lesson.respond())


@app.post("/api/lesson/skip")
def lesson_skip():
    lesson = lesson_from(request.get_json(force=True))
    lesson.skip_step()
    return jsonify(lesson.respond())


@app.post("/api/lesson/resume")
def lesson_resume():
    lesson = lesson_from(request.get_json(force=True))
    lesson.resume()
    return jsonify(lesson.respond())


@app.post("/api/lesson/dashboard")
def lesson_dashboard():
    lesson = lesson_from(request.get_json(force=True))
    result = lesson.dashboard()
    return jsonify({**result, **lesson.respond()})


@app.post("/api/lesson/read/handwriting")
def lesson_read_handwriting():
    # One digit per box, left to right; empty boxes are skipped. Each box is read by B3 (MNIST model).
    boxes = request.get_json(force=True).get("boxes", [])
    if not isinstance(boxes, list) or not 1 <= len(boxes) <= 4:
        raise BadInput("Send 1-4 boxes.")
    digits = []
    for ink in boxes:
        ink = np.asarray(ink, dtype=float)
        if ink.ndim != 2 or ink.size > 200 * 200:
            raise BadInput("Bad drawing.")
        if (ink > 60).sum() >= 5:
            digits.append(F["b3_read_drawing"](ink))
    if not digits:
        raise BadInput("Write the answer in the boxes first.")
    return jsonify({"value": "".join(str(d["digit"]) for d in digits),
                    "digits": [{"digit": int(d["digit"]), "probability": round(float(d["probability"]), 3)}
                               for d in digits]})


@app.post("/api/lesson/read/voice")
def lesson_read_voice():
    r = analyse_voice(request.files.get("audio"))
    if r["b5a"] is None:
        raise BadInput("I heard you, but the last word was too short to read. Say the number again.")
    return jsonify({"value": str(r["b5a"]["digit"]), "probability": round(float(r["b5a"]["probability"]), 3),
                    "personal": r["b5a"]["personal"], "calibration": len(VOICE["digits"]),
                    "state": r["result"]["state"], "p_hesitant": r["result"]["p_hesitant"], "features": r["features"]})


@app.post("/api/voice/sample")
def voice_sample():
    # One calibration recording: the child says the digit shown on the screen
    try:
        digit = int(request.form.get("digit", ""))
    except ValueError:
        raise BadInput("Which digit was said?") from None
    if not 0 <= digit <= 9:
        raise BadInput("Digit must be 0-9.")
    upload = request.files.get("audio")
    if upload is None:
        raise BadInput("No audio received.")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        upload.save(tmp.name)
    try:
        signal, sr = librosa.load(tmp.name, sr=16000)
    except Exception:
        raise BadInput("Could not read the recording.") from None
    finally:
        os.remove(tmp.name)
    features = last_word_features(voice_features(signal, sr), sr)
    if features is None:
        raise BadInput("Too short – say the digit a bit longer.")
    heard = read_digit(features)                       # what B5a understood BEFORE learning this recording
    VOICE["features"].append(features.tolist())
    VOICE["digits"].append(digit)
    return jsonify({"heard": heard, "counts": [VOICE["digits"].count(d) for d in range(10)]})


@app.post("/api/voice/train")
def voice_train():
    # Retrain B5a on FSDD + the child's recordings (each counted CALIBRATION_WEIGHT times), notebook B5a.9b
    if len(set(VOICE["digits"])) < 10:
        raise BadInput("Record every digit 0-9 at least once first.")
    VOICE["model"] = F["b5a_calibrate"](np.array(VOICE["features"]), VOICE["digits"])
    return jsonify({"recordings": len(VOICE["digits"]), "weight": C["CALIBRATION_WEIGHT"]})


@app.post("/api/voice/reset")
def voice_reset():
    VOICE.update(features=[], digits=[], model=None)
    return jsonify({"recordings": 0})


@app.get("/api/voice")
def voice_status():
    return jsonify({"counts": [VOICE["digits"].count(d) for d in range(10)], "personal": VOICE["model"] is not None,
                    "recordings": len(VOICE["digits"])})


def warm_up():
    # The first librosa call compiles code (numba); do it at start so the first visitor does not wait
    samples = os.path.join(HERE, "static", "samples")
    files = sorted(os.listdir(samples)) if os.path.isdir(samples) else []
    if files:
        recognize(os.path.join(samples, files[0]), trim=True)
        word, sr = librosa.load(os.path.join(samples, files[0]), sr=16000)
        voice_features(np.concatenate([np.zeros(8000), word, np.zeros(8000)]), sr)


warm_up()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)

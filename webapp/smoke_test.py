"""Smoke test for the web app: calls every endpoint with good and bad input.

    python webapp/smoke_test.py                 # server on http://localhost:8000
    python webapp/smoke_test.py http://host:port
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

import numpy as np
from PIL import Image

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
HERE = os.path.dirname(os.path.abspath(__file__))
failures = 0


def call(path, body=None, files=None):
    if files:
        boundary = uuid.uuid4().hex
        name, data = files
        payload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"{name}\"\r\n"
                   f"Content-Type: audio/wav\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(BASE + path, payload, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    elif body is not None:
        req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read()) if "json" in r.headers.get("Content-Type", "") else r.read()
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(name, condition, detail=""):
    global failures
    print(("PASS " if condition else "FAIL ") + name + (f"   {detail}" if detail else ""))
    failures += not condition


status, page = call("/")
check("index page", status == 200 and b"Math Buddy" in page)
status, meta = call("/api/meta")
check("meta", status == 200 and len(meta["topics"]) == 5 and len(meta["samples"]) == 10, meta.get("metrics"))

s, d = call("/api/b1", {"message": "I played football with my friends"})
check("B1 sports", s == 200 and d["result"]["interest"] == "sports" and d["word_problem"], d["result"])
s, d = call("/api/b1", {"message": "I hate football, it's so boring"})
check("B1 negative -> no word problem", s == 200 and d["word_problem"] is None, d["result"])
s, d = call("/api/b1", {"message": "   "})
check("B1 empty message rejected", s == 400, d)

s, d = call("/api/b2", {"message": "I don't understand multiplication at all"})
check("B2 multiplication", s == 200 and d["result"]["topic"] == "multiplication", d["result"])

ink = 255 - np.array(Image.open(os.path.join(HERE, "..", "test_drawings", "drawn_six.png")).convert("L").resize((140, 140)))
s, d = call("/api/b3", {"ink": ink.astype(int).tolist()})
check("B3 drawn six", s == 200 and d["mnist"]["result"]["digit"] == 6, (d["mnist"]["result"], d["small"]["result"]))
s, d = call("/api/b3", {"ink": [[0] * 10] * 10})
check("B3 empty drawing rejected", s == 400, d)

s, d = call("/api/b4", {"screen_gaze_ratio": 0.42, "head_angle": 28, "blink_rate": 17})
check("B4 distracted", s == 200 and d["result"]["state"] == "distracted", d["result"]["state"])
s, d = call("/api/b4", {"screen_gaze_ratio": None, "head_angle": 12, "blink_rate": 16})
check("B4 missing value accepted", s == 200, d["result"]["state"])
s, d = call("/api/b4", {"screen_gaze_ratio": 5, "head_angle": 12, "blink_rate": 16})
check("B4 out-of-range rejected", s == 400, d)

correct = 0
for digit in range(10):
    s, d = call("/api/b5a/sample", {"name": f"{digit}_george_0.wav"})
    correct += s == 200 and d["result"]["digit"] == digit
check("B5a samples", correct >= 9, f"{correct}/10 correct")
with open(os.path.join(HERE, "static", "samples", "4_george_0.wav"), "rb") as f:
    s, d = call("/api/b5a", files=("4.wav", f.read()))
check("B5a upload", s == 200 and d["result"]["digit"] == 4, d.get("result"))
s, d = call("/api/b5a", files=("x.wav", b"not audio"))
check("B5a bad file rejected", s == 400, d)
s, d = call("/api/b5a/sample", {"name": "../app.py"})
check("B5a path traversal rejected", s == 400, d)

s, d = call("/api/b5b", {"speech_rate": 2.4, "pause_count": 3, "response_delay": 3.5, "pitch_variation": 3.6})
check("B5b hesitant", s == 200 and d["result"]["state"] == "hesitant", d["result"])
s, d = call("/api/b5b", {"speech_rate": 3.1, "pause_count": 0, "response_delay": 0.8, "pitch_variation": 1.6})
check("B5b confident", s == 200 and d["result"]["state"] == "confident", d["result"])


def fake_answer(parts):
    # Build a 16 kHz recording from FSDD words (int digit) and silences (float seconds), as WAV bytes
    import io
    import librosa
    import soundfile
    pieces = [librosa.load(os.path.join(HERE, "static", "samples", f"{p}_george_0.wav"), sr=16000)[0]
              if isinstance(p, int) else np.zeros(int(p * 16000)) for p in parts]
    signal = np.concatenate(pieces) + np.random.default_rng(0).normal(0, 0.002, sum(map(len, pieces)))
    out = io.BytesIO()
    soundfile.write(out, signal, 16000, format="WAV")
    return out.getvalue()


s, d = call("/api/b5b/audio", files=("a.wav", fake_answer([0.8, 7, 1.6])))
check("B5b microphone: quick answer", s == 200 and d["result"]["state"] == "confident"
      and d["features"]["pause_count"] == 0 and d["b5a"]["digit"] == 7, d.get("features", d))
s, d = call("/api/b5b/audio", files=("a.wav", fake_answer([3.0, 4, 0.7, 1, 0.6, 7, 1.6])))
check("B5b microphone: late answer with pauses", s == 200 and d["result"]["state"] == "hesitant"
      and d["features"]["pause_count"] == 2, d.get("features", d))
s, d = call("/api/b5b/audio", files=("a.wav", fake_answer([2.0])))
check("B5b microphone: silence rejected", s == 400, d)

s, empty = call("/api/b6/mastery", {"answers": []})
answers = [{"topic": "multiplication", "difficulty": 2, "attention": "attentive", "answer_mode": "handwriting",
            "is_correct": 1}] * 10
s, many = call("/api/b6/mastery", {"answers": answers})
check("B6 mastery rises after 10 correct", s == 200 and many["mastery"]["multiplication"] > empty["mastery"]["multiplication"] + 10,
      f'{empty["mastery"]["multiplication"]} -> {many["mastery"]["multiplication"]}')
s, d = call("/api/b6/simulate", {"ability": 0, "learning_rate": 0.05, "distractibility": 0.25,
                                  "speech_preference": 0.4, "seed": 7})
check("B6 simulation", s == 200 and len(d["days"]) > 15 and d["answers"] > 200, f'{d["answers"]} answers, {len(d["days"])} days')

cases = [("addition", "47", "38", "75", "forgot_carry"), ("addition", "85", "47", "122", "forgot_carry"),
         ("addition", "47", "38", "84", "careless_slip"), ("multiplication", "7", "8", "15", "wrong_operation"),
         ("subtraction", "52", "38", "24", "forgot_carry"), ("fractions", "1/2", "1/3", "2/5", "fraction_rule"),
         ("fractions", "1/2", "1/3", "4/6", "careless_slip")]
for op, a, b, given, expected in cases:
    s, d = call("/api/b7", {"operation": op, "a": a, "b": b, "given": given})
    check(f"B7 {a} {op} {b} = {given}", s == 200 and d["result"]["error_type"] == expected, d.get("result", d))
s, d = call("/api/b7", {"operation": "fractions", "a": "1/2", "b": "1/3", "given": "10/12"})
check("B7 equivalent fraction counts as correct", s == 200 and d["result"] is None, d)
s, d = call("/api/b7", {"operation": "division", "a": "7", "b": "2", "given": "3"})
check("B7 division with remainder rejected", s == 400, d)
s, d = call("/api/b7", {"operation": "addition", "a": "4", "b": "5", "given": "0"})
check("B7 zero answer rejected", s == 400, d)
s, d = call("/api/b7", {"operation": "fractions", "a": "x", "b": "1/3", "given": "5/6"})
check("B7 bad fraction rejected", s == 400, d)
agree = 0
for _ in range(40):
    s, q = call("/api/b7/random", {})
    s, d = call("/api/b7", {"operation": q["operation"], "a": q["a"], "b": q["b"], "given": q["given"]})
    agree += d["result"]["error_type"] == q["hidden_type"]
check("B7 random mistakes vs. hidden type", agree >= 26, f"{agree}/40 agree")

s, d = call("/api/b8", {"avg_accuracy": 0.58, "learning_speed": 0.33, "avg_attention": 0.61,
                        "spoken_answer_ratio": 0.53, "characteristic_error": "forgot_carry"})
check("B8 Can", s == 200 and "profile" in d["result"], d["result"]["profile"])
s, d = call("/api/b8", {"avg_accuracy": 0.6, "learning_speed": 0.3, "avg_attention": 0.35,
                        "spoken_answer_ratio": 0.3, "characteristic_error": "careless_slip"})
check("B8 distracted student", s == 200 and "distracted" in d["result"]["profile"].lower(), d["result"]["profile"])
s, d = call("/api/b8", {"avg_accuracy": "abc"})
check("B8 bad input rejected", s == 400, d)

# Lesson: chat -> question -> wrong answer -> B9 probes -> learning path (practice) -> dashboard
s, d = call("/api/lesson/start", {})
lid = d["id"]
check("Lesson start", s == 200 and d["state"] == "chat_interest" and d["panel"]["arrows_used"] == 2, d["state"])
s, d = call("/api/lesson/chat", {"id": lid, "message": "I played football with my friends, it was awesome!"})
check("Lesson B1 interest", s == 200 and d["panel"]["interest"] == "sports" and d["state"] == "chat_topic", d["panel"]["interest"])
s, d = call("/api/lesson/chat", {"id": lid, "message": "I don't understand addition at all"})
check("Lesson B2 topic -> placement test", s == 200 and d["panel"]["topic"] == "addition" and d["state"] == "placement",
      d["panel"]["placement"] if s == 200 else d)
s, d = call("/api/lesson/skip", {"id": lid})
check("Lesson placement skipped -> first question", s == 200 and d["state"] == "question", d["prompt"]["text"] if s == 200 else d)
s, d = call("/api/lesson/answer", {"id": lid, "value": "abc", "mode": "keyboard", "camera": {"preset": "attentive"}})
check("Lesson bad answer rejected", s == 400, d)
s, d = call("/api/lesson/answer", {"id": lid, "value": "1", "mode": "keyboard", "camera": {"preset": "distracted"}})
arrows = {(e["from"], e["to"]) for e in d["events"] if e["type"] == "arrow"}
check("Lesson wrong answer -> B6, B7, B9", s == 200 and {("TUTOR", "B6"), ("TUTOR", "B7"), ("B7", "B9"), ("B6", "B9")} <= arrows,
      d["state"])
steps = 0
while s == 200 and d["state"] == "probe" and steps < 5:
    steps += 1
    s, d = call("/api/lesson/answer", {"id": lid, "value": "1", "mode": "keyboard", "camera": {"preset": "attentive"}})
check("Lesson B9 probes end in a diagnosis", s == 200 and d["state"] in ("practice", "question", "break") and d["panel"]["diagnoses"] == 1,
      f"{steps} probe(s), now {d['state']}")
s, d = call("/api/lesson/dashboard", {"id": lid})
check("Lesson dashboard", s == 200 and len(d["diagnoses"]) == 1 and d["answers"] == 1, d.get("characteristic"))
# A distracted child: B6 prices the distraction, the tutor takes a break before the next question
s, d = call("/api/lesson/start", {})
lid = d["id"]
call("/api/lesson/chat", {"id": lid, "message": "I played football with my friends"})
call("/api/lesson/chat", {"id": lid, "message": "I don't understand addition at all"})
call("/api/lesson/skip", {"id": lid})
s, d = call("/api/lesson/answer", {"id": lid, "value": "1", "mode": "keyboard", "camera": {"preset": "distracted"}})
cost = [e for e in d["events"] if e["type"] == "arrow" and (e["from"], e["to"]) == ("B6", "TUTOR")]
check("Lesson B6 prices the distraction", s == 200 and len(cost) == 1, cost[0]["message"] if cost else d)
while s == 200 and d["state"] == "probe":
    s, d = call("/api/lesson/answer", {"id": lid, "value": "1", "mode": "keyboard", "camera": {"preset": "attentive"}})
check("Lesson break before the next item", s == 200 and d["state"] == "break", d["state"])
s, d = call("/api/lesson/resume", {"id": lid})
check("Lesson resume after the break", s == 200 and d["state"] in ("practice", "question"), d["state"])
# Placement test of the chosen topic: one probe per skill, then a learning path from the first missing skill
s, d = call("/api/lesson/start", {})
lid = d["id"]
call("/api/lesson/chat", {"id": lid, "message": "I played football with my friends"})
s, d = call("/api/lesson/chat", {"id": lid, "message": "Multiplication is so hard for me"})
total = d["panel"]["placement"]["total"] if s == 200 and d["panel"]["placement"] else 0
check("Lesson placement test of the topic", s == 200 and d["state"] == "placement" and total >= 5
      and len(d["panel"]["placement_result"]) == total - 2, f"{total} questions")
for _ in range(total):
    s, d = call("/api/lesson/answer", {"id": lid, "value": "1", "mode": "keyboard", "camera": {"preset": "attentive"}})
known = [r["skill"] for r in d["panel"]["placement_result"] if r["result"]]
check("Lesson placement -> learning path or questions", s == 200 and d["state"] in ("practice", "question")
      and d["panel"]["answers"] == 2, f"now {d['state']}, known: {known}")
s, d = call("/api/lesson/answer", {"id": "nope", "value": "1"})
check("Lesson unknown id rejected", s == 400, d)

print(f"\n{'ALL PASSED' if not failures else f'{failures} FAILED'}")
sys.exit(1 if failures else 0)

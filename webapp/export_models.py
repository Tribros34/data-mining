"""Run the main notebook once and save its block functions (with their trained models) for the web app.

Usage (from the project folder, with the .venv active):
    python webapp/export_models.py

The web app never re-implements a block: it loads exactly the functions written in math_buddy_its.ipynb.
cloudpickle stores every function together with the models and helper functions it uses.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import time

import cloudpickle
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "webapp", "models", "blocks.pkl")
SAMPLES = os.path.join(ROOT, "webapp", "static", "samples")

# Names taken from the notebook namespace
FUNCTIONS = [
    "b1_analyze_message", "b2_analyze_message", "b3_read_drawing", "b3_read_handwriting", "drawing_to_mnist",
    "drawing_to_8x8", "b4_detect_attention", "b5a_recognize_speech", "extract_mfcc_features",
    "b5b_detect_confidence", "b6_mastery", "simulate_student", "make_student_profile", "true_mastery_from_skill",
    "b7_error_type", "b7_features", "make_question", "correct_answer", "wrong_answer", "needs_carry", "as_text",
    "value", "b8_student_profile", "b8_student_row",
    # B9 / B10 and the demo helpers used by the lesson page (lesson.py)
    "b9_case", "b9_first_guess", "bayes_update", "b9_next_probe", "b9_decision", "skills_for_question",
    "b9_learning_path", "practice_item", "word_problem", "b7_error_type",
    # tutor decisions from B6 / B8 (notebook section 10.2b)
    "b6_p_correct", "b6_attention_cost", "next_topic", "b8_pace", "b5a_calibrate",
]
MODELS = ["b1_model", "b2_model", "sentiment_model", "b3_mnist_model", "b4_model", "b5a_model", "b5b_model"]
CONSTANTS = ["TOPICS", "TOPIC_START", "ERROR_TYPES", "SYMBOL", "B7_HINTS", "B8_NUMERIC", "B8_PROFILES", "PROFILE_TAGS",
             "ATTENTION_FEATURES", "CONFIDENCE_FEATURES",
             "PROBES", "SKILL_TIPS", "SKILLS", "SKILL_MAP", "B9_CLASSES", "B10_SKILL_MAP", "CAMERA", "INTEREST_WORDS",
             "DIAGRAM_ARROWS", "DIAGRAM_BLOCKS", "MASTERED_AT", "BREAK_COST", "DEFAULT_PACE",
             "CALIBRATION_WEIGHT"]
METRICS = {"B1": "b1_accuracy", "B2": "b2_accuracy", "B3 (8x8)": "b3_accuracy", "B3 (MNIST)": "b3_mnist_accuracy",
           "B4": "b4_accuracy", "B5a": "b5a_accuracy", "B5b": "b5b_accuracy"}


def run_notebook():
    os.chdir(ROOT)
    with open("math_buddy_its.ipynb", encoding="utf-8") as f:
        notebook = json.load(f)
    namespace = {"__name__": "math_buddy_notebook"}      # not importable -> cloudpickle stores functions by value
    plt.show = lambda *args, **kwargs: plt.close("all")
    with contextlib.redirect_stdout(io.StringIO()):
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                exec("".join(cell["source"]), namespace)
    return namespace


def main():
    start = time.time()
    print("Running math_buddy_its.ipynb (takes ~30 s when MNIST is cached) ...")
    ns = run_notebook()

    b8 = ns["b8_df"]
    bundle = {
        "functions": {name: ns[name] for name in FUNCTIONS},
        "models": {name: ns[name] for name in MODELS},
        "constants": {name: ns[name] for name in CONSTANTS},
        "metrics": {block: round(float(ns[var]), 3) for block, var in METRICS.items()},
        "extra": {
            "b6_mae_model": round(float(ns["b6_error_model"]) * 100, 1),
            "b6_mae_formula": round(float(ns["b6_error_formula"]) * 100, 1),
            "b6_cold_start": {int(k): {"model": round(float(r["model"]), 2), "formula": round(float(r["formula"]), 2)}
                              for k, r in ns["cold_error"].iterrows()},
            "b8_mean": b8[ns["B8_NUMERIC"]].mean().round(4).to_dict(),
            "b8_std": b8[ns["B8_NUMERIC"]].std().round(4).to_dict(),
            "b8_centers_z": ns["b8_centers_z"].round(3).to_dict(orient="index"),
            "b8_sizes": b8["profile_id"].value_counts().sort_index().to_dict(),
            # Lesson page: 3 real MNIST test images per digit (for "What number is this?"), the mined learning
            # patterns of B10 and the average error-type shares (for the characteristic error of B8)
            "mnist_samples": {d: [ns["X_mnist_test"][i].reshape(28, 28).astype(int).tolist()
                                  for i in np.where(ns["y_mnist_test"] == d)[0][:3]] for d in range(10)},
            "b10_patterns": [{"prerequisite": r.prerequisite, "skill": r.skill, "without_rate": round(float(r.without_rate), 3)}
                             for r in ns["direct"].sort_values("without_rate").itertuples()],
            "average_share": {k: float(v) for k, v in ns["average_share"].items()},
            "b4_importance": {k: round(float(v), 3) for k, v in zip(
                ns["ATTENTION_FEATURES"], ns["b4_model"].named_steps["classifier"].feature_importances_)},
        },
        "python": sys.version.split()[0],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        cloudpickle.dump(bundle, f)
    print(f"Saved {OUT} ({os.path.getsize(OUT) / 1e6:.0f} MB)")

    # One FSDD recording per digit from a test speaker, so B5a can be tried without a microphone
    os.makedirs(SAMPLES, exist_ok=True)
    for digit in range(10):
        source = os.path.join(ns["FSDD_DIR"], f"{digit}_george_0.wav")
        if os.path.exists(source):
            shutil.copy(source, os.path.join(SAMPLES, f"{digit}_george_0.wav"))
    print(f"Copied sample recordings to {SAMPLES}")
    print(f"Done in {time.time() - start:.0f} s")


if __name__ == "__main__":
    main()

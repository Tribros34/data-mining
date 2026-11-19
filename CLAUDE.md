# Math Buddy – Intelligent Tutoring System (ITS) · Midterm Project

This folder is the midterm project of Kerem's group for a machine learning course.
This file summarizes the planning done in an earlier chat; treat everything here as the source of truth
and continue from where we left off.

## Language rules (important)

- **All deliverables are in English:** notebook code, comments, variable and column names, class labels,
  printed outputs, plot titles/axes, markdown cells, the report and the diagram.
- **Explanations to the user in chat are in Turkish** (plain language, analogies, before/after examples).
  If the user asks for English explanations, switch.

## How to work with the user (important)

- The user and their group will **have you write the code and do the setup**. What they need from you:
  **before each step, explain what you are going to do and why**, then do it, then explain the result.
- The user is new to ML. Already explained and understood in the earlier chat: X/y split, missing-value
  imputation (SimpleImputer), one-hot / label encoding, train_test_split (why it returns 4 values),
  StandardScaler, fit vs transform, data leakage, supervised vs unsupervised, what BERT is.
- The group must **explain this code in the report**, so keep it readable, well commented, section by section.
- Go step by step; after finishing a step, summarize and wait for the user's OK before the next one.

## Assignment (instructor's text)

> What are the requirements expected from an intelligent tutoring system? Draw a block diagram to express
> the functionalities of an ITS in terms of supervised learning tasks and unsupervised learning tasks.
> Each block will correspond to a supervised or an unsupervised learning task. What are the attributes in
> the structure of each dataset fed to each block? What is the structure of the output produced by each
> block? Provide the Python implementation which performs the functionalities in this diagram. Write a
> report to explain each section of this code and each section of the output of the code.

- **Submission:** zip/rar via the instructor's link. **Deadline: 23.11.2026 01:00** (effectively Sunday night, Nov 22). No late submissions.
- **Group work.** One student submits on behalf of the whole group; only submissions through the instructor's link count. The zip contains **code + report** (format of the report is not specified; PDF is the safe choice). The submission must include **name, last name and student ID of every member**; a forgotten member cannot be added later and gets zero.
- **Instructor's hints:**
  1. Write a **detailed scenario** of interactions between the student and the intelligent tutor
     (e.g. the tutor first chats with the student to learn their interests and picks topics from them).
  2. Think of interaction mechanisms by **modality**: **audio, visual, textual**. Derive the block tasks
     from examples in these three categories.
- **Requirements carried over from the previous assignment (must be included):**
  - Measure the student's percentage of accurately learning each subject and track its **variation over time**.
  - Extract students' **learning patterns** so better teaching mechanisms can be developed.

## Chosen topic and scenario

**Topic:** Elementary school basic math (addition, subtraction, multiplication, division, fractions).

**Scenario (Can, 3rd grader, "Math Buddy" tablet app):**
1. Starts with a chat: "What did you do today?" → "I played football with my friends" → the system detects
   the interest (sports) and builds word problems around it ("Your team scored 23 goals, then 19 more...").
2. "I don't understand multiplication at all" → topic the student struggles with: multiplication.
3. Can **writes the answer with his finger** on the tablet → handwritten digit recognition.
4. Or he **says the answer aloud** ("nine!") → spoken digit recognition; his voice also shows whether he is **confident or hesitant**.
5. The front camera tracks **attention** (attentive / distracted / tired).
6. After every answer, the **learning percentage** per topic is updated and kept as a time series.
7. Weekend teacher dashboard: **error types** (forgot to carry, careless slip, mixed up operation) and **student profiles**.

## Block diagram

```
                         ┌───────── STUDENT (Can) ─────────┐
                      📝 TEXT          👀 VISUAL          👂 AUDIO
   [B1] Interest    [B2] Struggle    [B3] Handwritten [B4] Attention [B5a] Spoken digit [B5b] Confidence
     (Sup.)           topic (Sup.)    digit (Sup.)     (Sup.)          (Sup.)             (Sup.)
          │              └───────────────┴──────┬──────┴──────────────┴──────────────────┘
          ▼                       [B6] Mastery / learning percentage (Supervised)
  Word problems personalized                    │
  to the student's interest      ┌──────────────┴──────────────┐
                          [B7] Error type discovery    [B8] Student profiles
                            (Unsupervised)               (Unsupervised)
                                 └──────────────┬──────────────┘
                                                ▼
                                        Teacher dashboard
```

## Block input / output definitions (use these column names in code)

| Block | Type | Modality | Data | Input columns | Output |
|---|---|---|---|---|---|
| **B1** Interest detection | Supervised, classification | Text | Synthetic | `message` (text), label `interest` | `sports`/`animals`/`food`/`games` + probabilities **+ `sentiment` (positive/neutral/negative)** |
| **B2** Struggle topic detection | Supervised, classification | Text | Synthetic | `message`, label `topic` | `addition`/`subtraction`/`multiplication`/`division`/`fractions` **+ `sentiment`** |
| **B3** Handwritten digit | Supervised, classification | Visual | **Real**: `sklearn.datasets.load_digits` (8×8, main) + **MNIST** 28×28 (B3.9, used by demo/app) | `pixel_1..pixel_64` (0–16), label `digit` | 0–9 + probability |
| **B4** Attention | Supervised, classification | Visual | Synthetic | `screen_gaze_ratio` (0–1), `head_angle` (deg), `blink_rate` (/min), label `state` | `attentive`/`distracted`/`tired` |
| **B5a** Spoken digit | Supervised, classification | Audio | **Real**: Free Spoken Digit Dataset (in this folder) | MFCC (20 coeffs × mean+std = 40 columns), label `digit` (first char of file name) | 0–9 |
| **B5b** Confidence | Supervised, classification | Audio | Synthetic | `speech_rate`, `pause_count`, `response_delay` (s), `pitch_variation`, label `state` | `confident`/`hesitant` |
| **B6** Mastery percentage | Supervised (probability, knowledge-tracing style) | Combined | Synthetic | `student_id`, `topic` (one-hot), `difficulty` (1–3), `attempt_no`, `prev_correct_ratio`, `attention` (from B4), `confidence` (from B5b), `timestamp`, label `is_correct` (0/1) | P(correct) per topic = mastery % + time-series plot |
| **B7** Error type discovery | Unsupervised, K-Means | Combined | Synthetic (one row = one wrong answer) | `operation` (one-hot), `correct_answer`, `given_answer`, `difference`, `ratio`, `needs_carry` | `cluster_id` → forgot_carry / careless_slip / wrong_operation / fraction_rule + teacher hint; per student: characteristic error |
| **B8** Student profiles | Unsupervised, K-Means | Combined | Synthetic (one row = one student) | `avg_accuracy`, `learning_speed`, `avg_attention`, `spoken_answer_ratio`, `characteristic_error` (from B7, one-hot) | `profile_id` → interpretation + recommendation (e.g. "fast but distracted: short sessions") |

## Technical decisions

- **Single notebook:** `math_buddy_its.ipynb` (code and output stay together, good for the report).
- Every block uses the same template: `1. Data → 2. Preprocessing → 3. Train/test split (supervised only) → 4. Model → 5. Evaluation → 6. Example prediction (Can's case)`.
- **Rules (explained to the user, apply in code):**
  - Split first, then imputer/scaler: **fit only on train**, only `transform` on test (no data leakage).
  - Scale numeric columns only; do not scale one-hot (0/1) columns. Prefer `ColumnTransformer` + `Pipeline`.
  - Always scale before K-Means.
  - Fixed `random_state` (reproducibility). Use `stratify=y` for classification.
- **Text (B1, B2):** messages are in English. TF-IDF + LogisticRegression as the main model.
  In the report, mention **DistilBERT** (the model the instructor shared in week 6) as the stronger alternative / future work;
  optionally add a small DistilBERT comparison if time allows.
- **B3:** `load_digits` (1797 images, 8×8). LogisticRegression(max_iter=2000) reached ~97% accuracy in a test run.
- **B5a:** `librosa.load(f, sr=8000)`, `librosa.feature.mfcc(y=..., sr=..., n_mfcc=20, n_fft=512)` (n_fft=512 avoids warnings),
  mean+std → 40 features, StandardScaler + LogisticRegression(max_iter=3000) reached ~92% accuracy in a test run.
- **Synthetic data:** generate reasonable but overlapping class distributions (add noise); otherwise accuracy is 100% and looks unrealistic.
  The report must state the data is synthetic and where it would come from in a real system (camera → e.g. MediaPipe, microphone → librosa, etc.).
- Save plots also as PNG in `outputs/` (for the report): B3 sample digits + confusion matrix,
  B6 mastery-over-time plot, B7/B8 cluster plots.
- Every block ends with a **block function** (clear input → output). The demo calls blocks only through these, with on/off switches
  (`BLOCKS_ENABLED`) and fallbacks (B3 off → spoken answer via B5a, or keyboard) for an **ablation study**:
  compare grading accuracy and mastery-estimate error with B3 on / off. Sensitivity plot only if time allows.
- All blocks use synthetic data (except B3, B5a); the report cites real datasets each block could use
  (B1 Yellowbrick Hobbies, B2 ASDiv, B4 DAiSEE/EngageNet, B5b Harvard Uncertainty corpus, B6 ASSISTments, B7 Eedi NeurIPS 2020, B8 OULAD).
- At the end: **Demo – Can's week** — an end-to-end simulation connecting the blocks.

## Folder structure

```
math_buddy_its/
├── CLAUDE.md                    ← this file
├── requirements.txt             ← numpy, pandas, matplotlib, scikit-learn, librosa, ipykernel, scipy, pillow
├── study_guide/               ← Turkish study guide for the group (5-person split), NOT in the submission
├── manual_tests.ipynb           ← user's playground for trying blocks (NOT in the submission)
├── test_drawings/               ← drawn_six.png (needed by B3.8/B3.9, include in submission)
├── math_buddy_its.ipynb         ← main notebook (B1–B8)
├── webapp/                      ← Flask block workbench (app.py, export_models.py, smoke_test.py, Dockerfile)
├── docker-compose.yml           ← runs the workbench on http://localhost:8000
├── free-spoken-digit-dataset/   ← downloaded, 3000 .wav files under recordings/ ("9_george_3.wav" → 9)
├── outputs/                     ← plots
├── diagram/                     ← block diagram (draw.io etc.)
└── report/                      ← report
```
Do not put `free-spoken-digit-dataset/` or `.venv/` in the submission zip (cite the source in the report:
https://github.com/Jakobovski/free-spoken-digit-dataset).

## Setup (Mac, in the project folder)

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```
The user will open the notebook in **Antigravity** (VS Code based); select `.venv` as the kernel.

## Roadmap and status

| Step | Task | Status |
|---|---|---|
| 1 | Folder, dataset, requirements.txt | ✅ Folder + FSDD + requirements + `.venv` (Python 3.14, all packages) ready. |
| 2 | B3 – Handwritten digit recognition | ✅ Notebook created (header, members placeholder, setup, B3). Test accuracy 0.972. Block function `b3_read_handwriting(pixels)`. **B3.8** limitation: 8×8 model misreads real/hand-drawn digits (distribution shift + 8×8 too small; user's mouse-drawn 6 in `test_drawings/drawn_six.png` → 5). **B3.9** MNIST (fetch_openml mnist_784, `parser="liac-arff"` because pandas 3 breaks the pandas parser; cached in ~/scikit_learn_data, first download ~6 min), official 60k/10k split, RandomForest(100 trees, ~144 MB) test 0.969; `drawing_to_mnist(ink)` (crop → thicken 8% → fit 20×20 → center of mass in 28×28) + `b3_read_drawing(ink)` reads the drawn 6 correctly (0.75). **Demo and web app use the MNIST model.** |
| 3 | B5a – Spoken digit recognition | ✅ Test accuracy 0.915 (random split). Block function `b5a_recognize_speech(wav_path)`. B5a.8 Leave-One-Speaker-Out: unseen speaker avg 0.496 (limitation). B5a.9 voice calibration (k recordings/digit from new speaker added to training): k=0 0.496, 1 0.612, 3 0.699, 5 0.755, 10 0.821 → `outputs/b5a_personalization.png`. |
| 4 | B4 – Attention | ✅ Synthetic 1500 rows (500/state, ~3% NaN = camera lost face), SimpleImputer(median) → RandomForest(200 trees, max_depth=6), no scaling. Train 0.946 / test 0.897 (overfit check). Importance: gaze 0.42, blink 0.30, head 0.28. Function `b4_detect_attention(gaze, head, blink)`. |
| 5 | B5b – Confidence | ✅ Synthetic 1000 rows (600 confident / 400 hesitant; Poisson pauses, log-normal delay), StandardScaler → LogisticRegression. Train 0.931 / test 0.935. Coefs: response_delay +2.73, pause_count +1.47, pitch_variation +1.19, speech_rate −1.50. Function `b5b_detect_confidence(...)` → state + p_hesitant. B4 decision: missing camera values stay median-imputed (option a), note added. |
| 6 | B1 + B2 – Text blocks | ✅ Template + word-pool synthetic messages (typos, cross-topic cues, duplicates removed, 8% sentiment label noise). Templates diversified (15 items/interest, 10 phrases/topic, ~16 templates/sentiment, when/who/opener/ending slots): B1 1597 unique msgs, B2 1392. B1 TF-IDF+LogReg test 0.884; B2 test 0.892. **Sentiment added as 2nd output of B1 and B2** (one model on all messages, TF-IDF (1,2) bigrams + LogReg, test 0.905 vs 0.893 unigrams; bigrams fix 'Chess is so boring'). Functions `b1_analyze_message(msg)` → interest, probability, sentiment, use_for_problems (False if negative); `b2_analyze_message(msg)` → topic, probability, sentiment, start_easy. 'soccer' deliberately not in training data (shows TF-IDF unknown-word limitation). DistilBERT comparison postponed to the end (optional). |
| 7 | B6 – Mastery percentage + time plot | ✅ (order changed: B6 → B7 → B8, because B8 uses B6 + B7 outputs). Student simulation: 200 students × 28 days (day 0 placement test = 5 medium questions per topic, then ~10/day, 20% skipped days), hidden true skill grows with practice; guess 0.15 / slip 0.05; attention from per-student distractibility; `answer_mode` speech/handwriting (speech preference per student), `is_hesitant` only for speech. 48,047 answers. History features from PAST answers only (smoothed ratios): attempt_no, prev_correct_ratio, recent_correct_ratio (last 5), prev_hesitant_ratio (**confidence enters as history, not the current answer – leakage**). GroupShuffleSplit by student (160/40). ColumnTransformer (scale numeric, one-hot topic/attention) → LogReg. Acc 0.679, AUC 0.725, well calibrated. Mastery = P(correct | medium, attentive). Mean error vs true mastery: model 8.1 pp vs simple formula (correct÷total) 16.0 pp. Cold start: error 12.4 pp (0 answers) → 8.9 (5) → ~8 (10+). Functions `b6_mastery(answers)` → {topic: %}, `simulate_student`, `add_history_features`. Can profile simulated (seed 7). |
| 8 | B7 – Error type discovery | ✅ For every wrong answer of B6 a question + given answer is generated from 4 hidden error types (forgot_carry, careless_slip, wrong_operation, **fraction_rule**); 18,740 wrong answers. Raw columns (`operation`, `correct_answer`, `given_answer`, `difference`, `ratio`, `needs_carry`) → 4 scale-free *shape* features (`size_ratio_log`, `error_steps_log`, `diff_is_tens`, `same_denominator`) → StandardScaler → K-Means. Elbow+silhouette: k=4 (sil 0.717). Clusters named automatically from centers. ARI 0.768 (raw columns only 0.028), 90.9% match hidden type. Functions `b7_predict(errors)`, `b7_error_type(operation, a, b, given)` → type + teacher hint. **Characteristic error** (share ÷ class average) instead of most common error (careless_slip dominates: 191/200). Can → forgot_carry (1.51×). `outputs/b7_choose_k.png`, `b7_clusters.png`, `b7_can_errors.png`. |
| 9 | B8 – Student profiles | ✅ 200 students: `avg_accuracy`, `learning_speed` (per-student LogReg slope of attempt_no; corr 0.74 with hidden learning rate), `avg_attention`, `spoken_answer_ratio` (scaled) + `characteristic_error` one-hot (weight 0.5). Silhouette ~0.2 for all k (honest: students vary continuously) → k=4: Fast learner·Prefers writing (62), Prefers speaking (56), Slow progress·Needs support (38), Easily distracted (44). Names + recommendations from center z-scores (|z|≥0.5). Checked vs hidden traits (attention↔distractibility −0.98, spoken↔speech pref 0.99). Function `b8_student_profile(...)`. Can → Prefers speaking + forgot_carry hint. `outputs/b8_choose_k.png`, `b8_profiles.png`. |
| 10 | Demo – Can's week | ⏳ Next |
| 10b | Web app (block workbench) + Docker | ✅ `webapp/`: `export_models.py` runs the notebook silently and cloudpickles the notebook's own block functions + models → `webapp/models/blocks.pkl` (146 MB, NOT in submission zip, regenerate). `app.py` (Flask) = one page per block with own input (B3 drawing canvas, B5a mic/upload/FSDD samples with silence trim, B6 manual answers + 28-day simulation chart, B7 equation + random mistake, B8 sliders; **B4 live camera**: `static/camera.js`, MediaPipe Face Landmarker 0.10.14 from jsdelivr in the browser, 2 s calibration, gaze/head over last 10 s, blinks over 30 s, drives the B4 sliders once per second + state timeline; **B5b microphone**: “Ask me a question” → records until 1.5 s quiet → `/api/b5b/audio` measures response_delay / pause_count (gaps ≥0.25 s) / speech_rate (loudness peaks ≈ syllables per s; training speech_rate is syllables/s, not words) / pitch_variation (pyin, semitones), B5a reads the last word). Look: exercise-book (paper, ink, red pencil, no web fonts). `smoke_test.py` 34/34 pass locally and in Docker. `docker compose up --build` (python:3.14.5-slim, pinned `webapp/requirements.txt` = .venv versions; image 1.2 GB). **Re-run export_models.py after any notebook change.** |
| 11 | Clean block diagram (diagram/) | ✅ `diagram/block_diagram.svg` (hand-written SVG, also embedded in the report). |
| 12 | Report (report/): requirements, scenario, diagram, input/output structure per block, code and output explanations, limitations | ✅ Draft done: `report/report.html` → `report/Math_Buddy_ITS_Report.pdf` (Chrome headless `--print-to-pdf --no-pdf-header-footer`, 30 pages, A4). Covers B1–B8 + 'How the blocks work together'; Demo (step 10) NOT covered yet. Member table on cover = TBD. Re-render after edits. |
| 12b | (Optional, only if time) Sentiment analysis of the student's chat messages (e.g. frustration "I hate math") – user asked to look at it at the very end | |
| 13 | Check: members' name/last name/ID, zip, submit | |

Target: steps 1–6 Thu/Fri, 7–10 Saturday, 11–13 Sunday.
A group-members table (placeholder _TBD_) is at the top of the notebook; the user will give the names at the very end.

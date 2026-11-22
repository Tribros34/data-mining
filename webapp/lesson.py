"""Math Buddy – the lesson: the learning loop of the notebook (section 10, tutor_episode), one step per request.

The child chats (B1, B2), then answers questions by keyboard, handwriting (B3) or voice (B5a + B5b) while the camera
(B4) watches. After every question B6 updates the mastery. A wrong answer goes to B7 and then to B9, which asks the
follow-up probes ONE AT A TIME (the web page has to wait for the child between probes, so the loop of b9_diagnose is
run here step by step with the notebook's own b9_first_guess / b9_next_probe / bayes_update / b9_decision).
The root cause gives a learning path (on the B10 skill map, told with the B1 interest); after practising, the child
gets the same kind of question again – at most 3 rounds, like tutor_episode() in the notebook.

Every step records the diagram arrow it uses (DIAGRAM_ARROWS of the notebook) and the notebook function that does
the work, so the page can show where in the code each decision is made.
"""
import re
import uuid

import numpy as np
import pandas as pd

MOVE_ON_STREAK = 3        # b9_learning_path: "move_on_when": "3 correct answers in a row"
MAX_ITEMS_PER_STEP = 8    # after 8 practice items the tutor moves on anyway (the re-test will show what is missing)
MAX_ROUNDS = 3            # like tutor_episode(): at most 3 diagnoses for the same kind of question
MIN_ANSWERS_BETWEEN_BREAKS = 3
PLACEMENT_TOPIC_QUESTIONS = 2   # placement test: one probe per skill of the topic + 2 questions of the topic itself (for B6)
SHOWS_DIGIT = re.compile(r"\[shows the digit (\d)\]\s*")

SKILL_NAMES = {
    "number_recognition": "reading numbers", "counting": "counting", "operation_meaning": "what + and − mean",
    "addition_facts": "adding small numbers", "place_value": "tens and ones", "subtraction_facts": "taking away small numbers",
    "times_tables": "the times tables", "carrying": "carrying a ten", "borrowing": "borrowing a ten",
    "division_facts": "sharing (division facts)", "fraction_concept": "what a fraction is",
    "equivalent_fractions": "equal fractions", "careless": "a careless slip",
}


class BadAnswer(Exception):
    pass


def parse_answer(text, fraction):
    text = str(text).strip().replace(" ", "")
    try:
        if fraction:
            if "/" not in text:
                return int(text)
            top, bottom = (int(p) for p in text.split("/"))
            if bottom <= 0 or top < 0:
                raise ValueError
            return (top, bottom)
        number = int(text)
        if number < 0:
            raise ValueError
        return number
    except ValueError:
        raise BadAnswer("Type a whole number" + (" or a fraction like 3/4" if fraction else "") + ".") from None


class Lesson:
    def __init__(self, F, C, X):
        self.F, self.C, self.X = F, C, X
        self.id = uuid.uuid4().hex[:12]
        self.rng = np.random.default_rng()
        self.state = "chat_interest"       # chat_interest -> chat_topic -> question <-> probe -> practice -> retest
        self.interest = None
        self.topic = None
        self.difficulty = 2
        self.streak = 0
        self.log = []                      # the B6 answer log of this child (one row per graded question)
        self.history = []                  # B6 mastery after every logged answer
        self.used_arrows = set()
        self.errors = []                   # B7 results
        self.diagnoses = []                # B9 results
        self.question = None               # the question that started the current diagnosis
        self.prompt = None                 # what the child is being asked now (answer kept on the server)
        self.diag = None                   # the running B9 diagnosis
        self.path = None                   # the running learning path
        self.round = 1
        self.pace = dict(C["DEFAULT_PACE"])   # changed by B8 (b8_pace) once the child has a profile
        self.profile = None
        self.last_cost = None              # B6: what the current attention costs (percentage points)
        self.break_pending = None
        self.after_break = None
        self.since_break = 99
        self.placement, self.placement_total, self.start_easy, self.placement_result = [], 0, False, {}
        self.out = []
        self.mastery_start = self.mastery()
        self.say("Hi, I'm Math Buddy! What did you do today?")
        self.arrow("TUTOR", "B10", "placement tests of all children (notebook B10.1)", "b10_skill_map()")
        edges = sum(len(p) for p in C["B10_SKILL_MAP"].values())
        self.arrow("B10", "TUTOR", f"discovered skill map, {edges} prerequisite edges = the teaching order", "B10_SKILL_MAP")
        self.ask("chat", "What did you do today?")

    # ------------------------------------------------------------ output helpers
    def say(self, text, image=None):
        self.out.append({"type": "tutor", "text": text, "image": image})

    def child(self, text, via):
        self.out.append({"type": "child", "text": text, "via": via})

    def note(self, text):
        self.out.append({"type": "note", "text": text})

    def arrow(self, source, target, message, fn=None):
        # The same rule as arrow() in the notebook demo: only arrows of the block diagram may be used
        assert (source, target) in self.C["DIAGRAM_ARROWS"], f"{source} -> {target} is not in the block diagram"
        self.used_arrows.add((source, target))
        self.out.append({"type": "arrow", "from": source, "to": target, "message": message, "fn": fn})

    def ask(self, kind, text, answer=None, fraction=False, skill=None):
        if self.break_pending and kind in ("question", "retest", "practice", "placement"):
            # B4 + B6: the distraction costs too much -> a short break before the next item (not inside a diagnosis)
            cost, attention, topic = self.break_pending
            self.break_pending, self.since_break = None, 0
            self.after_break = (self.state, kind, text, answer, fraction, skill)
            self.state = "break"
            self.prompt = {"kind": "break", "text": "", "answer": None, "fraction": False, "skill": None,
                           "mode": "break", "why": "B4 + B6: the distraction costs more than the B8 pace allows"}
            self.say(f"You look {attention}. Right now that costs you about {cost:.0f} points in {topic}, "
                     "so let's take a short break: stand up, stretch, drink some water – and press “I'm back”.")
            return
        image = None
        match = SHOWS_DIGIT.search(text)
        if match:                                             # "[shows the digit 7]" -> a real MNIST image of a 7
            samples = self.X["mnist_samples"][int(match.group(1))]
            image = samples[int(self.rng.integers(len(samples)))]
            text = SHOWS_DIGIT.sub("", text)
        mode, why = self.answer_mode(answer, fraction)
        self.prompt = {"kind": kind, "text": text, "answer": answer, "fraction": fraction, "skill": skill,
                       "mode": mode, "why": why}
        if kind != "chat":
            self.say(text, image)
            what = {"question": "question", "retest": "question (re-test)", "placement": "placement-test question", "probe": f"follow-up probe for {skill}",
                    "practice": f"practice item for {skill}"}[kind]
            self.arrow("TUTOR", "STUDENT", what)

    def answer_mode(self, answer, fraction):
        # Which input channel fits the answer – the same rule as read_answer() in the notebook demo:
        # B5a can hear one digit (0-9), B3 reads digits one box at a time, nobody reads "/" -> keyboard
        if answer is None:
            return "keyboard", "chat message → B1 / B2 read the text"
        if fraction:
            return "keyboard", "a fraction → typed (B3 and B5a cannot read “/”)"
        if 0 <= int(answer) <= 9 and self.pace.get("answer_mode") != "handwriting":
            return "speech", "one digit → say it: B5a hears the digit, B5b hears whether you are sure"
        if 0 <= int(answer) <= 9:
            return "handwriting", "one digit → write it (B8 profile: prefers writing): B3 reads it"
        return "handwriting", "a number with more digits → write one digit per box: B3 reads every box"

    def resume(self):
        if self.state != "break":
            raise BadAnswer("There is no break right now.")
        state, kind, text, answer, fraction, skill = self.after_break
        self.after_break, self.state = None, state
        self.child("I'm back!", "keyboard")
        self.say("Welcome back! Let's go on.")
        self.ask(kind, text, answer, fraction, skill)

    def respond(self):
        events, self.out = self.out, []
        prompt = None
        if self.prompt:
            prompt = {k: v for k, v in self.prompt.items() if k != "answer"}   # the answer stays on the server
        return {"id": self.id, "state": self.state, "events": events, "prompt": prompt, "panel": self.panel()}

    def panel(self):
        current = self.history[-1]["mastery"] if self.history else self.mastery_start
        belief = None
        if self.diag:
            order = np.argsort(self.diag["belief"])[::-1][:5]
            belief = [{"cause": self.C["B9_CLASSES"][i], "p": round(float(self.diag["belief"][i]), 3)} for i in order]
        path = None
        if self.path:
            path = [{"skill": s["skill"], "name": SKILL_NAMES.get(s["skill"], s["skill"]),
                     "status": "done" if i < self.path["step"] else "now" if i == self.path["step"] else "next"}
                    for i, s in enumerate(self.path["steps"])]
        return {"interest": self.interest, "topic": self.topic, "difficulty": self.difficulty, "round": self.round,
                "mastery": current, "mastery_start": self.mastery_start, "answers": len(self.log),
                "belief": belief, "asked": self.diag["asked"] if self.diag else None, "path": path,
                "streak": self.path["streak"] if self.path else None,
                "arrows_used": len(self.used_arrows), "arrows_total": len(self.C["DIAGRAM_ARROWS"]),
                "diagnoses": len(self.diagnoses), "pace": self.pace, "last_cost": self.last_cost,
                "profile": self.profile["profile"] if self.profile else None,
                "mastered_at": self.C["MASTERED_AT"], "topic_answers": self.topic_answers(),
                "placement": ({"done": self.placement_total - len(self.placement), "total": self.placement_total,
                               "topic": self.topic} if self.state == "placement" else None),
                "placement_result": [{"skill": s, "name": SKILL_NAMES[s], "result": v}
                                     for s, v in self.placement_result.items()]}

    def topic_answers(self):
        # How many graded answers B6 has per topic: 0 = B6 only knows the class average (cold start, notebook B6.7)
        counts = {t: 0 for t in self.C["TOPICS"]}
        for row in self.log:
            counts[row["topic"]] += 1
        return counts

    # ------------------------------------------------------------ B6
    def log_frame(self):
        columns = ["student_id", "seq", "day", "topic", "difficulty", "attention", "answer_mode", "is_hesitant",
                   "is_correct"]
        return pd.DataFrame(self.log, columns=columns)

    def mastery(self):
        return self.F["b6_mastery"](self.log_frame())

    # ------------------------------------------------------------ chat (B1, B2)
    def chat(self, message):
        message = str(message).strip()[:300]
        if not message:
            raise BadAnswer("Type a message.")
        if self.state == "chat_interest":
            self.child(message, "keyboard")
            self.arrow("STUDENT", "B1", repr(message))
            r = self.F["b1_analyze_message"](message)
            self.arrow("B1", "TUTOR", f"interest = {r['interest']} (p = {r['probability']:.2f}), "
                                      f"sentiment = {r['sentiment']}", "b1_analyze_message()")
            if r["use_for_problems"]:
                self.interest = r["interest"]
                thing = self.C["INTEREST_WORDS"][self.interest][0]
                self.say(f"That sounds fun! My questions for you will be about {thing}.")
            else:
                self.say("Oh, I see. Then I'll keep my questions simple, without that topic.")
            self.state = "chat_topic"
            self.say("Is there something in math that is hard for you?")
            self.ask("chat", "Is there something in math that is hard for you?")
        elif self.state == "chat_topic":
            self.child(message, "keyboard")
            self.arrow("STUDENT", "B2", repr(message))
            r = self.F["b2_analyze_message"](message)
            self.arrow("B2", "TUTOR", f"topic = {r['topic']} (p = {r['probability']:.2f}), "
                                      f"start_easy = {r['start_easy']}", "b2_analyze_message()")
            self.topic, self.start_easy = r["topic"], r["start_easy"]
            self.start_placement()
        else:
            raise BadAnswer("Answer the question first.")

    # ------------------------------------------------------------ placement test of the chosen topic (cold start)
    def start_placement(self):
        # Cold start: nothing is known about this child. Before teaching the B2 topic, test every skill the topic
        # needs (the probes of B9.1, in the teaching order of the B10 map) and ask 2 questions of the topic for B6.
        topic = self.topic
        skills = self.F["skills_for_question"](topic, 1, self.C["B10_SKILL_MAP"])
        self.placement = [("skill", s) for s in skills] + [("question", topic)] * PLACEMENT_TOPIC_QUESTIONS
        self.placement_total = len(self.placement)
        self.placement_result = {s: None for s in skills}
        self.say(f"Before we start with {topic}, a short placement test: {self.placement_total} questions. "
                 f"I want to find out which parts of {topic} you already know. Here I only listen – just do your best!")
        self.note(f"Cold start: B6 knows only the class average. Placement test of {topic}: one probe per skill "
                  f"({', '.join(skills)}) + {PLACEMENT_TOPIC_QUESTIONS} questions of the topic")
        self.next_placement()

    def next_placement(self):
        if not self.placement:
            self.finish_placement()
            return
        kind, what = self.placement.pop(0)
        self.state = "placement"
        if kind == "skill":                                        # a probe of B9.1 for this skill
            text, answer = self.C["PROBES"][what]
            if what == "number_recognition":
                answer = int(self.rng.integers(1, 10))
                text = f"[shows the digit {answer}] What number is this?"
            self.current_q = {"topic": self.topic, "skill": what}
            self.ask("placement", text, answer=answer, skill=what)
            return
        difficulty = 1 if self.start_easy else 2
        a, b = self.F["make_question"](what, difficulty, self.rng)
        self.current_q = {"topic": what, "a": a, "b": b, "difficulty": difficulty,
                          "has_carry": self.F["needs_carry"](what, a, b)}
        self.ask("placement", self.F["word_problem"](what, a, b, self.interest),
                 answer=self.F["correct_answer"](what, a, b), fraction=what == "fractions")

    def placement_answer(self, given, mode, hesitant, attention):
        right = self.F["value"](given) == self.F["value"](self.prompt["answer"])
        skill = self.current_q.get("skill")
        if skill:                                                  # a skill probe: 1 / 0.5 (unsure) / 0
            graded = 0.0 if not right else 0.5 if hesitant == 1 else 1.0
            self.placement_result[skill] = graded
            self.arrow("TUTOR", "B10", f"placement answer {skill} = {graded} (one more placement test for B10's data; "
                                       "the map used in this lesson was mined in advance)")
        else:                                                      # a question of the topic -> B6 log
            self.log_answer(self.current_q, mode, hesitant, attention, right)
        self.say(str(self.rng.choice(["OK, thank you!", "Got it.", "Thanks – next one."])))
        self.next_placement()

    def skip_placement(self):
        self.note(f"Placement test skipped after {self.placement_total - len(self.placement)} questions")
        self.placement = []
        self.finish_placement()

    def finish_placement(self):
        F, topic = self.F, self.topic
        result = self.placement_result
        known = [s for s, v in result.items() if v]
        missing = [s for s, v in result.items() if v == 0]        # None = not asked (skipped)
        mastery = self.mastery()
        self.arrow("B6", "TUTOR", f"{topic} mastery after the placement test: {mastery[topic]:.0f} %", "b6_mastery()")
        self.state = "placement_done"
        if known:
            self.say("You already know: " + ", ".join(SKILL_NAMES[s] for s in known) + ".")
        difficulty = 1 if self.start_easy or self.pace["start_easy"] or mastery[topic] < 50 else 2
        self.difficulty = difficulty
        if not missing:
            self.say(f"You know all the parts of {topic}! Let's practise with real questions.")
            self.next_question()
            return
        root = missing[0]                                          # the most basic missing skill (map order)
        a, b = F["make_question"](topic, difficulty, self.rng)
        self.question = {"topic": topic, "a": a, "b": b, "difficulty": difficulty,
                         "has_carry": F["needs_carry"](topic, a, b), "given": "-",
                         "case": {"error_type": "-", "attention": "-"}}
        self.diagnoses.append({"question": f"placement test of {topic}", "error_type": "-", "attention": "-",
                               "root_cause": root, "probability": 1.0, "round": 0,
                               "probes": [[s, v] for s, v in result.items() if v is not None]})
        steps = F["b9_learning_path"](root, topic, 1, self.interest, skill_map=self.C["B10_SKILL_MAP"],
                                      seed=int(self.rng.integers(10**6)))
        self.arrow("B10", "TUTOR", "teaching order from the discovered skill map", "b9_learning_path(skill_map=B10_SKILL_MAP)")
        if self.interest:
            self.arrow("B1", "TUTOR", f"practice items about {self.interest}", "practice_item()")
        self.say(f"Not yet: {', '.join(SKILL_NAMES[s] for s in missing)}. We start with {SKILL_NAMES[root]}. "
                 f"Our plan: {' → '.join(SKILL_NAMES[s['skill']] for s in steps)}, and then {topic} questions.")
        self.path = {"steps": steps, "step": 0, "streak": 0, "tried": 0, "queue": []}
        self.start_step()

    def set_topic(self, topic):
        if topic not in self.C["TOPICS"]:
            raise BadAnswer("Unknown topic.")
        if self.state not in ("question", "chat_topic"):
            raise BadAnswer("Finish the current diagnosis or practice first.")
        self.topic, self.streak, self.round = topic, 0, 1
        self.say(f"OK, let's switch to {topic}.")
        self.next_question()

    # ------------------------------------------------------------ questions
    def next_question(self, retest=False, same_kind=False):
        F = self.F
        if retest or same_kind:                               # new numbers, same topic, same carry / no carry
            q = self.question if retest else self.current_q
            for _ in range(500):
                a, b = F["make_question"](q["topic"], q["difficulty"], self.rng)
                if F["needs_carry"](q["topic"], a, b) == q["has_carry"]:
                    break
            topic, difficulty = q["topic"], q["difficulty"]
        else:
            topic, difficulty = self.topic, self.difficulty
            a, b = F["make_question"](topic, difficulty, self.rng)
        correct = F["correct_answer"](topic, a, b)
        text = F["word_problem"](topic, a, b, self.interest)
        if retest and self.question.get("given") == "-":           # after the placement test's learning path
            text = f"Now a real {topic} question: " + text
        elif retest:
            text = "Now one like the first question again: " + text
        elif same_kind:
            text = "One more of the same kind: " + text
        self.state = "retest" if retest else "question"
        self.current_q = {"topic": topic, "a": a, "b": b, "difficulty": difficulty,
                          "has_carry": F["needs_carry"](topic, a, b)}
        self.ask("retest" if retest else "question", text, answer=correct, fraction=topic == "fractions")

    def attention(self, camera):
        # B4: live camera features from the browser, or one of the demo's camera presets (notebook CAMERA)
        F = self.F
        if camera and camera.get("features"):
            f = camera["features"]
            r = F["b4_detect_attention"](f.get("screen_gaze_ratio"), f.get("head_angle"), f.get("blink_rate"))
            source = "live camera"
        else:
            preset = (camera or {}).get("preset", "attentive")
            if preset not in self.C["CAMERA"]:
                raise BadAnswer("Unknown camera preset.")
            r = F["b4_detect_attention"](*self.C["CAMERA"][preset])
            source = f"camera preset '{preset}'"
        self.arrow("STUDENT", "B4", f"{source}: {r['state']} (p = {r['probabilities'][r['state']]:.2f})",
                   "b4_detect_attention()")
        state = r["state"]
        topic = self.current_q["topic"] if getattr(self, "current_q", None) else self.topic
        self.last_cost = None
        if state != "attentive" and topic:
            # B6 asked twice: P(correct) with this attention vs. if attentive -> what the distraction costs now
            cost = self.F["b6_attention_cost"](self.log_frame(), topic, state)
            self.last_cost = {"attention": state, "topic": topic, "cost": round(cost, 1)}
            limit = self.pace["break_cost"]
            take_break = cost >= limit and self.since_break >= MIN_ANSWERS_BETWEEN_BREAKS
            self.arrow("B6", "TUTOR", f"being {state} costs {cost:.0f} points on {topic} (break at ≥ {limit})"
                       + (" -> break before the next item" if take_break else ""), "b6_attention_cost()")
            if take_break:
                self.break_pending = (cost, state, topic)
        return state

    def answer(self, data):
        if self.state not in ("question", "retest", "probe", "practice", "placement"):
            raise BadAnswer("There is no question to answer right now.")
        given = parse_answer(data.get("value", ""), self.prompt["fraction"])
        mode = data.get("mode") if data.get("mode") in ("keyboard", "handwriting", "speech") else "keyboard"
        hesitant = float(data.get("hesitant", -1)) if mode == "speech" else -1.0
        read = data.get("read") or {}
        text = self.F["as_text"](given)
        if mode == "handwriting":
            self.arrow("STUDENT", "B3", f"handwritten answer, {read.get('boxes', '?')} digit box(es)")
            self.arrow("B3", "TUTOR", f"read {read.get('read', text)}" +
                       (f" (p = {read['p']})" if read.get("p") else "") +
                       (f", corrected to {text}" if str(read.get("read", text)) != text else ""), "b3_read_drawing()")
        elif mode == "speech":
            self.arrow("STUDENT", "B5a", "spoken answer (microphone)")
            self.arrow("B5a", "TUTOR", f"heard {read.get('read', text)}" +
                       (f" (p = {read['p']})" if read.get("p") else "") +
                       (f", corrected to {text}" if str(read.get("read", text)) != text else ""),
                       "personal model from b5a_calibrate()" if read.get("personal") else "b5a_recognize_speech()")
            self.arrow("STUDENT", "B5b", f"voice: {'hesitant' if hesitant == 1 else 'confident'}"
                       + (f" (p_hesitant = {read['p_hesitant']})" if read.get("p_hesitant") is not None else ""),
                       "b5b_detect_confidence()")
        self.child(text + (" (sounded unsure)" if hesitant == 1 else ""), mode)
        self.since_break += 1
        attention = self.attention(data.get("camera"))
        if self.state == "placement":
            self.placement_answer(given, mode, hesitant, attention)
        elif self.state in ("question", "retest"):
            self.question_answer(given, mode, hesitant, attention)
        elif self.state == "probe":
            self.probe_answer(given, hesitant)
        else:
            self.practice_answer(given, hesitant)

    def log_answer(self, q, mode, hesitant, attention, is_correct):
        # One graded answer -> the B6 log (the input of B6 and later B8); returns the new mastery
        self.log.append({"student_id": "WEB", "seq": len(self.log), "day": 0, "topic": q["topic"],
                         "difficulty": q["difficulty"], "attention": attention,
                         "answer_mode": "speech" if mode == "speech" else "handwriting",
                         "is_hesitant": hesitant if hesitant >= 0 else np.nan, "is_correct": int(is_correct)})
        self.arrow("TUTOR", "B6", f"{q['topic']} answer logged as {'correct' if is_correct else 'wrong'}")
        self.arrow("B4", "B6", f"attention = {attention}")
        if hesitant >= 0:
            self.arrow("B5b", "B6", f"hesitant = {int(hesitant)}")
        mastery = self.mastery()
        self.history.append({"n": len(self.log), "topic": q["topic"], "correct": is_correct, "mastery": mastery})
        self.note(f"B6 b6_mastery(): {q['topic']} mastery is now {mastery[q['topic']]:.0f} %")
        return mastery

    def question_answer(self, given, mode, hesitant, attention):
        F, q = self.F, self.current_q
        correct = self.prompt["answer"]
        if F["value"](given) <= 0:
            self.say("Hmm, that can't be right. Have another look and try again.")
            return
        is_correct = F["value"](given) == F["value"](correct)
        mastery = self.log_answer(q, mode, hesitant, attention, is_correct)

        if is_correct:
            self.update_profile()
            if self.state == "retest":
                self.say("Yes! You learned it. That is exactly what we practised.")
            else:
                self.say(str(self.rng.choice(["Correct, well done!", "Yes, that's right!", "Great job!"])))
            self.round = 1
            if hesitant == 1:
                # B5b: right but unsure -> maybe a guess. One more of the same kind before it counts for levelling up.
                self.say("You sounded a bit unsure, so let's do one more of the same kind.")
                self.note("B5b hesitant + correct: the answer does not count towards levelling up")
                self.next_question(same_kind=True)
                return
            self.streak += 1
            new_topic = F["next_topic"](mastery, q["topic"])
            if new_topic != q["topic"]:
                # B6: the topic is mastered -> the first topic of the curriculum that is not mastered yet
                self.arrow("B6", "TUTOR", f"{q['topic']} mastered ({mastery[q['topic']]:.0f} % ≥ {self.C['MASTERED_AT']}) "
                                          f"-> next topic {new_topic} ({mastery[new_topic]:.0f} %)", "next_topic()")
                self.say(f"You have learned {q['topic']}! Now let's start with {new_topic}.")
                self.topic, self.streak = new_topic, 0
                self.difficulty = 1 if self.pace["start_easy"] or mastery[new_topic] < 50 else 2
            elif self.streak >= self.pace["level_up_after"] and self.difficulty < 3:
                self.difficulty += 1
                self.streak = 0
                self.say(f"{self.pace['level_up_after']} in a row! Let's try harder ones.")
            self.next_question()
            return

        self.streak = 0
        a_text, b_text, given_text = F["as_text"](q["a"]), F["as_text"](q["b"]), F["as_text"](given)
        if self.state == "retest":
            self.round += 1
        if self.round > MAX_ROUNDS:
            self.say("This kind of question is still hard. I'll show it to your teacher, and we go on with easier ones.")
            self.round, self.difficulty = 1, max(1, self.difficulty - 1)
            self.next_question()
            return
        b7 = F["b7_error_type"](q["topic"], a_text, b_text, given_text)
        self.errors.append({"question": f"{a_text} {self.C['SYMBOL'][q['topic']]} {b_text} = {given_text}", **b7})
        self.arrow("TUTOR", "B7", f"{a_text} {self.C['SYMBOL'][q['topic']]} {b_text} = {given_text}")
        self.update_profile()
        topic_mastery = mastery[q["topic"]]
        case = F["b9_case"](q["topic"], a_text, b_text, given_text, attention, hesitant, topic_mastery)
        self.arrow("B7", "B9", f"error type: {case['error_type']}", "b7_error_type()")
        self.arrow("B4", "B9", f"attention: {attention}")
        if hesitant >= 0:
            self.arrow("B5b", "B9", f"hesitant: {int(hesitant)}")
        self.arrow("B6", "B9", f"{q['topic']} mastery: {topic_mastery:.0f} %")
        belief = F["b9_first_guess"](case)
        self.question = {**q, "given": given_text, "case": case}
        self.diag = {"belief": belief, "candidates": F["skills_for_question"](q["topic"], q["has_carry"]), "asked": []}
        top = np.argsort(belief)[::-1][:3]
        self.note("B9 b9_first_guess() (decision tree): " +
                  ", ".join(f"{self.C['B9_CLASSES'][i]} {belief[i]:.0%}" for i in top))
        self.say("Not quite. Before I explain, let me ask you something.")
        self.next_probe()

    # ------------------------------------------------------------ B9: one probe per request
    def next_probe(self):
        d = self.diag
        skill = self.F["b9_next_probe"](d["belief"], d["candidates"], len(d["asked"]))
        if skill is None:
            self.finish_diagnosis()
            return
        text, answer = self.C["PROBES"][skill]
        if skill == "number_recognition":                     # a random digit each time, shown as an MNIST image
            answer = int(self.rng.integers(1, 10))
            text = f"[shows the digit {answer}] What number is this?"
        self.state = "probe"
        self.note(f"B9 b9_next_probe(): the probe with the lowest expected entropy is '{skill}'")
        self.ask("probe", text, answer=answer, skill=skill)

    def probe_answer(self, given, hesitant):
        F, d = self.F, self.diag
        skill = self.prompt["skill"]
        right = F["value"](given) == F["value"](self.prompt["answer"])
        graded = 0.0 if not right else 0.5 if hesitant == 1 else 1.0
        self.arrow("TUTOR", "B9", f"probe {skill} = {graded}")
        d["belief"] = F["bayes_update"](d["belief"], skill, graded)
        d["candidates"].remove(skill)
        d["asked"].append([skill, graded])
        top = np.argsort(d["belief"])[::-1][:3]
        self.note("B9 bayes_update(): " + ", ".join(f"{self.C['B9_CLASSES'][i]} {d['belief'][i]:.0%}" for i in top))
        self.say("Thanks!" if right else "OK, thank you.")
        self.next_probe()

    def finish_diagnosis(self):
        F, C, q = self.F, self.C, self.question
        d = self.diag
        result = F["b9_decision"](d["belief"], [tuple(x) for x in d["asked"]])
        root = result["root_cause"]
        self.arrow("B9", "TUTOR", f"root cause: {root} ({result['probability']:.0%})", "b9_decision()")
        self.diagnoses.append({"question": f"{F['as_text'](q['a'])} {C['SYMBOL'][q['topic']]} {F['as_text'](q['b'])}"
                                           f" = {q['given']}", "error_type": q["case"]["error_type"],
                               "attention": q["case"]["attention"], "root_cause": root,
                               "probability": result["probability"], "probes": d["asked"], "round": self.round})
        self.diag = None
        steps = F["b9_learning_path"](root, q["topic"], q["has_carry"], self.interest,
                                      skill_map=C["B10_SKILL_MAP"], seed=int(self.rng.integers(10**6)))
        self.arrow("B10", "TUTOR", "teaching order from the discovered skill map", "b9_learning_path(skill_map=B10_SKILL_MAP)")
        if self.interest:
            self.arrow("B1", "TUTOR", f"practice items about {self.interest}", "practice_item()")
        if root == "careless":
            attention = q["case"]["attention"]
            self.say("You know how to do this – I think it was just a small slip. Always check your answer once more!"
                     + (f" You look {attention}; let's take a short break after this one." if attention != "attentive" else ""))
            self.round = 1
            self.next_question()
            return
        if self.round == MAX_ROUNDS:
            self.say(f"I think {SKILL_NAMES[root]} is still missing. I'll tell your teacher, and we'll practise it next time.")
            self.round, self.difficulty = 1, max(1, self.difficulty - 1)
            self.next_question()
            return
        names = " → ".join(SKILL_NAMES[s["skill"]] for s in steps)
        self.say(f"I found it! We need to practise {SKILL_NAMES[root]} first. Our plan: {names}, "
                 "and then the first question again.")
        self.path = {"steps": steps, "step": 0, "streak": 0, "tried": 0, "queue": []}
        self.start_step()

    # ------------------------------------------------------------ learning path
    def start_step(self):
        step = self.path["steps"][self.path["step"]]
        self.path.update(streak=0, tried=0, queue=list(step["items"]))
        self.out.append({"type": "tip", "skill": step["skill"], "name": SKILL_NAMES[step["skill"]], "text": step["tip"]})
        self.next_item()

    def next_item(self):
        step = self.path["steps"][self.path["step"]]
        if self.path["queue"]:
            text, answer = self.path["queue"].pop(0)
        else:
            text, answer = self.F["practice_item"](step["skill"], self.rng, self.interest)
        self.state = "practice"
        self.ask("practice", text, answer=answer, skill=step["skill"])

    def skip_step(self):
        if self.state == "placement":
            self.skip_placement()
            return
        if self.state != "practice":
            raise BadAnswer("Nothing to skip.")
        self.say("OK, let's move on.")
        self.finish_step()

    def practice_answer(self, given, hesitant=-1.0):
        right = self.F["value"](given) == self.F["value"](self.prompt["answer"])
        p = self.path
        p["tried"] += 1
        if right and hesitant == 1:                           # B5b: right but unsure -> does not count yet
            self.say("Right – but you sounded unsure. Let's do another one.")
            self.next_item() if p["tried"] < MAX_ITEMS_PER_STEP else self.finish_step()
            return
        p["streak"] = p["streak"] + 1 if right else 0
        if right:
            self.say(str(self.rng.choice(["Right!", "Correct!", "Yes!"])) + f" ({p['streak']} of {MOVE_ON_STREAK} in a row)")
        else:
            self.say(f"Not quite – it is {self.F['as_text'](self.prompt['answer'])}. Let's try another one.")
        if p["streak"] >= MOVE_ON_STREAK:
            self.say(f"You've got {SKILL_NAMES[p['steps'][p['step']]['skill']]}!")
            self.finish_step()
        elif p["tried"] >= MAX_ITEMS_PER_STEP:
            self.say("Let's go on – we'll come back to this.")
            self.finish_step()
        else:
            self.next_item()

    def finish_step(self):
        self.path["step"] += 1
        if self.path["step"] < len(self.path["steps"]):
            self.start_step()
            return
        self.path = None
        self.next_question(retest=True)

    # ------------------------------------------------------------ B8: profile -> pace
    def characteristic_error(self):
        counts = pd.Series([e["error_type"] for e in self.errors], dtype=object).value_counts()
        if not len(counts):
            return None, None
        share = (counts / counts.sum()).reindex(self.C["ERROR_TYPES"], fill_value=0)
        return str((share / pd.Series(self.X["average_share"])).idxmax()), share

    def update_profile(self):
        # B8 needs a few answers (both correct and wrong) and one B7 error; then its profile sets the pace (b8_pace)
        log = self.log_frame()
        characteristic, _ = self.characteristic_error()
        if len(log) < 6 or log["is_correct"].nunique() < 2 or characteristic is None:
            return
        try:
            row = self.F["b8_student_row"](log, characteristic)
            profile = self.F["b8_student_profile"](**row)
        except Exception:                     # e.g. the learning-speed regression cannot be fitted yet
            return
        profile["row"] = {k: (round(float(v), 3) if k != "characteristic_error" else v) for k, v in row.items()}
        profile["outlier"] = self.F["b8_outlier_check"](**row)       # B8.5b: does the child fit the profile at all?
        changed = not self.profile or profile["profile_id"] != self.profile["profile_id"]
        self.profile = profile
        if changed:
            self.arrow("B6", "B8", "accuracy, learning speed, attention, spoken-answer ratio from the answer log")
            self.arrow("B7", "B8", f"characteristic error = {characteristic}")
            self.pace = self.F["b8_pace"](profile["profile_id"])
            self.arrow("B8", "TUTOR", f"profile '{profile['profile']}' -> pace {self.pace}", "b8_student_profile(), b8_pace()")
            if self.pace["answer_mode"] == "speech":
                self.say("I noticed you like answering out loud – use the 🎤 button whenever you want!")
            elif self.pace["answer_mode"] == "handwriting":
                self.say("I noticed you like writing your answers – the boxes are open for you.")

    # ------------------------------------------------------------ teacher dashboard
    def dashboard(self):
        F, C, X = self.F, self.C, self.X
        log = self.log_frame()
        mastery = self.mastery()
        self.arrow("B6", "DASHBOARD", "mastery at the start and now", "b6_mastery()")
        characteristic, share = self.characteristic_error()
        if characteristic:
            self.arrow("B7", "DASHBOARD", f"characteristic error: {characteristic}", "b7_error_type()")
        self.update_profile()
        profile, profile_note = self.profile, None
        if profile:
            self.arrow("B8", "DASHBOARD", f"profile: {profile['profile']}", "b8_student_profile()")
        else:
            profile_note = "B8 needs at least 6 graded answers, both correct and wrong ones, and one B7 error."
        if self.diagnoses:
            self.arrow("B9", "DASHBOARD", f"{len(self.diagnoses)} diagnoses in this lesson")
        self.arrow("B10", "DASHBOARD", "learning patterns of the class")
        unused = [f"{s} → {t}" for (s, t) in C["DIAGRAM_ARROWS"] if (s, t) not in self.used_arrows]
        return {"mastery_start": self.mastery_start, "mastery": mastery, "history": self.history,
                "topic_answers": self.topic_answers(),
                "answers": len(log), "accuracy": round(float(log["is_correct"].mean()), 3) if len(log) else None,
                "errors": self.errors, "error_share": share.round(3).to_dict() if share is not None else None,
                "characteristic": characteristic, "profile": profile, "profile_note": profile_note, "pace": self.pace,
                "diagnoses": self.diagnoses, "patterns": X["b10_patterns"][:5],
                "arrows_used": len(self.used_arrows), "arrows_total": len(C["DIAGRAM_ARROWS"]), "unused": unused}

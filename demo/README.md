# Live role-play demo

Synthetic only. A made-up patient and chart; do not say any real health information.

## Files
- `script.json`: the 25-turn scripted visit (clinician and patient lines). Same turn format as `data/eval`.
- `chart.json`: the demo patient's synthetic chart (includes a prior coronary stent).
- `expected_flags.json`: the five planted gaps the demo should show. Used to check the rehearsal, never shown to the audience before the reveal.
- `cache/`: rehearsed model outputs (empty until `rehearse.py` is run in Live mode).

## Actor notes (keep these gaps in, they are the point of the demo)
Clinician: do NOT ask about spreading to the arm or jaw; do NOT answer the patient's fear about her heart (go straight to the next question); when the patient says "Sorry, what did you say?" carry on without repeating; give the plan without asking her to repeat it back.
Patient: say line 7 (the fear about her heart), line 15 (mishearing) and line 21 (denies heart problems) exactly as written; answer "Okay." to the plan.

Say the lines close to word for word. Speak clearly, one at a time, pause about a second between turns.

## Stage checklist
Chrome, microphone allowed, quiet room, typed-turn box as fallback, screen recording ready.

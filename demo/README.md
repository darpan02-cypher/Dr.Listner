# Live role-play demo

Synthetic only. A made-up patient and chart; do not say any real health information.

## Files
- `script.json`: the 22-turn scripted visit (Mrs. Wilson) (clinician and patient lines). Same turn format as `data/eval`.
- `chart.json`: the demo patient's synthetic chart (includes a prior coronary stent).
- `expected_flags.json`: the four planted gaps the demo should show. Used to check the rehearsal, never shown to the audience before the reveal.
- `cache/`: rehearsed model outputs (empty until `rehearse.py` is run in Live mode).

## Actor notes (keep these gaps in, they are the point of the demo)
Clinician: never ask about sweating; after the patient asks if her daughter can come, do not answer; when she says she did not catch the transfer plan, do not repeat it.
Patient: say the denial of heart surgery (line 13), the missed-plan line (17) and the daughter question (19) exactly as written.

Say the lines close to word for word. Speak clearly, one at a time, pause about a second between turns.

## Stage checklist
Chrome, microphone allowed, quiet room, typed-turn box as fallback, screen recording ready.

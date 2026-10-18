# Eval dataset (dev + test)

Rebuild: `python -m scripts.build_eval_dataset` (deterministic, no network or API key).
Code: `src/dataset/eval_build.py`, phrase pools in `src/dataset/pools.py`, visit specs in `src/dataset/eval_specs.py`.

| split | visits | clean | missed Q (1) | unanswered concern (2) | chart contradiction (3) | comprehension (4) |
|---|---|---|---|---|---|---|
| dev | 9 | 2 | 4 | 2 | 3 | 4 |
| test | 15 | 5 | 6 | 5 | 5 | 6 |

Counts are gap instances (a visit can have several). Small counts mean wide confidence intervals; always report counts with percentages.

## How it is built
1. A complete, gap-free base visit is assembled from phrase pools (`base/`).
2. Gaps are planted by deterministic edits; the answer key is written from the edit (`answer_keys/`), never from a model.
3. Index convention: deletion indices refer to the base transcript; insertions and replacements refer to the final transcript.
4. `wrap_up_turn` is the clinician turn that starts wrap-up (it also holds the plan and, when present, the teach-back question). Types 1 and 2 are expected at or after this turn.
5. Type-4 edits: `insert_mishearing` replaces a patient answer with an off-topic reply or a repeat request that the clinician does not repair; `delete_teachback` removes the teach-back question and the patient's restatement (the key points at the plan turn).

## Hard negatives (must NOT be flagged)
- Repeat requests that the clinician repairs (repeat/rephrase) then the patient answers correctly.
- Patient concerns that the clinician addresses (mid-visit or at "any other questions?").
- Teach-back present, patient restates the plan.

## Guards
- Leakage lint: each checklist item's keywords may appear only in that item's own turns, so a deleted Q&A cannot leave the item covered elsewhere (build fails otherwise).
- Dev draws from the first half of each phrase pool and test from the second half; only chart-derived answers and plan restatements are shared (tested).
- Concerns appear at varied positions (not always last).

## Limits (say these in the README and slides)
- Charts are hand-authored FHIR-lite, **not Synthea**. Scripts come from our own pools: no clinician review, not drawn from ACI-Bench/MTS-Dialog/PriMock57.
- Gap-4 cues are our own draft. We author both the mishearings and the detector, so gap-4 recall shows the detector finds our cues, not real hearing-loss speech.
- Wording variety is limited (pools of 4 variants per item, 2 per split). Scores here are likely higher than on real visits.
- No real PHI; all personas and details are invented.

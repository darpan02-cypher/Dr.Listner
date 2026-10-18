# Dr.Listner SPEC (v0.2, master prompt v2)

Contracts only. Scope and rationale live in `docs/PROJECT_REPORT.md`. Code in `src/schemas.py` is normative for field names; this file is normative for semantics.

## 1. Principles
- Synthetic data only; `synthetic: true` is required on Transcript and Chart.
- Documentation completeness only. No flag text may suggest a diagnosis or treatment.
- Answer keys are written from the deterministic edit that planted a gap, never from a model's opinion.
- Every metric reported anywhere comes from a file in `eval/results/`.

## 2. Schemas (see `src/schemas.py`)
- **Transcript**: `visit_id`, `chart_id`, `turns[]` of `{idx, speaker: clinician|patient, text}`; idx contiguous from 0.
- **Chart**: FHIR-lite view of a Synthea bundle: `chart_id, age, sex, entries[]` of `{entry_id, resource_type, display, status, date, fhir?}`.
- **Flag**: `flag_id, visit_id, type, evidence[], rationale, verified, dismissed`.
  - `type` in `missed_question | unanswered_concern | chart_contradiction`.
  - Evidence pointer: `{source: transcript|chart|checklist, ref, quote}`. `ref` is a turn idx, a chart `entry_id`, or a checklist item id. `quote` is verbatim and required for transcript/chart sources.
  - Shape rules: missed_question needs a checklist pointer (its absence from the transcript is the finding, so there is no transcript line); unanswered_concern needs a transcript pointer to the patient turn voicing the worry; chart_contradiction needs one transcript and one chart pointer.
- **AnswerKey**: `visit_id, split: dev|test, planted_gaps[], plan_items[]`. Clean visit = no planted gaps. `PlantedGap` = `{gap_id, type, edit_op, turn_indices, checklist_item_id?, chart_entry_id?, description}`. Edit ops: `delete_turns` (type 1), `insert_concern` (type 2), `insert_contradiction` (type 3). `plan_items` are the care-plan items the patient summary must cover.
- **EvalResult**: run metadata (`run_id, system, split, mode, model, git_commit, timestamp`), counts, `per_type` and `overall` TP/FP/FN/precision/recall/F1, `false_flags_per_visit`, clean-visit false flags, mean reading grade, plan coverage.

## 3. Checklist file (`data/checklist/chest_pain.json`)
`{checklist_id, version, source, items[]}`; file lives at `packs/chest_pain/checklist.json`; item = `{id, label, description, example_questions[], guideline_ref, guideline_quote, verification_status: VERIFIED|UNVERIFIED, verification_note}`. `VERIFIED` requires a `guideline_ref`. Status is VERIFIED only after the item was checked against the guideline text. Current state: all 10 items VERIFIED against the guideline text (Section 2.1 and Table 3) by Claude; not clinician-reviewed (see PROGRESS.md). Items carry `guideline_quote`.

## 4. Eval definitions
Evaluated per visit on flags that survive the VerifierAgent (dismissed flags are not removed; dismissal is UI-only).

**Matching rule** (a flag matches at most one planted gap and vice versa; greedy one-to-one):
- missed_question: same type and flag's checklist pointer `ref == checklist_item_id`.
- unanswered_concern: same type and a flag transcript pointer `ref` is in the gap's `turn_indices`.
- chart_contradiction: same type and the flag's chart pointer `ref == chart_entry_id`, or its transcript pointer is in `turn_indices`.

**TP**: a flag matched to a planted gap. **FP**: a flag matched to no planted gap (including any flag on a clean visit, and duplicates beyond the first match). **FN**: a planted gap with no matching flag.
precision = TP/(TP+FP), recall = TP/(TP+FN), F1 = harmonic mean; undefined (null) when the denominator is 0. Per type and overall, micro-averaged over the split. `false_flags_per_visit` = total FP / visits. Counts are always reported with the percentages.

Caveat: an unplanted but genuine gap in a generated script counts as FP. Scripts are generated to cover the whole checklist and spot-read to limit this.

**Baseline**: an LLM writes a scribe-style note, then a single prompt lists anything missing, with no checklist, chart agent or verifier. Its flags are scored with the same matching rule.

**Splits**: tune on dev only; test is run at the end of Phase 4 and at final submission, reported as-is.

## 5. Agent contracts
All agents are pure functions of their inputs plus an `LLMClient`; the orchestrator is deterministic Python.

| Component | Input | Output |
|---|---|---|
| deid | text | scrubbed text (Presidio). Runs before any hosted call. |
| ChecklistAgent | scrubbed Transcript, Checklist | candidate Flags (missed_question) |
| ConcernAgent | scrubbed Transcript | candidate Flags (unanswered_concern) |
| ChartAgent | scrubbed Transcript, Chart | candidate Flags (chart_contradiction) |
| VerifierAgent | candidate Flag, Transcript, Chart | Flag with `verified=True`, or dropped. (a) programmatic: pointed turn/entry exists and quote is a substring (whitespace-normalized); for missed_question, the checklist id exists. (b) LLM: evidence supports the flag. |
| SummaryAgent | Transcript, verified Flags, plan items | patient summary text; loop: score with textstat, rewrite with the score as feedback, max 3 iterations, ship best attempt, log final grade |

Each LLM-backed agent has its own prompt, a Pydantic output schema, and tests.

## 6. LLM client
One wrapper (`src/llm/client.py`). `generate(prompt, schema, system)` returns a validated Pydantic object. LIVE: cache, then providers in order (default Groq `openai/gpt-oss-120b`, then Gemini, then Ollama; JSON mode, retries with exponential backoff), else `LLMUnavailable`. Order is set by `LLM_PROVIDERS`. Groq was added at the user's request; live Groq JSON calls verified with a smoke test. DEMO: cache only, miss raises `DemoCacheMiss`, no network. Cache key is sha256 over model, system prompt and prompt (including the schema); the cache file stores the response, not the prompt.

## 7. Privacy
No real PHI. No transcript storage by the app. The committed LLM cache holds model outputs on synthetic data only. No HIPAA claim.

## 8. v2 deltas (override the report)
- **Timing:** the engine processes a visit turn by turn through `process_turn(state, turn) -> state`; batch mode is a fold over all turns. Input arrives via a `TurnSource` (`ReplaySource` implemented; typed/mic sources are out of scope for the 2026-10-21 deadline).
- **Patient focus:** `PatientProfile` (hearing level, literacy, caregiver present, active detectors, summary limits, teach-back count). Two demo profiles in `packs/chest_pain/profiles/`.
- **Gap type 4, `comprehension_breakdown`:** patient shows they did not hear or understand and the clinician does not repair it (repeat, rephrase, confirm, teach-back). Cues are our own **draft**, not clinically validated: repeat requests ("what?"), answer mismatched to the question just asked, bare "okay/yes" after a multi-part instruction (low confidence, likely noisy), plan/medication/warning-sign instruction with no teach-back. Because we author the planted mishearings, gap-4 recall measures whether the detector finds our cues, not real hearing-loss speech.
- **Speakers:** `clinician | patient | caregiver`. `Turn` has optional `t_start`/`t_end`.
- **Packs:** `packs/chest_pain/` holds checklist and profiles (retrieval corpus added in Phase 5). Only chest pain is built.

### Surfacing rules
- During the visit: coverage ticks and at most passive badges for types 3 and 4. No pop-ups.
- At wrap-up: unasked red flags (1), unanswered concerns (2), unrepaired comprehension (4), then a clarify card of at most 3 items.
- Types 1 and 2 are never raised before wrap-up. All flags dismissible; dismissals logged.

### Eval additions
- Each event is **one flag**, emitted once with `raised_at_turn`. A live badge and a wrap-up list item for the same event are the same flag (no double counting).
- **Wrap-up turn:** the answer key records `wrap_up_turn`. Headline eval uses it; closing-phrase detection is scored separately.
- **Flags raised too early** = any type 1 or 2 flag with `raised_at_turn < wrap_up_turn`.
- **Turns-to-detection** (types 3, 4) = `raised_at_turn` minus the planted turn.
- **Matching, type 4:** `insert_mishearing` -> same type and a flag transcript pointer in `turn_indices`. `delete_teachback` -> same type and a flag transcript pointer at the plan-instruction turn recorded in `turn_indices` (the turn that lacks teach-back).
- Per-type counts always reported with percentages; gap-4 test counts will be small.

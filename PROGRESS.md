# PROGRESS

## Phase 1 — Foundation & spec
**Done**
- Repo skeleton, `SPEC.md`, Pydantic schemas, draft checklist JSON, LLM client (cache, retry/backoff, Gemini→Ollama fallback, DEMO/LIVE), config.
- Project report converted from `Project-SRS.docx` to `docs/PROJECT_REPORT.md`.
- v2 delta applied: gap type 4, caregiver speaker, timed turns, PatientProfile + 2 profiles, VisitState, `process_turn` stub, ReplaySource, packs layout. 24 tests pass.

**Checklist verification: 10 of 10 items VERIFIED** against the full guideline text (Section 2.1 History and Table 3, pages e377-e378), matched by Claude, **not clinician-reviewed**. Changes from the report's draft of 8: added `nature` and `relieving` (named in Sec 2.1's six history elements); merged "duration" into `onset` (Table 3 row "Onset and duration"); `risk_factors` cites Sec 2.1 rec 1; `family_history` cites Sec 2.1 supportive text (the guideline says "family and social history" generally; "premature CAD" appears only in 2.1.1 trial data). Not included: Table 3 "Severity" row. If you want the original 8 only, delete `nature` and `relieving`.

**Live-verified**: Groq (`openai/gpt-oss-120b` and `-20b` return schema-valid JSON). **Not exercised**: live Gemini (no key) and live Ollama (not installed). Both paths are tested only against mocked HTTP. Run `python -m scripts.smoke_llm` with a key / Ollama to confirm.

**Next**: Complete Phase 2 provenance/validation tasks below, then implement de-identification and detection agents.

**Risks**
- Gemini model name default (`gemini-2.5-flash`) is unverified for today's free tier; set `GEMINI_MODEL`.
- Hosted LIVE checklist matching is LLM-only (no embeddings at runtime).
- ~25 visits gives wide intervals on per-type metrics.
- Python 3.12.4 verified in the current local environment; Streamlit Cloud's Python version and Presidio/spaCy model footprint under 690 MB are unchecked (Phase 6).


## Phase 2 — Synthetic development dataset (in progress)
**Implemented**
- Reproducible offline builder: `python -m scripts.build_dataset`.
- 29 paired synthetic visits/charts (covering all 10 checklist items), saved original transcripts, deterministic
  gap edits, and separate answer keys with plan items and edit provenance.
- 3 clean controls, 10 missed-question cases, 3 concern cases, 3 contradiction
  cases, and 10 mixed cases. All are development fixtures, not a held-out test.
- FHIR-lite Synthea bundle adapter and `scripts.import_synthea` CLI with explicit
  synthetic attestation, patient-reference filtering, and reference-date age.
- Tests for reproducibility, dataset links, mixed-edit indices for all checklist
  items, and FHIR mapping/rejection behavior.

**Remaining**
- Checklist is matched to the guideline (10/10) but not clinician-reviewed.
- Known gaps vs master prompt v2: no gap type 4, caregiver turns or `wrap_up_turn`; all
  visits are dev (no test split); only 3 clean controls (need 5+); templated wording and
  positional tells (concern is always the last turn) make it unsuitable for tuning or
  reporting metrics. Use as a contract/engine fixture only.
- Included charts are hand-authored. Generate actual Synthea bundles and exercise
  the importer against them; independently author matching visit scripts.
- Review script coverage and variety, and freeze independent dev/test data.
- No accuracy measurements, populated model cache, detection agents, or UI yet.


## Phase 2b — Eval dataset (awaiting gate: user spot-read)
- `data/eval/`: 9 dev + 15 test visits (7 clean total), all four gap types, caregiver visits, hard negatives (repaired repeat requests, addressed concerns), `wrap_up_turn`, base transcripts and keys from edits. 44 tests pass (key reconciliation, determinism, dev/test phrasing disjoint, leakage lint).
- Test gap counts: type 1: 6, type 2: 5, type 3: 5, type 4: 6. Small; report counts with percentages.
- **Limits:** charts hand-authored (not Synthea); pool phrasing (limited variety); no clinician review; gap-4 cues are our draft and we author both sides, so gap-4 numbers show cue detection, not real hearing-loss speech.
- **Gate:** user spot-reads 5 transcripts including 2 gap-4 cases (suggested: eval-test-14, eval-test-10, eval-dev-08, eval-test-03, eval-test-12).


## Phase 3 — De-id, agents, engine (implemented; detector quality NOT yet measured)
**Implemented** (details in SPEC.md section 10): `src/deid.py` (Presidio + spaCy `en_core_web_sm`, clinical keep-list), `src/agents/{checklist,concern,chart_agent,comprehension,verifier,summary}.py`, engine wiring (`EngineContext`, per-turn types 3/4, `finalize` for types 1/2 + teach-back, verification, failure recording in `VisitState.errors`), `Retry-After` handling for 429 in the LLM client. 62 tests pass; agents and engine are tested against a scripted fake LLM, deid against real Presidio.

**Live smoke (Groq `gpt-oss-120b`, dev only, 2 visits, not a measurement):**
- eval-dev-08 (2 planted type-4 gaps): both found (turn 19 repeat-reply, turn 28 no teach-back), plus 1 extra concern flag.
- eval-dev-01 (clean): still 3 flags after one round of prompt tightening (first run: 6). Remaining false flags are plain symptom answers read as concerns / mishearings, which the verifier LLM also accepted. Needs Phase 4 tuning on dev with a scored harness.
- Some calls hit Groq's 8,000 tokens/min limit and gave up after 3 tries (visible in logs; recorded in `state.errors`). A full visit is about 20-30 calls, so LIVE passes are slow; cached reruns are instant.

**Not done / open**
- No precision/recall numbers yet: there is no scoring harness (Phase 4). Do not quote the smoke results as metrics.
- Test split untouched. Prompts were adjusted after looking at dev-01 and dev-08 only.
- Summary agent is tested with a fake LLM only; never run live. Plan coverage of summaries is unmeasured.
- Per-turn coverage ticks (UI) are not implemented; `checklist_coverage` is filled only at `finalize`.
- `requirements.txt` still lacks the spaCy model (`en_core_web_sm`). Hosted deploy needs it as a wheel URL line; I did not edit `requirements.txt` (outside this phase's file list). Footprint on Streamlit Cloud unchecked.
- The small NER model tags some capitalized words as PERSON (e.g. sentence-initial "Clearer"); drug names are handled by the keep-list. De-id is best-effort.
- `data/llm_cache/` has new untracked entries from the smoke runs (dev-only synthetic text); decide whether to commit.

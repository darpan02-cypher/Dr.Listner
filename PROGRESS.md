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

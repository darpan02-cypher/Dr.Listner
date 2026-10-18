# PROGRESS

## Phase 1 — Foundation & spec (awaiting gate approval)
**Done**
- Repo skeleton, `SPEC.md`, Pydantic schemas, draft checklist JSON, LLM client (cache, retry/backoff, Gemini→Ollama fallback, DEMO/LIVE), config.
- Project report converted from `Project-SRS.docx` to `docs/PROJECT_REPORT.md`.
- v2 delta applied: gap type 4, caregiver speaker, timed turns, PatientProfile + 2 profiles, VisitState, `process_turn` stub, ReplaySource, packs layout. 24 tests pass.

**Checklist verification: 10 of 10 items VERIFIED** against the full guideline text (Section 2.1 History and Table 3, pages e377-e378), matched by Claude, **not clinician-reviewed**. Changes from the report's draft of 8: added `nature` and `relieving` (named in Sec 2.1's six history elements); merged "duration" into `onset` (Table 3 row "Onset and duration"); `risk_factors` cites Sec 2.1 rec 1; `family_history` cites Sec 2.1 supportive text (the guideline says "family and social history" generally; "premature CAD" appears only in 2.1.1 trial data). Not included: Table 3 "Severity" row. If you want the original 8 only, delete `nature` and `relieving`.

**Live-verified**: Groq (`openai/gpt-oss-120b` and `-20b` return schema-valid JSON). **Not exercised**: live Gemini (no key) and live Ollama (not installed). Both paths are tested only against mocked HTTP. Run `python -m scripts.smoke_llm` with a key / Ollama to confirm.

**Next**: Phase 2 (Synthea charts, scripted visits, planted gaps, answer key).

**Risks**
- Gemini model name default (`gemini-2.5-flash`) is unverified for today's free tier; set `GEMINI_MODEL`.
- Hosted LIVE checklist matching is LLM-only (no embeddings at runtime).
- ~25 visits gives wide intervals on per-type metrics.
- Python 3.14 locally; Streamlit Cloud's Python version and Presidio/spaCy model footprint under 690 MB are unchecked (Phase 6).

# PROGRESS

## Phase 1 — Foundation & spec
**Done**
- Repo skeleton, `SPEC.md`, Pydantic schemas, draft checklist JSON, LLM client (cache, retry/backoff, Gemini→Ollama fallback, DEMO/LIVE), config.
- Project report converted from `Project-SRS.docx` to `docs/PROJECT_REPORT.md`.
- 17 unit tests pass (schemas, checklist file, LLM client with mocked HTTP).

**Checklist verification: 0 of 8 items VERIFIED, 8 UNVERIFIED.** I confirmed from the ACC "Guidelines Made Simple" summary that Section 2.1 (History) and Table 3 (Chest Pain Characteristics and Corresponding Causes) exist. The primary guideline text returned HTTP 403, so Table 3's contents are unread. Shortness of breath is supported at summary level only. Someone with access to the full text needs to check each item.

**Not exercised**: live Gemini (no API key in this environment) and live Ollama (not installed). Both paths are tested only against mocked HTTP. Run `python -m scripts.smoke_llm` with a key / Ollama to confirm.

**Next**: Complete Phase 2 provenance/validation tasks below, then implement de-identification and detection agents.

**Risks**
- Gemini model name default (`gemini-2.5-flash`) is unverified for today's free tier; set `GEMINI_MODEL`.
- Hosted LIVE checklist matching is LLM-only (no embeddings at runtime).
- ~25 visits gives wide intervals on per-type metrics.
- Python 3.12.4 verified in the current local environment; Streamlit Cloud's Python version and Presidio/spaCy model footprint under 690 MB are unchecked (Phase 6).


## Phase 2 — Synthetic development dataset (in progress)
**Implemented**
- Reproducible offline builder: `python -m scripts.build_dataset`.
- 25 paired synthetic visits/charts, saved original transcripts, deterministic
  gap edits, and separate answer keys with plan items and edit provenance.
- 3 clean controls, 8 missed-question cases, 3 concern cases, 3 contradiction
  cases, and 8 mixed cases. All are development fixtures, not a held-out test.
- FHIR-lite Synthea bundle adapter and `scripts.import_synthea` CLI with explicit
  synthetic attestation, patient-reference filtering, and reference-date age.
- Tests for reproducibility, dataset links, mixed-edit indices for all checklist
  items, and FHIR mapping/rejection behavior.

**Remaining**
- Checklist verification is still 0/8; no clinical validation claimed.
- Included charts are hand-authored. Generate actual Synthea bundles and exercise
  the importer against them; independently author matching visit scripts.
- Review script coverage and variety, and freeze independent dev/test data.
- No accuracy measurements, populated model cache, detection agents, or UI yet.

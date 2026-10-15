# PROGRESS

## Phase 1 — Foundation & spec (awaiting gate approval)
**Done**
- Repo skeleton, `SPEC.md`, Pydantic schemas, draft checklist JSON, LLM client (cache, retry/backoff, Gemini→Ollama fallback, DEMO/LIVE), config.
- Project report converted from `Project-SRS.docx` to `docs/PROJECT_REPORT.md`.
- 17 unit tests pass (schemas, checklist file, LLM client with mocked HTTP).

**Checklist verification: 0 of 8 items VERIFIED, 8 UNVERIFIED.** I confirmed from the ACC "Guidelines Made Simple" summary that Section 2.1 (History) and Table 3 (Chest Pain Characteristics and Corresponding Causes) exist. The primary guideline text returned HTTP 403, so Table 3's contents are unread. Shortness of breath is supported at summary level only. Someone with access to the full text needs to check each item.

**Not exercised**: live Gemini (no API key in this environment) and live Ollama (not installed). Both paths are tested only against mocked HTTP. Run `python -m scripts.smoke_llm` with a key / Ollama to confirm.

**Next**: Phase 2 (Synthea charts, scripted visits, planted gaps, answer key).

**Risks**
- Gemini model name default (`gemini-2.5-flash`) is unverified for today's free tier; set `GEMINI_MODEL`.
- Hosted LIVE checklist matching is LLM-only (no embeddings at runtime).
- ~25 visits gives wide intervals on per-type metrics.
- Python 3.14 locally; Streamlit Cloud's Python version and Presidio/spaCy model footprint under 690 MB are unchecked (Phase 6).

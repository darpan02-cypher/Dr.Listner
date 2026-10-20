# Dr.Listner: catching what the visit missed

Oct 15, 2026 (updated Oct 19, 2026) · @himanshi

AI scribes record what was said; Dr.Listner flags what was never asked, answered or understood, and hands the patient a plain-language plan they can actually follow. IEEE Hack for Humanity, Track 2: AI for Accessibility and Disability Inclusion.

## The problem

Roughly 1 in 20 US adults is misdiagnosed in outpatient care each year, and the people least able to catch a gap in the visit are the ones most exposed to it.

- Diagnostic error is common. About 12 million US adults a year, around half potentially harmful (BMJ Quality & Safety, 2014). The Institute of Medicine's 2015 report puts the rate at 5% of US adults who seek outpatient care each year and links errors in part to inadequate communication among clinicians, patients and families (National Academies, 2015).

- Hearing loss is the norm in older patients. Disabling hearing loss affects 22% of US adults aged 65 to 74 and 55% of those 75 and older, and only about 30% of adults 70+ who could benefit from hearing aids have ever used them (NIDCD, NIH). Fewer than a quarter of studies on physician communication with older patients even mention hearing loss (Cohen et al., JAGS).

- Low health literacy is the majority. In the 2003 national survey, only 12% of US adults had proficient health literacy and 36% were at basic or below basic (NCES, U.S. Department of Education, 2006). These are the latest figures we found for this survey; they are 2003 data.

- Patients forget the plan. 40% to 80% of the medical information clinicians give is forgotten immediately, and almost half of what is remembered is incorrect (Kessels, Journal of the Royal Society of Medicine, 2003).

- Hearing loss lowers rated communication quality in a nationally representative US sample (study in PMC).

## Market gap

Ambient scribes are built to document the conversation; nobody is checking the conversation itself for what is missing, and no one is writing for the patient.

|  | Ambient AI scribes today | Dr.Listner |
|---|---|---|
| Core job | Draft the visit note from what was said | Flag what was not said, not resolved or not understood |
| Known failure | Omissions and made-up content in the note; omissions were the top error in a 356-note audit (64 notes, 18%) (JMIR Med Inform, 2026) | Misses are surfaced with the transcript line that triggered them, so the clinician can verify in seconds |
| Clinician experience | Note to review and edit | Quiet coverage ticks during the visit, one end-of-visit gaps list and a clarify card of at most 3 items; no pop-ups, to avoid alert fatigue |
| Patient experience | Notes written for clinicians | Plain-language care summary, captions, read-aloud, questions to ask next time |
| Who it helps most | Clinician workload | Patients with hearing loss, low health literacy or cognitive impairment |

Caveat: this compares the category as described in published audits; we have not audited individual vendors. Scribe omissions (things said but dropped from the note) are a different problem from visit omissions (things that should have been asked); Dr.Listner targets the second.

## Goal

Build a working prototype for one visit type (outpatient chest pain) that shows, with measured numbers, it finds missed questions, unanswered concerns, chart contradictions and unrepaired comprehension breakdowns, and gives the patient a summary they can follow. The design centers on older adults with hearing loss and low health literacy, with or without a caregiver in the room.

Draft targets, to be confirmed against the first eval run:

- Recall of at least 80% on planted gaps, reported per gap type (four types)

- Precision of at least 80%, and no more than 1 false flag per visit on average

- Patient summary at or below a 6th-grade reading level, checked automatically

- Every flag cites the transcript line or chart entry behind it

- No flag raised before the visit's wrap-up turn for missed questions or unanswered concerns

## Solution

Dr.Listner reads a visit transcript turn by turn against a published checklist and the patient's chart. During the visit it shows only passive coverage ticks and badges; at wrap-up it produces two outputs.

Four gap types

- Red-flag questions not asked (`missed_question`). Ten chest-pain checklist items with no matching question in the transcript: onset and duration, nature, exertional pattern, radiation, relieving factors, associated symptoms (sweating, shortness of breath, fainting), risk factors, family history and the rest of the verified list in `packs/chest_pain/checklist.json`.

- Patient concerns left unanswered (`unanswered_concern`). Worries the patient or caregiver voiced that a later clinician turn never addressed.

- Statements that contradict the chart (`chart_contradiction`). For example, the patient says no heart history while the chart lists a prior stent.

- Comprehension breakdowns not repaired (`comprehension_breakdown`, new). The patient shows they did not hear or understand (a repeat request, an answer that does not match the question, a bare "okay" after a multi-part instruction) and the clinician does not repeat, rephrase, confirm or use teach-back; also plan, medication or warning-sign instructions given with no teach-back. These cues are our own draft, not clinically validated.

Checklist source: the 2021 AHA/ACC Guideline for the Evaluation and Diagnosis of Chest Pain (Gulati et al., J Am Coll Cardiol, 2021). All 10 items were matched to the guideline text (Section 2.1 and Table 3) with a verbatim quote each. The matching was done by Claude and has not been reviewed by a clinician.

Two outputs

- Clinician wrap-up view. Unasked red flags, unanswered concerns and unrepaired comprehension, each with its evidence line and a one-tap dismiss, plus a clarify card of at most 3 items to say to the patient before they leave. Documentation completeness only; it never suggests a diagnosis.

- Patient summary. Plain-language plan, key warning signs and questions to ask next time, at a 6th-grade target and 180 words or fewer, with captions and read-aloud for patients with hearing loss.

Patient profiles

A `PatientProfile` sets hearing level, health literacy, whether a caregiver is present, which detectors are active, summary word and grade limits, and the number of teach-back questions. Two profiles ship: older adult with hearing loss and low literacy attending alone, and the same patient with a caregiver present. Caregiver turns are a third speaker type.

Surfacing rules

- During the visit: coverage ticks, plus at most passive badges for chart contradictions and comprehension breakdowns. No pop-ups.
- Missed questions and unanswered concerns are never raised before wrap-up.
- At wrap-up: unasked red flags, unanswered concerns, unrepaired comprehension, then the clarify card.
- Every flag is dismissible and dismissals are logged.

## How it works

Dr.Listner pipeline · turn-by-turn engine, 4 detectors, 1 verifier, 2 outputs

1. Input. A `TurnSource` feeds speaker-labeled turns (`clinician | patient | caregiver`, optional timestamps). Only replay of synthetic transcripts is implemented; typed and microphone input are being added for the role-play demo (see Live role-play demo).
2. De-identification. Each turn is scrubbed with Presidio and spaCy before any hosted call. Dates are kept because onset and follow-up timing are clinical, and cardiac drug names are protected from being tagged as people.
3. Per-turn detectors. On each patient or caregiver turn, the ChartAgent checks the last 5 turns against the chart. On each clinician turn, the ComprehensionAgent re-reads the window, because a repair can only be judged after the clinician replies.
4. Finalize detectors. After the last turn, the ChecklistAgent (coverage per item, with a turn and verbatim quote) and the ConcernAgent read the whole transcript once. Teach-back is also a whole-transcript check. A coverage claim whose quote does not check out counts as not covered.
5. Verifier. Programmatic check first (the pointed turn or chart entry exists, the quote is verbatim, the checklist id exists, the rationale contains no diagnosis or treatment wording), then one LLM yes/no check that the evidence supports the flag. Only `verified=True` flags are scored.
6. Summary. The SummaryAgent drafts up to 3 times, scores each draft with textstat, feeds the score back, and ships the best draft.
7. Failure handling. An LLM outage in a detector or verifier is recorded in the visit state, never raised. A failed checklist call means coverage is unknown, not "everything missed", and a failed verifier leaves the flag unverified, so an outage lowers recall instead of inflating precision.

Every flag links to the transcript line or chart entry that triggered it, and the patient summary reuses the flags as questions to ask next time.

## Tech stack

Python end to end, free or open-source pieces only, chosen so a two-person team can have a demo running in a day. Free-tier limits change, so check them before the build.

| Layer | Pick | Why |
|---|---|---|
| UI | Streamlit | A clinician view and a patient view in one Python file; no frontend build |
| Transcript input | Synthetic transcripts as JSON, speaker-labeled | Removes audio risk; the eval depends on controlled input |
| Speech to text (stretch) | faster-whisper, local | Free, runs offline, adds a live-audio demo if time allows |
| Extraction and gap reasoning | One LLM client with a response cache and provider order set by `LLM_PROVIDERS`: Groq `openai/gpt-oss-120b` (default, live-verified), then Gemini, then Ollama | Structured JSON output; fallback guards against rate limits. Groq free tier is 8,000 tokens per minute, so a full visit (20 to 30 calls) takes minutes live. Gemini and Ollama paths are tested only against mocked HTTP. Send synthetic text only |
| Schemas | Pydantic | Validates every model response before it reaches the UI |
| Checklist matching | LLM coverage check with verbatim-quote validation; sentence-transformers is optional and offline only | The hosted app has no embeddings at runtime (PyTorch would crowd the RAM limit) |
| De-identification | Microsoft Presidio with spaCy `en_core_web_sm` and a clinical keep-list | Open-source PII scrubbing before any text leaves the machine; best-effort, since the small model sometimes tags capitalized words as names |
| Synthetic charts | Synthea (FHIR output) and fhir.resources | Realistic fake patient histories, no real PHI |
| Reference dialogues | ACI-Bench, MTS-Dialog, PriMock57 | Public doctor-patient conversations for style; check each license |
| Patient readability | textstat | Automatic grade-level score on every summary |
| Read-aloud and captions | Browser SpeechSynthesis API through a small Streamlit HTML component; captions are on-screen text | No install, works in the demo browser |
| Evaluation | Own harness in `eval/` (standard library plus Pydantic), pandas for tables | Deterministic matcher, per-type precision, recall and F1 with Wilson 95% intervals, false flags per visit |
| Hosting and repo | Streamlit Community Cloud, GitHub | Free public demo link for judges |

## Evaluation plan

The proof is a number: how many planted gaps Dr.Listner finds, and how many false flags it raises per visit.

Dataset (built, `data/eval/`)

- 24 synthetic visits: 9 dev and 15 test, 7 clean in total, with caregiver visits and hard negatives (repaired repeat requests, addressed concerns). Dev and test use disjoint phrase pools.
- Test gap counts are small: 6 missed questions, 5 unanswered concerns, 5 chart contradictions, 6 comprehension breakdowns. We report counts with every percentage.
- Answer keys come from the deterministic edit that planted each gap (delete turns, insert concern, insert contradiction, insert mishearing, delete teach-back), never from a model's opinion. Each key records a `wrap_up_turn`.
- A separate 29-visit set in `data/synthetic/` is a contract fixture for tests only, not for tuning or reported metrics.

Harness (built, `eval/`)

- One-to-one matching: missed questions by checklist id, concerns and comprehension gaps by transcript turn, contradictions by chart entry or transcript turn. Unplanted but genuine gaps count as false positives, a known caveat.
- Reports precision, recall and F1 per type and overall with Wilson 95% intervals, false flags per visit, false flags on clean visits, flags raised too early, and turns-to-detection for chart contradictions and comprehension gaps.
- The committed `fake-*` runs (oracle and a run that drops two flags) only prove the harness works. They are not detector accuracy.

Still to run

- Tune on dev only, then run test once at the end of Phase 4 and once at final submission, and report as-is.
- Baseline: an LLM writes a scribe-style note, then one prompt lists what is missing, with no checklist, chart agent or verifier. Scored with the same matcher.
- Score every patient summary for reading grade level and plan-item coverage.
- No real accuracy numbers exist yet. Live smoke tests on two dev visits found both planted comprehension gaps in one and left 3 false flags on a clean visit; that is a smoke test, not a measurement.
- Limits to state on the results slide: charts are hand-authored rather than Synthea, phrasing variety is limited, the checklist has no clinician review, and because we author both sides of the planted mishearings, comprehension recall measures whether the detector finds our cues, not real hearing-loss speech. If a clinician reviews the checklist or a transcript sample, say so and note what they changed.

## Streamlit UI design

Status: designed, not yet built. There is no `app.py` yet; everything below is the plan, shaped by the engine's existing contracts (`VisitState`, `Flag`, `PatientProfile`, `TurnSource`). One Streamlit app, a sidebar and four tabs, driven by synthetic visits replayed turn by turn.

### Design principles

- Quiet by default: no pop-ups or modals during the visit; gaps surface at wrap-up.
- Evidence first: no flag appears without the transcript line or chart entry that triggered it.
- Accessible by design, since the users are people with hearing loss and low literacy: large type, high contrast, captions always on, no information carried by color alone.
- Honest labeling: a permanent banner reads "Synthetic data only. Documentation check, not a diagnosis. Not a medical device."
- Demo-safe: Demo mode is the default, so the app works with no key and no network.

### Sidebar (controls)

- Mode switch: Demo (cached, no network) or Live (provider chain; shows a warning about the Groq 8,000 tokens per minute limit and per-visit wait).
- Visit picker: the 24 eval visits plus a label for each (clean, which gap types, caregiver or alone). Test-split visits are hidden behind an "evaluation visits" toggle so the demo does not tune on them.
- Patient profile: the two shipped profiles (alone, with caregiver), showing hearing level, literacy and active detectors read-only.
- Replay controls: play, pause, step one turn, speed, jump to wrap-up.
- Status strip: provider and model in use, cache hits, and any `VisitState.errors` (for example "checklist call failed; coverage unknown").

### Tab 1: Live visit (clinician-facing)

Three columns while the replay runs.

1. Transcript (left): speaker-labeled chat bubbles for clinician, patient and caregiver, with turn numbers. The current turn is highlighted. Text is the de-identified version, with scrubbed spans shown as tags such as [PERSON]. Turns cited by a flag get a small marker, and clicking a marker scrolls to the flag.
2. Coverage panel (center): the 10 checklist items as a ticklist. Per spec, `checklist_coverage` is filled only at finalize, so during replay items stay neutral ("pending"), then flip to covered (with the turn number and quote) or not covered at wrap-up. Per-turn ticks are a stretch goal and need engine work. Items are labeled with the guideline reference and a "verified against guideline text, not clinician-reviewed" note.
3. Chart (right): the synthetic chart entries (conditions, medications, procedures, with status and date). A chart entry is outlined when a contradiction cites it.

Passive badges: chart contradictions and comprehension breakdowns may show as a small neutral badge near the transcript line (not a pop-up), with the turns-to-detection visible on hover. Missed questions and unanswered concerns never appear before wrap-up.

### Tab 2: Wrap-up (clinician gaps list)

Appears when the replay reaches the wrap-up turn (or on "Jump to wrap-up").

- Gaps list grouped by type, in the surfacing order: unasked red flags, unanswered concerns, unrepaired comprehension, chart contradictions.
- Each flag card shows: type label, one-line rationale (lint-checked, never diagnostic wording), evidence (quoted transcript line with turn number, chart entry with display text, or checklist item with guideline quote), verified status, and a Dismiss button with an optional reason. Dismissed flags collapse but stay visible under "Dismissed" and are logged.
- Clarify card: at most 3 items worth saying to the patient before they leave, such as repeat the warning signs with teach-back, ask the unasked red-flag question, answer the open worry.
- Counters: flags shown, dismissed, and flags raised too early (should be 0).
- Empty state for clean visits: "No gaps found. This does not mean the visit was complete."

### Tab 3: Patient view

Written for the patient, in large type, with high contrast.

- Plain-language summary from the SummaryAgent: what we talked about, your plan, warning signs to watch for, and questions to ask next time (derived from the verified flags).
- Accessibility controls: text size slider, high-contrast toggle, read-aloud button (browser speech synthesis) with a stop button, and captions for the read-aloud text.
- Readability badge: grade level from textstat against the 6th-grade target, word count against the 180 limit, and the grade for each of the up to 3 drafts.
- Teach-back card: the profile's two teach-back questions ("In your own words, what will you do if the pain comes back?").
- Printable view for the patient or caregiver to take home.

### Tab 4: Evaluation (judge-facing)

- Results tables from `eval/results/*.json`: per-type TP/FP/FN, precision, recall, F1 with Wilson intervals, false flags per visit, clean-visit false flags, too-early flags, and turns-to-detection. The UI formats saved values only and never computes a score.
- System selector: Dr.Listner versus the scribe-style baseline once both are run.
- Error explorer: the FP and FN exports with each missed gap and false flag next to its transcript lines.
- Fake runs are labeled "HARNESS CHECK, NOT ACCURACY" until real runs replace them.
- Limits panel: synthetic data, hand-authored charts, no clinician review, small per-type counts, comprehension cues are our own draft.

### State and data flow

- `st.session_state` holds the `VisitState`, the replay position and the dismissals. Each replay step calls `process_turn`; the wrap-up step calls `finalize` and the SummaryAgent.
- In Demo mode every LLM call is served from `data/llm_cache/`; a miss shows a clear message instead of crashing.
- No transcript is stored by the app beyond the session, and no uploads are accepted. Keys come from Streamlit secrets.

### Build order and cuts

1. Visit picker, transcript replay and chart panel (Demo mode only).
2. Wrap-up tab with flag cards, evidence and dismiss.
3. Patient tab with summary, grade badge and read-aloud.
4. Evaluation tab from saved results.
5. If time allows: Live mode toggle, per-turn coverage ticks, microphone or typed input (speech-to-text stays a stretch goal).
6. First cuts if time runs short: printable view, error explorer, Live mode.

## Live role-play demo (final demo plan)

Two people, one playing the clinician and one the patient, talk through a prepared script while Dr.Listner listens and reacts as if live. The demo is partly hardcoded on purpose, and the report says so: the point is to show the full end-to-end experience reliably, and the measured numbers come from the eval harness, not from this demo.

### What the audience sees

- Speech from the room appears turn by turn in the transcript as it is spoken, labeled clinician or patient.
- Passive badges appear in real time when a chart contradiction or an unrepaired comprehension breakdown happens (for example, the patient says "no heart problems" and the chart shows a prior stent).
- The checklist panel ticks off red-flag questions as the clinician asks them.
- When the clinician says a closing phrase, or presses "End visit", the wrap-up tab fills in: questions never asked, the unanswered concern, the unrepaired comprehension, and a clarify card of at most 3 items. Then the patient view shows the plain-language summary, read aloud.

### How it works

- **Input:** the browser's speech recognition (Web Speech API, Chrome) turns speech into text. A "Clinician / Patient" speaker toggle, or one phone per speaker, labels each turn. A typed-turn box is the fallback if the microphone or room noise fails. Audio never leaves the browser except to the browser's own speech service, so say that on the slide.
- **Engine:** each finished utterance becomes a `Turn` and goes through `process_turn`, as designed. No engine change is needed for input; it replaces the `ReplaySource`.
- **Prepared script:** a scripted visit (one chart, one profile) with planted gaps: a skipped red-flag question, a voiced worry that goes unanswered, one chart contradiction, one mishearing with no repair, and no teach-back. The script lives in `demo/` with the matching synthetic chart.
- **Hardcoded parts:** model outputs for the script are rehearsed once in Live mode and stored in the LLM cache, so the demo runs instantly with no rate-limit wait. Spoken lines are matched to script lines by text similarity; a line that matches is served from the cache. A line that does not match goes to the live model if it is available, and otherwise is shown in the transcript without a flag.
- **Live ticks:** the checklist panel ticks per turn in the demo, using the scripted coverage for matched lines. This is a demo-only shortcut until per-turn coverage exists in the engine.

### Folder layout

- `demo/script.json`: the line-by-line script with speaker, text and the expected flag for each planted gap.
- `demo/chart.json`: the synthetic chart for the demo patient.
- `demo/cache/`: the rehearsed LLM outputs for this script.
- `demo/rehearse.py`: runs the script through the engine in Live mode once to fill the cache and checks that the expected flags appear.
- `demo/README.md`: stage notes, with the browser to use, microphone setup, and what to do if something fails.

### Rules and risks, stated honestly

- Best case is the partners say the scripted lines almost verbatim. Large deviations will not match, and the system falls back to live model calls (slow and rate-limited) or no flag.
- Mid-visit alerts stay passive. Missed questions and unanswered concerns appear at wrap-up only, which is the design choice already in this report.
- Fallbacks: a typed-turn box, a screen recording of a clean run, and a laptop with Ollama.
- The demo cannot claim accuracy. Say it is a scripted walkthrough, and show the eval tab for the measured numbers.
- Everything stays synthetic: a made-up patient, a made-up chart, and no real health information spoken.

## Build status (Oct 19, 2026)

| Piece | Status |
|---|---|
| Spec, schemas, 10-item guideline-matched checklist | Done; no clinician review |
| LLM client (cache, Groq, Gemini, Ollama, Demo/Live) | Done; only Groq verified live |
| Synthetic eval set, 9 dev + 15 test, 4 gap types | Done; user spot-read gate pending |
| De-identification, 4 detectors, verifier, engine, SummaryAgent | Implemented, 62 tests at last count; detector quality not measured |
| Evaluation harness and fake-run artifacts | Done; fake runs are not accuracy |
| Real dev run, tuning, test run, baseline | Not done |
| Streamlit app | Not started |
| Live role-play demo (`demo/` folder, speech input, rehearsed cache) | Planned |
| Hosted deploy and RAM check | Not started |

Deadline: Oct 21, 2026.

## Privacy and safety

The prototype never touches real patient data, and we do not claim HIPAA compliance.

- Synthetic and public data only; no transcript storage.

- De-identification runs before any text is sent to a hosted model. The committed LLM cache holds model outputs on synthetic text only.

- The tool checks documentation completeness. It does not diagnose or recommend treatment, and a clinician decides what to do with every flag.

- Production path, stated as a roadmap item: a HIPAA-eligible deployment with a signed business associate agreement, audit logging and patient consent for recording.

- Known limits, said up front: single visit type, synthetic data, no clinician validation unless we secure it.

## Deployment and cost

Target spend is $0: the app runs on Streamlit Community Cloud from a GitHub repo, model calls use a free LLM tier (Groq by default, Gemini as fallback), and every other component is open source and runs inside the app.

| Piece | Where it runs | Cost | Watch-out |
|---|---|---|---|
| Web app (clinician and patient views) | Streamlit Community Cloud, deployed from GitHub | Free (Streamlit docs) | RAM is 690 MB minimum and 2.7 GB maximum per the docs (February 2024 figures, subject to change); apps with no traffic for 12 hours go to sleep and wake with one click (Streamlit docs) |
| LLM extraction and gap reasoning | Groq free tier (default), Gemini API free tier (fallback) | $0 on free tiers (Google AI pricing page for Gemini) | Groq allows 8,000 tokens per minute, so Live mode is slow; Gemini free-tier content is used to improve Google products, so send only synthetic, de-identified text |
| De-identification, readability, eval | Presidio, spaCy, textstat, pandas, inside the app process | $0, open source | The Presidio plus spaCy footprint against the 690 MB RAM minimum is unchecked; no PyTorch in the hosted app |
| Synthetic charts, transcripts, answer key | Generated offline on a laptop, committed to the repo as JSON | $0 | No real data, keep files small |
| Backup demo | Laptop with Ollama and the same code, plus a screen recording | $0 | Covers wifi, rate-limit and sleeping-app failures on demo day |

Hugging Face Spaces is not the plan: its docs say Gradio and Docker Spaces need a paid plan to create, with only static Spaces free (Hugging Face docs).

- Keep one repo: app.py (not yet written), requirements.txt, and a data/ folder holding the synthetic transcripts, charts, answer keys and the LLM cache.

- Demo mode replays cached LLM outputs with no network (a cache miss raises an error); Live mode calls the provider chain. The demo path is the default because of the Groq rate limit.

- Store API keys in the platform's secrets settings, never in the repo.

- Connect the GitHub repo in Streamlit Community Cloud and deploy; changes pushed to GitHub generally show up in the app right away (Streamlit docs).

- Within 12 hours before presenting, open the live link (a sleeping app needs a one-click wake), run one visit end to end, and keep the recording ready.

Expected spend is $0 if the free tiers hold; the unconfirmed limits above are the only way that changes.

## Sources

Opened and checked against the page: NIDCD, NCES, Kessels, National Academies brief, Google AI pricing, Streamlit docs, Hugging Face docs. Taken from search excerpts only, so open before submitting: BMJ abstract, JAGS review, the PMC hearing study, the JMIR audit. The chest-pain item list was matched to the guideline text by Claude, with no clinician review. Targets in the Goal section are our own drafts.

- Frequency of diagnostic errors in outpatient care, BMJ Quality & Safety (2014)

- Improving Diagnosis in Health Care, Institute of Medicine (2015)

- Quick Statistics About Hearing, NIDCD, NIH

- Hearing loss in physician-patient communication research, JAGS systematic review

- Hearing loss and ratings of patient-physician communication, PMC

- The Health Literacy of America's Adults, NCES 2006-483, U.S. Department of Education

- Patients' memory for medical information, Kessels, J R Soc Med (2003)

- AI scribe quality audit, JMIR Medical Informatics (2026)

- 2021 AHA/ACC Guideline for the Evaluation and Diagnosis of Chest Pain, J Am Coll Cardiol

- Gemini API pricing, Google AI for Developers

- Streamlit Community Cloud docs

- Manage your app, Streamlit Community Cloud resource limits and sleep

- Spaces overview, Hugging Face docs


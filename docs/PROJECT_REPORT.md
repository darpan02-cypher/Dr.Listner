# Dr.Listner: catching what the visit missed

Oct 15, 2026 · @himanshi

AI scribes record what was said; Dr.Listner flags what was never asked or answered, and hands the patient a plain-language plan they can actually follow. IEEE Hack for Humanity, Track 2: AI for Accessibility and Disability Inclusion.

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
| Core job | Draft the visit note from what was said | Flag what was not said or not resolved |
| Known failure | Omissions and made-up content in the note; omissions were the top error in a 356-note audit (64 notes, 18%) (JMIR Med Inform, 2026) | Misses are surfaced with the transcript line that triggered them, so the clinician can verify in seconds |
| Clinician experience | Note to review and edit | One quiet end-of-visit gaps list; no live pop-ups, to avoid alert fatigue |
| Patient experience | Notes written for clinicians | Plain-language care summary, captions, read-aloud, questions to ask next time |
| Who it helps most | Clinician workload | Patients with hearing loss, low health literacy or cognitive impairment |

Caveat: this compares the category as described in published audits; we have not audited individual vendors. Scribe omissions (things said but dropped from the note) are a different problem from visit omissions (things that should have been asked); Dr.Listner targets the second.

## Goal

Build a working prototype for one visit type (outpatient chest pain) that shows, with measured numbers, it finds missed questions, unanswered concerns and chart contradictions, and gives the patient a summary they can follow.

Draft targets, to be confirmed against the first eval run:

- Recall of at least 80% on planted gaps across all three gap types

- Precision of at least 80%, and no more than 1 false flag per visit on average

- Patient summary at or below a 6th-grade reading level, checked automatically

- Every flag cites the transcript line or chart entry behind it

## Solution

Dr.Listner reads a visit transcript against a published checklist and the patient's chart, then produces two outputs after the visit ends.

Three gap types

- Red-flag questions not asked. Chest-pain checklist items (onset, exertional pattern, radiation, sweating, shortness of breath, fainting, family history, risk factors) with no matching question in the transcript.

- Patient concerns left unanswered. Worries the patient voiced that the clinician never addressed.

- Statements that contradict the chart. For example, the patient says no heart history while the chart lists a prior stent.

Checklist source: the 2021 AHA/ACC Guideline for the Evaluation and Diagnosis of Chest Pain (Gulati et al., J Am Coll Cardiol, 2021). The red-flag items above are our working draft; each must be confirmed against the guideline's history section (Section 2.1, Table 3) before the eval.

Two outputs

- Clinician gaps list. Quiet, end-of-visit, each item with its evidence line and a one-tap dismiss. Documentation completeness only; it never suggests a diagnosis.

- Patient summary. Plain-language plan, key warning signs, and questions to ask next time, with captions and read-aloud for patients with hearing loss.

## How it works

Dr.Listner pipeline · 2 inputs, 3 gap checks, 2 outputs

Gap checks run on de-identified text only. Every flag links to the transcript line or chart entry that triggered it, and the patient summary reuses the flags as questions to ask next time.

## Tech stack

Python end to end, free or open-source pieces only, chosen so a two-person team can have a demo running in a day. Free-tier limits change, so check them before the build.

| Layer | Pick | Why |
|---|---|---|
| UI | Streamlit | A clinician view and a patient view in one Python file; no frontend build |
| Transcript input | Synthetic transcripts as JSON, speaker-labeled | Removes audio risk; the eval depends on controlled input |
| Speech to text (stretch) | faster-whisper, local | Free, runs offline, adds a live-audio demo if time allows |
| Extraction and gap reasoning | Google Gemini API free tier with JSON output, Ollama (Llama or Qwen) as offline fallback | Structured output keeps results parseable; fallback guards against rate limits; free-tier content may be used to improve Google products, so send synthetic text only |
| Schemas | Pydantic | Validates every model response before it reaches the UI |
| Checklist matching | sentence-transformers (all-MiniLM-L6-v2) plus an LLM check for borderline cases | Cheap first pass, so the LLM runs only where it is unsure; heavy PyTorch install, so keep it out of the hosted app and ship precomputed embeddings |
| De-identification | Microsoft Presidio | Open-source PII scrubbing before any text leaves the machine |
| Synthetic charts | Synthea (FHIR output) and fhir.resources | Realistic fake patient histories, no real PHI |
| Reference dialogues | ACI-Bench, MTS-Dialog, PriMock57 | Public doctor-patient conversations for style; check each license |
| Patient readability | textstat | Automatic grade-level score on every summary |
| Read-aloud and captions | Browser SpeechSynthesis API, Web Speech API | No install, works in the demo browser |
| Evaluation | pandas, scikit-learn | Precision, recall and F1 per gap type in a few lines |
| Hosting and repo | Streamlit Community Cloud, GitHub | Free public demo link for judges |

## Evaluation plan

The proof is a number: how many planted gaps Dr.Listner finds, and how many false flags it raises per visit.

- Write 20 to 30 synthetic chest-pain transcripts, each paired with a synthetic chart.

- Plant known gaps in each (missed red-flag question, ignored concern, chart contradiction) and record them in a separate answer key.

- Run Dr.Listner and compare against the key. Report precision, recall and F1 per gap type, plus false flags per visit.

- Compare against a baseline of a plain scribe-style summary with no gap check.

- Score every patient summary for reading grade level and check that it covers the care plan items in the key.

- If we can get a clinician to review the checklist and a sample of transcripts, say so on the results slide and note what they changed.

## Privacy and safety

The prototype never touches real patient data, and we do not claim HIPAA compliance.

- Synthetic and public data only; no transcript storage.

- De-identification runs before any text is sent to a hosted model.

- The tool checks documentation completeness. It does not diagnose or recommend treatment, and a clinician decides what to do with every flag.

- Production path, stated as a roadmap item: a HIPAA-eligible deployment with a signed business associate agreement, audit logging and patient consent for recording.

- Known limits, said up front: single visit type, synthetic data, no clinician validation unless we secure it.

## Deployment and cost

Target spend is $0: the app runs on Streamlit Community Cloud from a GitHub repo, model calls use Gemini's free tier, and every other component is open source and runs inside the app.

| Piece | Where it runs | Cost | Watch-out |
|---|---|---|---|
| Web app (clinician and patient views) | Streamlit Community Cloud, deployed from GitHub | Free (Streamlit docs) | RAM is 690 MB minimum and 2.7 GB maximum per the docs (February 2024 figures, subject to change); apps with no traffic for 12 hours go to sleep and wake with one click (Streamlit docs) |
| LLM extraction and gap reasoning | Gemini API free tier | $0 on the listed Flash and Flash-Lite models (Google AI pricing) | Free-tier content is used to improve Google products, so send only synthetic, de-identified text; the page lists no numeric rate limits, so check AI Studio for yours |
| De-identification, matching, readability, eval | Presidio, sentence-transformers, textstat, scikit-learn, inside the app process | $0, open source | sentence-transformers pulls in PyTorch, which would crowd the 690 MB RAM minimum; run it offline, ship precomputed embeddings, and let the LLM do matching in Live mode |
| Synthetic charts, transcripts, answer key | Generated offline on a laptop, committed to the repo as JSON | $0 | No real data, keep files small |
| Backup demo | Laptop with Ollama and the same code, plus a screen recording | $0 | Covers wifi, rate-limit and sleeping-app failures on demo day |

Hugging Face Spaces is not the plan: its docs say Gradio and Docker Spaces need a paid plan to create, with only static Spaces free (Hugging Face docs).

- Keep one repo: app.py, requirements.txt, and a data/ folder holding the synthetic transcripts, charts, answer key and cached results.

- Add a Demo mode that reads cached results with no API calls, and a Live mode that calls Gemini.

- Store the Gemini key in the platform's secrets settings, never in the repo.

- Connect the GitHub repo in Streamlit Community Cloud and deploy; changes pushed to GitHub generally show up in the app right away (Streamlit docs).

- Within 12 hours before presenting, open the live link (a sleeping app needs a one-click wake), run one visit end to end, and keep the recording ready.

Expected spend is $0 if the free tiers hold; the unconfirmed limits above are the only way that changes.

## Sources

Opened and checked against the page: NIDCD, NCES, Kessels, National Academies brief, Google AI pricing, Streamlit docs, Hugging Face docs. Taken from search excerpts only, so open before submitting: BMJ abstract, JAGS review, the PMC hearing study, the JMIR audit. The chest-pain item list is not yet checked against the guideline. Targets in the Goal section are our own drafts.

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


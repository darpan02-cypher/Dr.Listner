# Dr. Listener - A Second Ear For Care

**AI scribes capture what was said. Dr. Listener catches what was missed.**

Dr. Listener is an accessibility-first, multi-agent AI prototype that identifies communication gaps in doctor–patient consultations, particularly for older adults with hearing loss and limited health literacy.

Built for **IEEE Hack for Humanity — AI for Accessibility and Disability Inclusion**.

## The Problem

Every year, approximately **12 million Americans experience outpatient diagnostic errors**. Meanwhile, patients can forget 40–80% of medical information soon after receiving it.

Traditional AI medical scribes document conversations. But documentation alone cannot reveal everything that was **never asked, never answered, or never understood**.

## Our Solution

Dr. Listener analyzes consultations for four critical gaps:

| Gap | What Dr. Listener checks |
|---|---|
| **Missed Questions** | Uncovered questions from a 10-item AHA/ACC guideline-referenced chest-pain checklist |
| **Unanswered Concerns** | Patient worries that were never addressed |
| **Chart Contradictions** | Conflicts between patient statements and medical records |
| **Comprehension Breakdowns** | Potential misunderstandings that were not clarified |

### Designed for Accessible Healthcare

- **Live transcription:** Speaker-labeled doctor–patient conversations.
- **Evidence-backed analysis:** AI-generated flags checked against transcript or chart evidence.
- **Minimal alert fatigue:** Quiet indicators during consultations and consolidated wrap-up checks.
- **Patient-friendly summaries:** Plain-language explanations with readability assessment.
- **Accessible interface:** Adjustable text, high-contrast options, and read-aloud support.

## How It Works

```text
Doctor + Patient Conversation
            |
            v
Deepgram Speech-to-Text + Diarization
            |
            v
Python Visit Orchestrator
            |
            v
Specialized AI Agents
 |-- Checklist Agent
 |-- Concern Agent
 |-- Chart Agent
 |-- Comprehension Agent
            |
            v
Evidence Verification
            |
            v
Clinician Review + Patient Summary
```

Our deterministic Python orchestrator manages specialized agents instead of relying on one large AI prompt, making the processing pipeline easier to test and audit.

## Tech Stack

| Layer | Technologies |
|---|---|
| Interface | Streamlit |
| Backend | Python, Pydantic |
| Speech recognition | Deepgram |
| AI inference | Groq, with Gemini and Ollama fallback configurations |
| Multi-agent processing | Custom Python orchestration and specialized LLM agents |
| De-identification | Microsoft Presidio, spaCy |
| Readability | textstat |
| Synthetic evaluation | Python, pytest, synthetic clinical datasets |

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/darpan02-cypher/Dr.Listner.git
cd Dr.Listner
```

### 2. Set up the environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Launch the application

```bash
./run.sh
```

This opens the landing page at `http://localhost:8800`. Launch the console from there.

To jump straight to the Streamlit console, run:

```bash
streamlit run app2.py
```

### 4. Explore the demo

Use the scripted demo backend to explore synthetic doctor–patient consultations without an LLM API key.

For live AI processing, configure the relevant provider credentials. For Deepgram microphone streaming, configure `DEEPGRAM_API_KEY`.

The live microphone WebSocket relay currently targets localhost and requires additional configuration for remote deployment.

## Testing and Evaluation

Install development dependencies and run the test suite:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m scripts.build_dataset
python -m scripts.build_eval_dataset
```

The repository includes 29 synthetic development fixtures and a separate evaluation dataset containing 9 development and 15 test consultations.

Our evaluation goals are:

- **≥80% precision and recall** for gap detection.
- **≤1 false positive per consultation.**
- **Evidence-backed findings** with traceable transcript or chart references.

These are **targets, not validated performance results**.

## What's Next?

- Improve real-time speaker diarization and role identification.
- Validate gap detection through independent evaluation and clinical review.
- Expand to additional consultation types and languages.
- Strengthen accessible patient summaries and trusted-source retrieval.
- Explore secure clinical integration with FHIR and appropriate consent controls.

## Safety and Limitations

**Dr. Listener is a research and hackathon prototype, not a medical device.**

The project uses synthetic clinical scenarios only. It does not provide diagnoses or treatment recommendations, is not validated for clinical use, and makes no HIPAA-compliance claim.

The guideline-referenced checklist has not been clinician-reviewed, and speech recognition and gap-detection errors remain possible.

## Documentation

- [Project Specification](SPEC.md)
- [Implementation Progress](PROGRESS.md)
- [Project Report](docs/PROJECT_REPORT.md)
- [Synthetic Dataset](data/synthetic/README.md)

---

**Dr. Listener — Because every patient deserves to be heard, understood, and informed.**

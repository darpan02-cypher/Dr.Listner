"""De-identification (Presidio). Runs before any hosted LLM call. See SPEC.md section 5.

Only identifier-like entities are scrubbed. DATE_TIME is deliberately NOT scrubbed:
"yesterday afternoon" / "one week" are clinical content (onset, follow-up), and the
data is synthetic. NER is statistical, so this reduces but does not guarantee removal.
"""
from __future__ import annotations

from functools import lru_cache

from .schemas import Transcript, Turn

ENTITIES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "LOCATION", "URL", "IP_ADDRESS", "CREDIT_CARD"]
SPACY_MODEL = "en_core_web_sm"  # small enough for the hosted app; large model is not needed here
MIN_SCORE = 0.4  # Presidio scores bare phone numbers 0.4; favour privacy over keeping clinical text


# The small NER model tags drug names as PERSON ("I take Lisinopril" -> "I take <PERSON>"), which would
# destroy the evidence chart_contradiction needs. PERSON spans that are one of these terms are kept.
KEEP_TERMS = frozenset(
    "aspirin clopidogrel plavix atorvastatin lipitor rosuvastatin simvastatin statin lisinopril losartan metoprolol "
    "carvedilol amlodipine apixaban eliquis warfarin coumadin rivaroxaban xarelto metformin insulin nitroglycerin "
    "ibuprofen naproxen acetaminophen tylenol furosemide lasix ticagrelor ranolazine".split()
)


def keep_terms_from_chart(chart) -> frozenset[str]:
    """Words of the chart's own entries (drugs, conditions) are clinical content, not identifiers."""
    words = {w.strip(".,;:()").lower() for e in chart.entries for w in e.display.split()}
    return frozenset(w for w in words if w)


@lru_cache(maxsize=1)
def _engines():
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine

    nlp = NlpEngineProvider(
        nlp_configuration={"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": SPACY_MODEL}]}
    ).create_engine()
    return AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"]), AnonymizerEngine()


def scrub(text: str, keep: frozenset[str] = frozenset()) -> str:
    """Replace identifiers with <ENTITY> placeholders. Deterministic for a given input."""
    analyzer, anonymizer = _engines()
    keep = KEEP_TERMS | keep
    found = [
        r
        for r in analyzer.analyze(text=text, language="en", entities=ENTITIES)
        if r.score >= MIN_SCORE and not (r.entity_type == "PERSON" and text[r.start : r.end].strip().lower() in keep)
    ]
    if not found:
        return text
    return anonymizer.anonymize(text=text, analyzer_results=found).text


def scrub_turn(turn: Turn, keep: frozenset[str] = frozenset()) -> Turn:
    return turn.model_copy(update={"text": scrub(turn.text, keep) or turn.text})


def scrub_transcript(t: Transcript, keep: frozenset[str] = frozenset()) -> Transcript:
    return t.model_copy(update={"turns": [scrub_turn(x, keep) for x in t.turns]})

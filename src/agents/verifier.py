"""VerifierAgent: (a) programmatic evidence checks, (b) LLM check that the evidence supports the flag."""
from __future__ import annotations

from pydantic import BaseModel

from ..schemas import Chart, Checklist, Flag, GapType, Transcript
from .common import SAFETY_RULES, LLM, fmt_chart, fmt_turns, has_clinical_advice, quote_in, turn_by_idx

SYSTEM = "You are a strict reviewer of documentation-gap flags. " + SAFETY_RULES

PROMPT = """Transcript:
{transcript}

Chart:
{chart}

Proposed flag: type={ftype}
Claim: {claim}
Evidence:
{evidence}

Is this flag correct? Rules by type:
- missed_question: the named checklist topic is truly NOT covered anywhere in the transcript (asked or volunteered).
- unanswered_concern: the quoted turn is a worry, fear, question or request the patient raised on their own (a plain
  answer to a clinician question, including reporting a symptom, is NOT a concern) AND no later clinician turn responds to it.
- chart_contradiction: the patient's quoted words really conflict with the chart entry.
- comprehension_breakdown: the quoted turn shows non-understanding (repeat request, reply about a different topic than
  the question) that is not repaired, or instructions lack teach-back. A brief answer that fits the question is not a breakdown.
Answer supported=true only if the transcript/chart text proves it. Give a one-sentence reason."""


class Verdict(BaseModel):
    supported: bool
    reason: str


def programmatic_ok(flag: Flag, transcript: Transcript, chart: Chart | None, checklist: Checklist | None) -> bool:
    """SPEC section 5 (a): pointed turn/entry exists and quote is a (whitespace-normalized) substring."""
    if has_clinical_advice(flag.rationale):
        return False
    for e in flag.evidence:
        if e.source == "transcript":
            t = turn_by_idx(transcript.turns, int(e.ref))
            if t is None or not e.quote or not quote_in(e.quote, t.text):
                return False
        elif e.source == "chart":
            entry = chart.entry(e.ref) if chart else None
            if entry is None or not e.quote or not quote_in(e.quote, entry.display):
                return False
        elif e.source == "checklist":
            if checklist is None or e.ref not in {i.id for i in checklist.items}:
                return False
    return True


class VerifierAgent:
    def __init__(self, llm: LLM):
        self.llm = llm

    def verify(
        self, flag: Flag, transcript: Transcript, chart: Chart | None = None, checklist: Checklist | None = None
    ) -> Flag | None:
        if not programmatic_ok(flag, transcript, chart, checklist):
            return None
        ev = []
        for e in flag.evidence:
            label = next((i.label for i in checklist.items if i.id == e.ref), "") if e.source == "checklist" and checklist else ""
            ev.append(f"- {e.source} {e.ref}" + (f" ({label})" if label else "") + (f': "{e.quote}"' if e.quote else ""))
        verdict = self.llm.generate(
            PROMPT.format(
                transcript=fmt_turns(transcript.turns),
                chart=fmt_chart(chart) if chart else "(none)",
                ftype=flag.type.value,
                claim=flag.rationale,
                evidence="\n".join(ev),
            ),
            Verdict,
            SYSTEM,
        )
        return flag.model_copy(update={"verified": True}) if verdict.supported else None

    def verify_all(self, flags, transcript, chart=None, checklist=None) -> list[Flag]:
        return [v for f in flags if (v := self.verify(f, transcript, chart, checklist)) is not None]

"""ConcernAgent: patient worries the clinician never addressed -> unanswered_concern flags."""
from __future__ import annotations

from pydantic import BaseModel

from ..schemas import EvidencePointer, Flag, GapType, Transcript
from .common import SAFETY_RULES, LLM, flag_id, fmt_turns, quote_in, turn_by_idx

SYSTEM = "You find patient concerns in a doctor-patient visit transcript. " + SAFETY_RULES

PROMPT = """Transcript:
{transcript}

List every concern the patient or caregiver raises ON THEIR OWN INITIATIVE: a worry, fear, a question they ask the
clinician, or a request (for example about work, driving, a family member, cost, what a symptom means).
A direct answer to a clinician's question is NOT a concern, even when it reports a symptom ("Yes, I feel winded",
"It goes down my arm"), lists medicines, or says how well they hear. Also NOT a concern: a preference about how the
clinician speaks ("face me", "slower", "louder") or a request to repeat ("sorry, what did you say?"); those are
hearing needs, not worries. Ignore small talk. When unsure, leave it out.
For each, give the turn index of the patient/caregiver turn voicing it and a verbatim quote from that turn.
Then say whether a LATER clinician turn actually responds to that specific concern (addressed=true, with the
responding turn index) or not (addressed=false, addressed_by=null). A generic "any other questions?" with no
reply to the concern does not count as addressing it. Repeating the concern back or answering it does."""


class Concern(BaseModel):
    turn_idx: int
    quote: str
    addressed: bool
    addressed_by: int | None = None


class ConcernOut(BaseModel):
    concerns: list[Concern]


class ConcernAgent:
    def __init__(self, llm: LLM):
        self.llm = llm

    def run(self, transcript: Transcript) -> tuple[list[Flag], list[Concern]]:
        out = self.llm.generate(PROMPT.format(transcript=fmt_turns(transcript.turns)), ConcernOut, SYSTEM)
        last = transcript.turns[-1].idx
        flags: list[Flag] = []
        valid: list[Concern] = []
        for c in out.concerns:
            t = turn_by_idx(transcript.turns, c.turn_idx)
            if t is None or t.speaker == "clinician" or not quote_in(c.quote, t.text):
                continue  # bad citation or wrong speaker: drop, never guess
            valid.append(c)
            by = turn_by_idx(transcript.turns, c.addressed_by) if c.addressed_by is not None else None
            if c.addressed and by is not None and by.speaker == "clinician" and by.idx > c.turn_idx:
                continue
            flags.append(
                Flag(
                    flag_id=flag_id(transcript.visit_id, "c", c.turn_idx),
                    visit_id=transcript.visit_id,
                    type=GapType.UNANSWERED_CONCERN,
                    evidence=[EvidencePointer(source="transcript", ref=str(c.turn_idx), quote=c.quote)],
                    rationale="The patient raised this and no later clinician turn appears to respond to it.",
                    raised_at_turn=last,
                )
            )
        return flags, valid

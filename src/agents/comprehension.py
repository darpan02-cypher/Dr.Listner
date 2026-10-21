"""ComprehensionAgent (gap type 4). Cues are our own DRAFT, not clinically validated (SPEC section 8).

Two checks:
  repair  - a patient turn shows they did not hear/understand and the clinician does not repair it.
  teachback - the clinician gives plan/medication/warning-sign instructions with no teach-back.
"""
from __future__ import annotations

from typing import Literal

import re

from pydantic import BaseModel

from ..schemas import EvidencePointer, Flag, GapType, Turn
from .common import SAFETY_RULES, LLM, flag_id, fmt_turns, quote_in, turn_by_idx

SYSTEM = "You look for communication breakdowns in a doctor-patient visit. " + SAFETY_RULES

REPAIR_PROMPT = """Transcript excerpt:
{transcript}

Find PATIENT/CAREGIVER turns (only turns that have a later clinician turn in the excerpt) that show they did not
hear or understand the clinician, and where the clinician does NOT repair it afterwards. Cues:
- a repeat request ("what?", "sorry?", "could you say that again") that is not followed by a repeat or rephrase;
- an answer that is about something different from the question just asked (off-topic reply). A short or plain
  yes/no/symptom answer that fits the question is NOT a breakdown, and neither is a patient saying how well they hear
  or asking the clinician to speak more clearly (that is a preference, not a misunderstanding);
- a bare "okay"/"yes" right after a multi-part instruction (low confidence).
When unsure, leave it out.
Do NOT report a breakdown if a later clinician turn repeats, rephrases or confirms and the patient then answers
sensibly. For each: first write the clinician's preceding question, then decide whether the patient's reply gives the
information asked for (reply_answers_question). Give the patient turn index and a verbatim quote from it."""

TEACHBACK_PROMPT = """Transcript:
{transcript}

Does the clinician give the patient plan, medication or warning-sign instructions? If yes, does the clinician
ask the patient to say it back or confirm understanding in their own words (teach-back), and does the patient do so?
Set gives_instructions=true only if instructions were actually given. Set teach_back_done=true only if a
clinician turn asks for a restatement/confirmation and the patient restates it. A plain "any questions?" or a
bare "okay" from the patient is NOT teach-back.
If instructions were given without teach-back, give instruction_turn (the clinician turn that delivers the
plan; if several, the one with the most instructions) and a verbatim quote from it."""


_YES_NO = re.compile(r"^\W*(yes|yeah|yep|no|nope|not really|i do|i don't|i do not|i have|i have not|i haven't)\b", re.I)
_HEARING_CHECK = re.compile(r"\b(can|could) you hear me\b|\bhear me (ok|okay|well|clearly)\b", re.I)


def _responsive_in_form(reply: str, question: str) -> bool:
    """Draft rule (not clinically validated): the model's 'off-topic' self-check is unreliable, so a reply that
    starts with yes/no, or any reply to the opening 'can you hear me?' check, is treated as an answer."""
    return bool(_YES_NO.match(reply)) or bool(_HEARING_CHECK.search(question))


def _preceding_clinician_text(window: list[Turn], idx: int) -> str:
    prev = [x for x in window if x.idx < idx and x.speaker == "clinician"]
    return prev[-1].text if prev else ""


class Breakdown(BaseModel):
    turn_idx: int
    quote: str
    cue: Literal["repeat_request", "off_topic", "bare_ack"]
    preceding_question: str = ""
    reply_answers_question: bool = False  # does the reply give the information the question asked for?


class RepairOut(BaseModel):
    breakdowns: list[Breakdown]


class TeachbackOut(BaseModel):
    gives_instructions: bool
    teach_back_done: bool
    instruction_turn: int | None = None
    quote: str | None = None


class ComprehensionAgent:
    def __init__(self, llm: LLM):
        self.llm = llm

    def check_repair(self, visit_id: str, window: list[Turn]) -> list[Flag]:
        out = self.llm.generate(REPAIR_PROMPT.format(transcript=fmt_turns(window)), RepairOut, SYSTEM)
        flags = []
        for b in out.breakdowns:
            t = turn_by_idx(window, b.turn_idx)
            # needs a later clinician turn, otherwise "not repaired yet" is undecidable
            if t is None or t.speaker == "clinician" or not quote_in(b.quote, t.text):
                continue
            if b.cue == "off_topic" and (
                b.reply_answers_question or _responsive_in_form(t.text, _preceding_clinician_text(window, t.idx))
            ):
                continue  # replies that answer the question in form are not a mismatch
            if not any(x.speaker == "clinician" and x.idx > t.idx for x in window):
                continue
            flags.append(
                Flag(
                    flag_id=flag_id(visit_id, "h", t.idx),
                    visit_id=visit_id,
                    type=GapType.COMPREHENSION_BREAKDOWN,
                    evidence=[EvidencePointer(source="transcript", ref=str(t.idx), quote=b.quote)],
                    rationale="The patient may not have heard or understood this and it was not repaired.",
                    raised_at_turn=window[-1].idx,
                )
            )
        return flags

    def check_teachback(self, visit_id: str, turns: list[Turn]) -> list[Flag]:
        out = self.llm.generate(TEACHBACK_PROMPT.format(transcript=fmt_turns(turns)), TeachbackOut, SYSTEM)
        if not out.gives_instructions or out.teach_back_done or out.instruction_turn is None or not out.quote:
            return []
        t = turn_by_idx(turns, out.instruction_turn)
        if t is None or t.speaker != "clinician" or not quote_in(out.quote, t.text):
            return []
        return [
            Flag(
                flag_id=flag_id(visit_id, "t", t.idx),
                visit_id=visit_id,
                type=GapType.COMPREHENSION_BREAKDOWN,
                evidence=[EvidencePointer(source="transcript", ref=str(t.idx), quote=out.quote)],
                rationale="Instructions were given without a teach-back to confirm the patient understood.",
                raised_at_turn=turns[-1].idx,
            )
        ]

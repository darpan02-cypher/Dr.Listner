"""ChecklistAgent: which verified checklist items were never covered? -> missed_question flags."""
from __future__ import annotations

from pydantic import BaseModel

from ..schemas import Checklist, EvidencePointer, Flag, GapType, Transcript
from .common import SAFETY_RULES, LLM, flag_id, fmt_turns, quote_in, turn_by_idx

SYSTEM = (
    "You audit a doctor-patient chest-pain visit transcript against a history checklist. " + SAFETY_RULES
)

PROMPT = """Checklist of history elements a clinician should cover:
{items}

Transcript:
{transcript}

For EVERY checklist item decide whether the visit covered it. An item is covered if the clinician asked about it
or the patient clearly gave that information, even without being asked. If covered, give the turn index and a
verbatim quote from that turn. If it was not covered anywhere, set covered=false, turn_idx=null, quote=null.
Do not count a vague mention that does not address the item."""


class ItemCoverage(BaseModel):
    item_id: str
    covered: bool
    turn_idx: int | None = None
    quote: str | None = None


class ChecklistOut(BaseModel):
    items: list[ItemCoverage]


class ChecklistAgent:
    def __init__(self, llm: LLM):
        self.llm = llm

    def run(self, transcript: Transcript, checklist: Checklist) -> tuple[list[Flag], dict[str, int | None]]:
        """Returns (candidate flags, coverage map item id -> covering turn idx or None)."""
        items = "\n".join(
            f"- {i.id}: {i.label}. {i.description} Example questions: {'; '.join(i.example_questions)}"
            for i in checklist.items
        )
        out = self.llm.generate(
            PROMPT.format(items=items, transcript=fmt_turns(transcript.turns)), ChecklistOut, SYSTEM
        )
        said = {c.item_id: c for c in out.items}
        coverage: dict[str, int | None] = {}
        flags: list[Flag] = []
        last = transcript.turns[-1].idx
        for item in checklist.items:
            c = said.get(item.id)
            cited = c is not None and c.covered and c.turn_idx is not None and c.quote
            turn = turn_by_idx(transcript.turns, c.turn_idx) if cited else None
            # A coverage claim only counts if its citation checks out; otherwise treat as uncovered.
            if turn is not None and quote_in(c.quote, turn.text):
                coverage[item.id] = turn.idx
                continue
            coverage[item.id] = None
            flags.append(
                Flag(
                    flag_id=flag_id(transcript.visit_id, "q", item.id),
                    visit_id=transcript.visit_id,
                    type=GapType.MISSED_QUESTION,
                    evidence=[EvidencePointer(source="checklist", ref=item.id)],
                    rationale=f"The visit does not appear to cover: {item.label}.",
                    raised_at_turn=last,
                )
            )
        return flags, coverage

"""ChartAgent: patient statements that conflict with a chart entry -> chart_contradiction flags."""
from __future__ import annotations

from pydantic import BaseModel

from ..schemas import Chart, EvidencePointer, Flag, GapType, Turn
from .common import SAFETY_RULES, LLM, flag_id, fmt_chart, fmt_turns, has_clinical_advice, quote_in, turn_by_idx

SYSTEM = "You compare what a patient says in a visit with their chart. " + SAFETY_RULES

PROMPT = """Chart:
{chart}

Recent transcript (judge ONLY the patient/caregiver turn with index {focus}; earlier turns are context):
{transcript}

Does what the patient says in turn {focus} directly conflict with a chart entry (for example denies a condition,
medication, allergy or procedure the chart lists, or claims one the chart lacks)? Report only clear conflicts.
Missing information, vague answers, and things the chart simply does not mention are NOT conflicts.
For each conflict give the chart entry_id, a verbatim quote of the patient's words, and a one-sentence neutral
rationale that states the two facts and does not interpret them."""


class Conflict(BaseModel):
    chart_entry_id: str
    turn_quote: str
    rationale: str


class ChartOut(BaseModel):
    conflicts: list[Conflict]


class ChartAgent:
    def __init__(self, llm: LLM):
        self.llm = llm

    def check_turn(self, visit_id: str, window: list[Turn], focus: int, chart: Chart) -> list[Flag]:
        """Judge one patient turn (idx `focus`, must be in `window`) against the chart."""
        t = turn_by_idx(window, focus)
        if t is None or t.speaker == "clinician":
            return []
        out = self.llm.generate(
            PROMPT.format(chart=fmt_chart(chart), transcript=fmt_turns(window), focus=focus), ChartOut, SYSTEM
        )
        flags: list[Flag] = []
        for c in out.conflicts:
            entry = chart.entry(c.chart_entry_id)
            if entry is None or not quote_in(c.turn_quote, t.text) or has_clinical_advice(c.rationale):
                continue
            flags.append(
                Flag(
                    flag_id=flag_id(visit_id, "x", focus, entry.entry_id),
                    visit_id=visit_id,
                    type=GapType.CHART_CONTRADICTION,
                    evidence=[
                        EvidencePointer(source="transcript", ref=str(focus), quote=c.turn_quote),
                        EvidencePointer(source="chart", ref=entry.entry_id, quote=entry.display),
                    ],
                    rationale=c.rationale,
                    raised_at_turn=window[-1].idx,
                )
            )
        return flags

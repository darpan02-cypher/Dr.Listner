"""Shared helpers for agents. Agents are pure functions of inputs plus an LLMClient."""
from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from ..schemas import Chart, Flag, Turn

T = TypeVar("T", bound=BaseModel)

SAFETY_RULES = (
    "You check documentation completeness only. Never suggest a diagnosis, a cause, or a treatment. "
    "Use only the text given. Quotes must be copied verbatim from the source text."
)


class LLM(Protocol):
    def generate(self, prompt: str, schema: type[T], system: str | None = None) -> T: ...


def norm(s: str) -> str:
    return " ".join(s.split())


def quote_in(quote: str, text: str) -> bool:
    """Whitespace-normalized substring check (SPEC section 5, VerifierAgent a)."""
    q = norm(quote)
    return bool(q) and q in norm(text)


def fmt_turns(turns: list[Turn]) -> str:
    return "\n".join(f"[{t.idx}] {t.speaker}: {t.text}" for t in turns)


def fmt_chart(chart: Chart) -> str:
    rows = [f"- {e.entry_id} | {e.resource_type} | {e.display}" + (f" | {e.status}" if e.status else "") for e in chart.entries]
    return f"age {chart.age}, sex {chart.sex}\n" + "\n".join(rows)


def flag_id(visit_id: str, kind: str, *parts: object) -> str:
    return "-".join([visit_id, kind, *map(str, parts)])


def turn_by_idx(turns: list[Turn], idx: int) -> Turn | None:
    return next((t for t in turns if t.idx == idx), None)


# Wording a flag must not contain (SPEC principle: no diagnosis or treatment suggestion).
import re

_CLINICAL_ADVICE = re.compile(
    r"\b(diagnos\w*|prescrib\w*|should (?:be )?(?:start|take|given|treated|admitted)\w*|"
    r"(?:may|might|likely|probably) (?:have|has|be)|myocardial infarction|heart attack|acs|angina|"
    r"rule out|recommend(?:s|ed)? (?:starting|taking|treatment))\b",
    re.I,
)


def has_clinical_advice(text: str) -> bool:
    return bool(_CLINICAL_ADVICE.search(text))

"""Deterministic orchestrator (SPEC sections 5 and 8). All model calls go through the agents.

process_turn(state, turn[, ctx]) folds one turn. With no ctx it only records the turn (Phase 1 contract).
With a ctx it also runs the passive per-turn detectors (types 3 and 4) on scrubbed text.
finalize(state, ctx) runs the omission detectors (types 1 and 2) once, after the last turn, and verifies.
Types 1 and 2 are never raised before finalize, so they are never raised before wrap-up.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

from . import deid
from .agents.chart_agent import ChartAgent
from .agents.checklist import ChecklistAgent
from .agents.common import LLM
from .agents.comprehension import ComprehensionAgent
from .agents.concern import ConcernAgent
from .agents.verifier import VerifierAgent, programmatic_ok
from .llm.client import LLMError
from .schemas import Chart, Checklist, Flag, GapType, PatientProfile, Transcript, Turn, VisitState

log = logging.getLogger(__name__)
WINDOW = 5  # turns of context handed to per-turn detectors
WRAP_UP = re.compile(
    r"(any other questions|anything else (?:you|i)|before you go|to (?:sum up|summari[sz]e)|"
    r"here'?s (?:the|our) plan|let'?s go over (?:the|our) plan|the plan (?:is|for)|what i'?d like you to do)",
    re.I,
)


@dataclass
class EngineContext:
    llm: LLM
    chart: Chart
    checklist: Checklist
    scrub: bool = True  # False only in tests that must not load the NER model
    verify: bool = True
    candidates: list[Flag] = field(default_factory=list)  # pre-verification flags, kept for eval/debugging

    def prep(self, turn: Turn) -> Turn:
        return deid.scrub_turn(turn, deid.keep_terms_from_chart(self.chart)) if self.scrub else turn


def _try(errors: list[str], name: str, fn, *args) -> list[Flag]:
    """Run one detector. A model failure is recorded in state.errors, never raised and never read as 'no gap'."""
    try:
        return fn(*args)
    except LLMError as e:
        log.warning("%s failed: %s", name, e)
        errors.append(f"{name}: {type(e).__name__}")
        return []


def _verify(errors: list[str], verifier: VerifierAgent, f: Flag, *args) -> Flag | None:
    """Verifier failure keeps the flag UNVERIFIED rather than dropping or silently trusting it."""
    try:
        return verifier.verify(f, *args)
    except LLMError as e:
        errors.append(f"verifier: {type(e).__name__}")
        return f if programmatic_ok(f, *args) else None


def new_state(visit_id: str, profile: PatientProfile) -> VisitState:
    return VisitState(visit_id=visit_id, profile=profile)


def _event_key(f: Flag) -> tuple:
    """One event = one flag (SPEC section 8). A chart conflict is the same event whichever turn restates it."""
    if f.type is GapType.CHART_CONTRADICTION:
        return (f.type, tuple(sorted(e.ref for e in f.evidence if e.source == "chart")))
    return (f.type, tuple((e.source, e.ref) for e in f.evidence))


def _known(flags: list[Flag], f: Flag) -> bool:
    return any(_event_key(x) == _event_key(f) for x in flags)


def process_turn(state: VisitState, turn: Turn, ctx: EngineContext | None = None) -> VisitState:
    """Pure function: returns a new state."""
    if state.turns_seen and turn.idx != state.turns_seen[-1].idx + 1:
        raise ValueError(f"turn idx {turn.idx} out of order")
    if ctx is None:
        return state.model_copy(update={"turns_seen": [*state.turns_seen, turn]})

    turn = ctx.prep(turn)
    seen = [*state.turns_seen, turn]
    wrapped = state.wrapped_up or (turn.speaker == "clinician" and bool(WRAP_UP.search(turn.text)))
    window = seen[-WINDOW:]
    active = set(state.profile.active_detectors)
    new: list[Flag] = []
    errors = list(state.errors)

    if GapType.CHART_CONTRADICTION in active and turn.speaker != "clinician":
        new += _try(errors, "chart", ChartAgent(ctx.llm).check_turn, state.visit_id, window, turn.idx, ctx.chart)
    # A repair can only be judged once the clinician has answered, so look back on clinician turns.
    if GapType.COMPREHENSION_BREAKDOWN in active and turn.speaker == "clinician" and len(seen) > 1:
        new += _try(errors, "comprehension", ComprehensionAgent(ctx.llm).check_repair, state.visit_id, window)

    cur = state.model_copy(update={"turns_seen": seen, "wrapped_up": wrapped})
    transcript = _transcript(cur)
    flags = list(state.flags)
    for f in new:
        if _known(flags, f):
            continue
        ctx.candidates.append(f)
        kept = _verify(errors, VerifierAgent(ctx.llm), f, transcript, ctx.chart, ctx.checklist) if ctx.verify else f
        if kept is not None:
            flags.append(kept)
    return cur.model_copy(update={"flags": flags, "errors": errors})


def _transcript(state: VisitState) -> Transcript:
    return Transcript(visit_id=state.visit_id, chart_id="", turns=state.turns_seen)


def finalize(state: VisitState, ctx: EngineContext) -> VisitState:
    """End-of-visit pass: omission detectors (types 1, 2), teach-back check, then verification."""
    if not state.turns_seen:
        raise ValueError("no turns to finalize")
    transcript = _transcript(state)
    active = set(state.profile.active_detectors)
    new: list[Flag] = []
    errors = list(state.errors)
    coverage = dict(state.checklist_coverage)
    if GapType.MISSED_QUESTION in active:
        try:
            flags, coverage = ChecklistAgent(ctx.llm).run(transcript, ctx.checklist)
            new += flags
        except LLMError as e:  # leave coverage empty: "unknown" must not look like "all missed" or "all covered"
            errors.append(f"checklist: {type(e).__name__}")
    if GapType.UNANSWERED_CONCERN in active:
        new += _try(errors, "concern", lambda: ConcernAgent(ctx.llm).run(transcript)[0])
    if GapType.COMPREHENSION_BREAKDOWN in active:
        agent = ComprehensionAgent(ctx.llm)
        new += _try(errors, "teachback", agent.check_teachback, state.visit_id, state.turns_seen)
        new += _try(errors, "comprehension", agent.check_repair, state.visit_id, state.turns_seen[-WINDOW:])  # last turns had no clinician reply yet
    cur = state.model_copy(update={"checklist_coverage": coverage, "wrapped_up": True})
    flags = list(state.flags)
    verifier = VerifierAgent(ctx.llm)
    for f in new:
        if _known(flags, f):
            continue
        ctx.candidates.append(f)
        kept = _verify(errors, verifier, f, transcript, ctx.chart, ctx.checklist) if ctx.verify else f
        if kept is not None:
            flags.append(kept)
    return cur.model_copy(update={"flags": flags, "errors": errors})


def run_batch(state: VisitState, turns: Iterable[Turn], ctx: EngineContext | None = None) -> VisitState:
    """Fold over all turns; with a ctx, also finalize."""
    for t in turns:
        state = process_turn(state, t, ctx)
    return finalize(state, ctx) if ctx is not None else state

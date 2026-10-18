"""Deterministic orchestrator. Agents are added in Phase 3; this is the contract."""
from __future__ import annotations

from typing import Iterable

from .schemas import PatientProfile, Turn, VisitState


def new_state(visit_id: str, profile: PatientProfile) -> VisitState:
    return VisitState(visit_id=visit_id, profile=profile)


def process_turn(state: VisitState, turn: Turn) -> VisitState:
    """Pure function: returns a new state. Phase 1 stub only records the turn.

    Rules to be enforced in Phase 3: no omission flag (types 1, 2) before wrap-up;
    types 3 and 4 may raise passive flags immediately.
    """
    if state.turns_seen and turn.idx != state.turns_seen[-1].idx + 1:
        raise ValueError(f"turn idx {turn.idx} out of order")
    return state.model_copy(update={"turns_seen": [*state.turns_seen, turn]})


def run_batch(state: VisitState, turns: Iterable[Turn]) -> VisitState:
    for t in turns:
        state = process_turn(state, t)
    return state

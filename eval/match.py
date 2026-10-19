"""Pure, greedy visit matching under SPEC sections 4, 8, and 10.

Inputs are already schema-validated. Verification is the engine's responsibility:
only verified flags are scored, while excluded flags remain in the audit output.
Dismissal is UI state and has no effect. This module performs no I/O and does not
recheck quotes or infer gaps from text. It matches the evidence references only.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from src.schemas import AnswerKey, Flag, GapType, PlantedGap


@dataclass(frozen=True)
class FlagAssignment:
    """One record per input flag, including duplicates and exclusions.

    Indices, rather than IDs, identify occurrences in the original input lists.
    A duplicate may reuse a flag_id; it must still be counted separately.
    """

    flag_index: int
    flag_id: str
    type: GapType
    outcome: Literal["TP", "FP", "EXCLUDED"]
    gap_index: int | None
    gap_id: str | None
    reason_code: str
    reason: str


@dataclass(frozen=True)
class GapAssignment:
    """One record per planted gap, in answer-key order."""

    gap_index: int
    gap_id: str
    type: GapType
    outcome: Literal["TP", "FN"]
    flag_index: int | None
    flag_id: str | None
    reason_code: str
    reason: str


@dataclass(frozen=True)
class VisitMatch:
    visit_id: str
    flags: tuple[FlagAssignment, ...]
    gaps: tuple[GapAssignment, ...]


def _matching_evidence(flag: Flag, gap: PlantedGap) -> str | None:
    """Return the first qualifying evidence description, or no match.

    Same type applies to BOTH arms of the contradiction's chart-or-turn rule.
    For missed questions, deletion indices belong to the base transcript and
    must never be used for matching against the edited transcript.
    """
    if flag.type != gap.type:
        return None
    for pointer in flag.evidence:
        if flag.type == GapType.MISSED_QUESTION:
            if pointer.source == "checklist" and pointer.ref == gap.checklist_item_id:
                return f"checklist ref {pointer.ref!r}"
        else:
            if (flag.type == GapType.CHART_CONTRADICTION
                    and pointer.source == "chart" and pointer.ref == gap.chart_entry_id):
                return f"chart ref {pointer.ref!r}"
            if pointer.source == "transcript":
                # The shared schema accepts isdigit() refs; some such Unicode
                # strings cannot be parsed as integer indices. They cannot match.
                try:
                    turn_index = int(pointer.ref)
                except ValueError:
                    continue
                if turn_index in gap.turn_indices:
                    return f"transcript turn {turn_index}"
    return None


def match_visit(flags: Sequence[Flag], key: AnswerKey) -> VisitMatch:
    """Assign every flag and gap once, without modifying either input.

    Visit flags in file order; for each verified flag select the first eligible,
    unmatched gap in answer-key order. This intentionally does not maximize the
    number of matches. An unverified flag neither consumes a gap nor counts as
    an FP (SPEC section 10); its corresponding gap may therefore remain an FN.
    A wrong visit_id is an invalid input, including on an unverified flag.
    """
    for index, flag in enumerate(flags):
        if flag.visit_id != key.visit_id:
            raise ValueError(
                f"flags[{index}] ({flag.flag_id!r}) has visit_id {flag.visit_id!r}; "
                f"expected {key.visit_id!r}"
            )

    assignments: list[FlagAssignment] = []
    matched: dict[int, FlagAssignment] = {}
    for flag_index, flag in enumerate(flags):
        gap_index = None
        gap_id = None
        if not flag.verified:
            outcome, code, reason = "EXCLUDED", "unverified", "verified=False; excluded under SPEC section 10."
        else:
            candidates = [
                (index, evidence)
                for index, gap in enumerate(key.planted_gaps)
                if (evidence := _matching_evidence(flag, gap)) is not None
            ]
            available = next(((index, evidence) for index, evidence in candidates if index not in matched), None)
            if available is not None:
                gap_index, evidence = available
                gap_id = key.planted_gaps[gap_index].gap_id
                outcome, code = "TP", "matched"
                reason = f"Same type and {evidence} match gap[{gap_index}] {gap_id!r}."
            elif candidates:
                outcome, code = "FP", "duplicate"
                used = ", ".join(f"gap[{index}] {key.planted_gaps[index].gap_id!r}" for index, _ in candidates)
                reason = f"All matching gaps were assigned to earlier flags: {used}."
            elif key.is_clean:
                outcome, code, reason = "FP", "clean_visit", "Answer key has no planted gaps."
            elif not any(gap.type == flag.type for gap in key.planted_gaps):
                outcome, code, reason = "FP", "no_same_type_gap", "Answer key has no planted gap of this type."
            else:
                outcome, code, reason = "FP", "evidence_mismatch", "No same-type gap matches the required evidence references."
        assignment = FlagAssignment(flag_index, flag.flag_id, flag.type, outcome, gap_index, gap_id, code, reason)
        assignments.append(assignment)
        if gap_index is not None:
            matched[gap_index] = assignment

    gaps = []
    for gap_index, gap in enumerate(key.planted_gaps):
        assignment = matched.get(gap_index)
        gaps.append(GapAssignment(
            gap_index=gap_index, gap_id=gap.gap_id, type=gap.type,
            outcome="TP" if assignment is not None else "FN",
            flag_index=assignment.flag_index if assignment is not None else None,
            flag_id=assignment.flag_id if assignment is not None else None,
            reason_code="matched" if assignment is not None else "unmatched_gap",
            reason=(assignment.reason if assignment is not None
                    else "No verified flag was assigned to this gap by greedy file-order matching."),
        ))
    return VisitMatch(key.visit_id, tuple(assignments), tuple(gaps))

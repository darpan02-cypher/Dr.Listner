"""Micro-averaged counts, Wilson intervals, and timing for verified flags."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from math import sqrt
from statistics import mean, median

from eval.match import VisitMatch, match_visit
from src.schemas import AnswerKey, Flag, GapType, TypeMetrics


def type_metrics(tp: int, fp: int, fn: int) -> TypeMetrics:
    if min(tp, fp, fn) < 0:
        raise ValueError("Counts must be nonnegative")
    return TypeMetrics(
        tp=tp, fp=fp, fn=fn,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / (tp + fn) if tp + fn else None,
        f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    )


def wilson_interval(successes: int, trials: int) -> dict[str, float | None]:
    """Two-sided Wilson score interval at 95%; no trials means unavailable."""
    if not 0 <= successes <= trials:
        raise ValueError("Expected 0 <= successes <= trials")
    if trials == 0:
        return {"lower": None, "upper": None}
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    radius = z * sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return {"lower": max(0.0, center - radius), "upper": min(1.0, center + radius)}


def _count_details(metric: TypeMetrics, n_visits: int) -> dict:
    return {
        "n_visits": n_visits, "n_gaps": metric.tp + metric.fn,
        "n_predictions": metric.tp + metric.fp,
        "precision_ci95": wilson_interval(metric.tp, metric.tp + metric.fp),
        "recall_ci95": wilson_interval(metric.tp, metric.tp + metric.fn),
    }


def _delay_details(values: list[int], missing: int) -> dict:
    return {
        "n_tp": len(values) + missing, "n_timed": len(values),
        "n_missing_raised_at_turn": missing,
        "mean": mean(values) if values else None,
        "median": median(values) if values else None,
        "n_negative": sum(value < 0 for value in values),
        "values": values,
    }


@dataclass
class Aggregate:
    n_visits: int
    per_type: dict[GapType, TypeMetrics]
    overall: TypeMetrics
    false_flags_per_visit: float
    n_clean_visits: int
    false_flags_on_clean_visits: int
    extras: dict
    matches: tuple[VisitMatch, ...]


def aggregate(visits: Sequence[tuple[AnswerKey, Sequence[Flag]]]) -> Aggregate:
    """Score a split; preserve supplied visit, flag, and gap order in the audit.

    Null type-1/2 emission times mean end-of-visit. Missing wrap-up time makes
    explicit emission times unassessable. Delays retain negative values and
    report their count; only matched, verified type-3/4 flags enter delays.
    """
    if not visits:
        raise ValueError("Cannot evaluate an empty split")
    ids = [key.visit_id for key, _ in visits]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate visit IDs")
    if len({key.split for key, _ in visits}) != 1:
        raise ValueError("Cannot aggregate different splits together")
    counts = {kind: [0, 0, 0] for kind in GapType}
    excluded = {kind.value: 0 for kind in GapType}
    early = {kind.value: {"n_flags": 0, "n_too_early": 0, "n_assumed_end": 0,
                         "n_missing_wrap_up": 0}
             for kind in (GapType.MISSED_QUESTION, GapType.UNANSWERED_CONCERN)}
    values = {kind: [] for kind in (GapType.CHART_CONTRADICTION, GapType.COMPREHENSION_BREAKDOWN)}
    missing = {kind: 0 for kind in values}
    matches = []
    n_clean = clean_fp = 0
    for key, flags in visits:
        result = match_visit(flags, key)
        matches.append(result)
        n_clean += key.is_clean
        for assignment in result.flags:
            kind = assignment.type
            flag = flags[assignment.flag_index]
            if assignment.outcome == "EXCLUDED":
                excluded[kind.value] += 1
                continue
            counts[kind][0 if assignment.outcome == "TP" else 1] += 1
            clean_fp += key.is_clean and assignment.outcome == "FP"
            if kind.value in early:
                detail = early[kind.value]
                detail["n_flags"] += 1
                if flag.raised_at_turn is None:
                    detail["n_assumed_end"] += 1
                elif key.wrap_up_turn is None:
                    detail["n_missing_wrap_up"] += 1
                else:
                    detail["n_too_early"] += flag.raised_at_turn < key.wrap_up_turn
            if assignment.outcome == "TP" and kind in values:
                if flag.raised_at_turn is None:
                    missing[kind] += 1
                else:
                    planted = key.planted_gaps[assignment.gap_index].turn_indices[0]
                    values[kind].append(flag.raised_at_turn - planted)
        for assignment in result.gaps:
            counts[assignment.type][2] += assignment.outcome == "FN"

    per_type = {kind: type_metrics(*count) for kind, count in counts.items()}
    overall = type_metrics(*(sum(count[i] for count in counts.values()) for i in range(3)))
    early_total = {field: sum(detail[field] for detail in early.values())
                   for field in next(iter(early.values()))}
    all_values = [value for kind in values for value in values[kind]]
    extras = {
        "schema_version": 1,
        "per_type": {kind.value: _count_details(metric, len(visits)) for kind, metric in per_type.items()},
        "overall": _count_details(overall, len(visits)),
        "excluded_unverified": {"per_type": excluded, "total": sum(excluded.values())},
        "too_early": {"per_type": early, "total": early_total},
        "turns_to_detection": {
            "per_type": {kind.value: _delay_details(values[kind], missing[kind]) for kind in values},
            "overall": _delay_details(all_values, sum(missing.values())),
        },
        "assignments": [asdict(result) for result in matches],
    }
    return Aggregate(len(visits), per_type, overall, overall.fp / len(visits),
                     n_clean, clean_fp, extras, tuple(matches))

"""FP/FN evidence export; no diagnosis, inference, or quote reconstruction."""
from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence

from eval.io import DatasetVisit
from eval.match import VisitMatch
from src.schemas import Flag, GapType


def errors_csv(run_id: str, visits: Sequence[DatasetVisit],
               flags: dict[str, list[Flag]], matches: Sequence[VisitMatch]) -> str:
    """One row per scored FP or FN. Oracle runs have only the header.

    FP quotes are exactly what the engine emitted (possibly de-identified).
    FN quotes come from the synthetic ground truth. Missed-question FNs use
    checklist IDs and explicitly label deletion indices as base-transcript
    positions; they cannot be quoted from the edited visit.
    """
    stream = io.StringIO(newline="")
    fields = ["run_id", "visit_id", "type", "outcome", "flag_index", "flag_id",
              "gap_index", "gap_id", "reason_code", "reason", "evidence",
              "edit_op", "turn_indices", "index_space", "details", "raised_at_turn", "dismissed"]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    by_id = {visit.key.visit_id: visit for visit in visits}
    for match in matches:
        visit = by_id[match.visit_id]
        for assignment in match.flags:
            if assignment.outcome != "FP":
                continue
            flag = flags[match.visit_id][assignment.flag_index]
            writer.writerow({
                "run_id": run_id, "visit_id": match.visit_id, "type": flag.type.value,
                "outcome": "FP", "flag_index": assignment.flag_index, "flag_id": flag.flag_id,
                "reason_code": assignment.reason_code, "reason": assignment.reason,
                "evidence": json.dumps([p.model_dump(mode="json") for p in flag.evidence], ensure_ascii=False),
                "index_space": "final_transcript", "details": flag.rationale,
                "raised_at_turn": flag.raised_at_turn, "dismissed": flag.dismissed,
            })
        for assignment in match.gaps:
            if assignment.outcome != "FN":
                continue
            gap = visit.key.planted_gaps[assignment.gap_index]
            if gap.type == GapType.MISSED_QUESTION:
                evidence = [{"source": "checklist", "ref": gap.checklist_item_id, "quote": None}]
            else:
                evidence = [{"source": "transcript", "ref": str(index),
                             "quote": visit.transcript.turn(index).text} for index in gap.turn_indices]
            if gap.chart_entry_id is not None:
                entry = visit.chart.entry(gap.chart_entry_id)
                evidence.append({"source": "chart", "ref": entry.entry_id, "quote": entry.display})
            writer.writerow({
                "run_id": run_id, "visit_id": match.visit_id, "type": gap.type.value,
                "outcome": "FN", "gap_index": assignment.gap_index, "gap_id": gap.gap_id,
                "reason_code": assignment.reason_code, "reason": assignment.reason,
                "evidence": json.dumps(evidence, ensure_ascii=False), "edit_op": gap.edit_op,
                "turn_indices": json.dumps(gap.turn_indices),
                "index_space": "base_transcript" if gap.type == GapType.MISSED_QUESTION else "final_transcript",
                "details": gap.description,
            })
    return stream.getvalue()

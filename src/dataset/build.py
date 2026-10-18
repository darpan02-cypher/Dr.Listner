"""Build development fixtures, with answer keys derived only from explicit edits.

Charts are hand-authored synthetic fixtures, not Synthea output. These deliberately
simple scripts exercise pipeline contracts; they are not a clinical benchmark.
"""
from __future__ import annotations

import json
from pathlib import Path

from src import config
from src.schemas import (
    AnswerKey, Chart, ChartEntry, Checklist, GapType, PlanItem, PlantedGap,
    Transcript, Turn,
)

# Each question and answer occupies its own removable pair of turns.
HISTORY = {
    "onset": ("When did the pain start, and did it begin suddenly or gradually?", "It started gradually yesterday afternoon."),
    "exertional": ("Does walking or climbing stairs bring it on, and does rest help?", "Walking brings it on, and resting helps."),
    "radiation": ("Does the pain spread to your arm, jaw, neck, or back?", "No, it stays in one spot."),
    "diaphoresis": ("Do you break out in a sweat with the pain?", "No, I have not noticed sweating."),
    "dyspnea": ("Do you feel short of breath with the pain?", "No, my breathing feels the same."),
    "syncope": ("Have you fainted, felt lightheaded, or felt like you might pass out?", "No, none of those."),
    "family_history": ("Has a close relative had heart disease at a young age?", "No, not that I know of."),
    "risk_factors": ("Do you smoke, or have high blood pressure, diabetes, or high cholesterol?", "I do not smoke. I have high blood pressure, but no diabetes or high cholesterol."),
}
PLAN = "We will review your medicine list together before this visit ends. Please bring that list to your next appointment."
CONCERN = "I am worried I will not understand the words in my visit summary. Can someone help me read it?"


def base_visit(visit_id: str, variant: int = 0) -> tuple[Transcript, Chart, dict[str, list[int]]]:
    chart_id = f"chart-{visit_id}"
    turns: list[Turn] = []
    def add(speaker: str, text: str) -> None:
        turns.append(Turn(idx=len(turns), speaker=speaker, text=text))
    add("clinician", "Tell me what brought you in today.")
    add("patient", ("I have noticed chest discomfort.", "I want to discuss pain in my chest.", "I have been feeling chest pain.")[variant % 3])
    ranges = {}
    for item, (question, answer) in HISTORY.items():
        ranges[item] = [len(turns), len(turns) + 1]
        add("clinician", question)
        add("patient", answer)
    add("clinician", "What heart procedures have you had before?")
    add("patient", "I had a coronary stent placed several years ago.")
    add("clinician", PLAN)
    add("patient", "I understand those two steps. I have no other questions today.")
    chart = Chart(chart_id=chart_id, age=45 + variant, sex="female" if variant % 2 else "male", entries=[
        ChartEntry(entry_id="hypertension", resource_type="Condition", display="High blood pressure", status="active"),
        ChartEntry(entry_id="stent", resource_type="Procedure", display="Coronary stent placement", status="completed", date="2020-01-10"),
    ])
    return Transcript(visit_id=visit_id, chart_id=chart_id, turns=turns), chart, ranges


def plant_gaps(base: Transcript, chart: Chart, ranges: dict[str, list[int]], *,
               missing: str | None = None, concern: bool = False,
               contradiction: bool = False, split: str = "dev") -> tuple[Transcript, AnswerKey]:
    """Apply edits, retaining pre-edit deletion and post-edit insertion indices."""
    if base.chart_id != chart.chart_id:
        raise ValueError("Transcript and chart must refer to the same chart")
    deleted = set()
    gaps = []
    if missing is not None:
        if missing not in ranges:
            raise ValueError(f"Unknown checklist item: {missing}")
        deleted = set(ranges[missing])
        if not deleted or any(base.turn(i) is None for i in deleted):
            raise ValueError("Deletion references missing turns")
        gaps.append(PlantedGap(gap_id=f"{base.visit_id}-missing", type=GapType.MISSED_QUESTION,
            edit_op="delete_turns", turn_indices=sorted(deleted), checklist_item_id=missing,
            description=f"Deleted the question and answer for {missing} from the base transcript."))
    turns = []
    for turn in base.turns:
        if turn.idx in deleted:
            continue
        turns.append(turn.model_copy(update={"idx": len(turns)}))
    if contradiction:
        entry = chart.entry("stent")
        if entry is None:
            raise ValueError("Contradiction requires a stent chart entry")
        old = next((i for i, t in enumerate(turns) if t.text == "I had a coronary stent placed several years ago."), None)
        if old is None:
            raise ValueError("Expected heart-history response not found")
        # Remove the truthful answer, then insert its contradictory replacement.
        turns.pop(old)
        turns.insert(old, Turn(idx=old, speaker="patient", text="I have never had any heart procedures or a stent."))
        gaps.append(PlantedGap(gap_id=f"{base.visit_id}-contradiction", type=GapType.CHART_CONTRADICTION,
            edit_op="insert_contradiction", turn_indices=[old], chart_entry_id=entry.entry_id,
            description="Replaced the truthful procedure response with a denial of the charted stent."))
    if concern:
        # Last turn: no subsequent clinician response can answer the new concern.
        idx = len(turns)
        turns.append(Turn(idx=idx, speaker="patient", text=CONCERN))
        gaps.append(PlantedGap(gap_id=f"{base.visit_id}-concern", type=GapType.UNANSWERED_CONCERN,
            edit_op="insert_concern", turn_indices=[idx], description="Appended a request for help reading the summary after the clinician's final turn."))
    transcript = Transcript(visit_id=base.visit_id, chart_id=base.chart_id, turns=turns)
    key = AnswerKey(visit_id=base.visit_id, split=split, planted_gaps=gaps, plan_items=[
        PlanItem(item_id="review-list", text="Review the medicine list together before the visit ends."),
        PlanItem(item_id="bring-list", text="Bring the medicine list to the next appointment."),
    ])
    return transcript, key


def build_dataset(output: Path) -> dict:
    checklist = Checklist.model_validate_json(config.CHECKLIST_PATH.read_text())
    if set(HISTORY) != {item.id for item in checklist.items}:
        raise ValueError("Scripted history does not match checklist IDs")
    # Dev only: template siblings are unsuitable for an independent test split.
    cases = [(None, False, False)] * 3
    cases += [(item, False, False) for item in HISTORY]
    cases += [(None, True, False)] * 3 + [(None, False, True)] * 3
    cases += [(item, True, True) for item in HISTORY]
    records = []
    for number, (missing, concern, contradiction) in enumerate(cases, 1):
        visit_id = f"dev-{number:03d}"
        base, chart, ranges = base_visit(visit_id, number)
        transcript, key = plant_gaps(base, chart, ranges, missing=missing, concern=concern, contradiction=contradiction)
        for folder, value in (("base_transcripts", base), ("transcripts", transcript), ("charts", chart), ("answer_keys", key)):
            path = output / folder / f"{visit_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value.model_dump_json(indent=2) + "\n")
        records.append({"visit_id": visit_id, "chart_id": chart.chart_id, "split": key.split, "gap_count": len(key.planted_gaps)})
    manifest = {"version": 1, "synthetic": True, "source": "hand-authored synthetic fixtures; not Synthea", "purpose": "development contract fixtures; not an independent clinical evaluation", "checklist_version": checklist.version, "checklist_verified": all(i.verification_status == "VERIFIED" for i in checklist.items), "visits": records}
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest

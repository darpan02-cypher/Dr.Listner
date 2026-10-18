"""Generate deterministic FAKE runs for harness checks, never engine metrics.

Example: python -m eval.fake_runs --run fake-dev-oracle --split dev --scenario oracle
Mutation counts are split-wide, applied in filename/flag order. --type optionally
restricts drop, wrong-type, early, and duplicates. Extra/clean add concern flags.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from eval.io import ROOT, DatasetVisit, InputError, RunMeta, load_dataset, safe_run_id
from eval.match import match_visit
from src.schemas import EvidencePointer, Flag, GapType

SCENARIOS = ("oracle", "drop", "extra", "wrong-type", "clean", "early", "duplicates")


def _transcript_pointer(visit: DatasetVisit, index: int) -> EvidencePointer:
    return EvidencePointer(source="transcript", ref=str(index), quote=visit.transcript.turn(index).text)


def oracle_flags(visit: DatasetVisit) -> list[Flag]:
    flags = []
    for index, gap in enumerate(visit.key.planted_gaps):
        evidence = []
        if gap.type == GapType.MISSED_QUESTION:
            evidence.append(EvidencePointer(source="checklist", ref=gap.checklist_item_id))
        else:
            evidence.append(_transcript_pointer(visit, gap.turn_indices[0]))
        if gap.type == GapType.CHART_CONTRADICTION:
            entry = visit.chart.entry(gap.chart_entry_id)
            evidence.append(EvidencePointer(source="chart", ref=entry.entry_id, quote=entry.display))
        turn = (len(visit.transcript.turns) - 1 if gap.type in (GapType.MISSED_QUESTION, GapType.UNANSWERED_CONCERN)
                else gap.turn_indices[0])
        flags.append(Flag(
            flag_id=f"fake-{visit.key.visit_id}-{index}", visit_id=visit.key.visit_id,
            type=gap.type, evidence=evidence, rationale="FAKE oracle flag copied from a planted-gap key.",
            verified=True, raised_at_turn=turn,
        ))
    return flags


def _false_concern(visit: DatasetVisit, index: int) -> Flag:
    planted = {turn for gap in visit.key.planted_gaps if gap.type == GapType.UNANSWERED_CONCERN for turn in gap.turn_indices}
    turn = next((turn for turn in visit.transcript.turns if turn.speaker in {"patient", "caregiver"} and turn.idx not in planted), None)
    if turn is None:
        raise InputError(f"{visit.key.visit_id}: no patient/caregiver turn available for a false concern")
    return Flag(flag_id=f"fake-extra-{visit.key.visit_id}-{index}", visit_id=visit.key.visit_id,
                type=GapType.UNANSWERED_CONCERN, evidence=[_transcript_pointer(visit, turn.idx)],
                rationale="FAKE extra concern on a turn without a planted concern.", verified=True,
                raised_at_turn=len(visit.transcript.turns) - 1)


def generate_flags(visits: list[DatasetVisit], scenario: str, count: int = 1,
                   kind: GapType | None = None) -> dict[str, list[Flag]]:
    if scenario not in SCENARIOS or count < 1:
        raise InputError("Use a known scenario and count >= 1")
    if kind is not None and scenario in {"oracle", "extra", "clean"}:
        raise InputError("--type only applies to drop, wrong-type, early, or duplicates")
    flags = {v.key.visit_id: oracle_flags(v) for v in visits}
    if scenario == "oracle":
        return flags
    if scenario in {"extra", "clean"}:
        visit = next((v for v in visits if v.key.is_clean == (scenario == "clean")), None)
        if visit is None:
            raise InputError(f"No suitable visit for {scenario!r}")
        flags[visit.key.visit_id].extend(_false_concern(visit, i) for i in range(count))
        return flags
    eligible = [(visit, index, flag) for visit in visits for index, flag in enumerate(flags[visit.key.visit_id])
                if (kind is None or flag.type == kind)
                and (scenario != "early" or flag.type in {GapType.MISSED_QUESTION, GapType.UNANSWERED_CONCERN})]
    if count > len(eligible):
        raise InputError(f"Requested {count} mutations but only {len(eligible)} eligible flags exist")
    selected = eligible[:count]
    if scenario == "drop":
        dropped = {(v.key.visit_id, index) for v, index, _ in selected}
        return {vid: [f for index, f in enumerate(items) if (vid, index) not in dropped] for vid, items in flags.items()}
    for visit, index, flag in selected:
        items = flags[visit.key.visit_id]
        if scenario == "duplicates":
            items.append(flag.model_copy(update={"flag_id": f"{flag.flag_id}-duplicate"}))
        elif scenario == "early":
            wrap = visit.key.wrap_up_turn
            if wrap is None or wrap == 0:
                raise InputError(f"{visit.key.visit_id}: cannot emit before missing/zero wrap_up_turn")
            items[index] = flag.model_copy(update={"raised_at_turn": wrap - 1})
        elif scenario == "wrong-type":
            # Both alternative types require transcript evidence. Preserve the
            # original quote when possible, otherwise use an actual patient turn.
            new_type = (GapType.COMPREHENSION_BREAKDOWN if flag.type == GapType.UNANSWERED_CONCERN
                        else GapType.UNANSWERED_CONCERN)
            pointer = next((p for p in flag.evidence if p.source == "transcript"), None)
            if pointer is None:
                pointer = _false_concern(visit, index).evidence[0]
            replacement = Flag(**(flag.model_dump() | {
                "type": new_type, "evidence": [pointer], "rationale": "FAKE flag with intentionally wrong gap type.",
            }))
            if match_visit([replacement], visit.key).flags[0].outcome != "FP":
                raise InputError(f"{visit.key.visit_id}: wrong-type mutation would match a different planted gap")
            items[index] = replacement
    return flags


def write_fake_run(run_id: str, split: str, scenario: str = "oracle", count: int = 1,
                   kind: GapType | None = None, *, data_root: Path = ROOT / "data/eval",
                   runs_root: Path = ROOT / "eval/runs") -> Path:
    safe_run_id(run_id)
    visits = load_dataset(data_root, split)
    flags = generate_flags(visits, scenario, count, kind)
    meta = RunMeta(run_id=run_id, system="drlistner", mode="DEMO", model=f"FAKE/{scenario}", split=split)
    run_dir = runs_root / run_id
    if run_dir.exists():
        raise InputError(f"{run_dir}: already exists; choose a new fake run ID")
    run_dir.mkdir(parents=True)
    (run_dir / "flags").mkdir()
    (run_dir / "run_meta.json").write_text(meta.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (run_dir / "fake_recipe.json").write_text(json.dumps({
        "scenario": scenario, "count": count, "type": kind.value if kind else None,
        "note": "Fabricated flags for harness validation, not detector output.",
    }, indent=2) + "\n", encoding="utf-8")
    for vid, items in flags.items():
        (run_dir / "flags" / f"{vid}.json").write_text(
            json.dumps([Flag.model_validate(f.model_dump()).model_dump(mode="json") for f in items], indent=2) + "\n",
            encoding="utf-8",
        )
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--split", required=True, choices=["dev", "test"])
    parser.add_argument("--scenario", choices=SCENARIOS, default="oracle")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--type", choices=[kind.value for kind in GapType])
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/eval")
    parser.add_argument("--runs-root", type=Path, default=ROOT / "eval/runs")
    args = parser.parse_args(argv)
    try:
        path = write_fake_run(args.run, args.split, args.scenario, args.count,
                              GapType(args.type) if args.type else None,
                              data_root=args.data_root, runs_root=args.runs_root)
    except (InputError, OSError) as error:
        print(f"Fake run failed:\n{error}", file=sys.stderr)
        return 2
    print(f"Wrote FAKE run to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate and score a file-based engine run without calling the engine."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from eval.io import ROOT, InputError, load_dataset, load_run, safe_run_id
from eval.metrics import aggregate
from src.schemas import EvalResult, GapType


def results_csv(result: dict) -> str:
    stream = io.StringIO(newline="")
    fields = ["run_id", "system", "split", "mode", "model", "type", "n_visits", "n_gaps",
              "n_predictions", "tp", "fp", "fn", "precision", "recall", "f1",
              "precision_ci95_lower", "precision_ci95_upper", "recall_ci95_lower", "recall_ci95_upper"]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for name in [kind.value for kind in GapType] + ["overall"]:
        metric = result["overall"] if name == "overall" else result["per_type"][name]
        detail = result["extras"]["overall"] if name == "overall" else result["extras"]["per_type"][name]
        row = {field: result[field] for field in ("run_id", "system", "split", "mode", "model")}
        row.update(type=name, **metric)
        row.update({field: detail[field] for field in ("n_visits", "n_gaps", "n_predictions")})
        for measure in ("precision", "recall"):
            for bound in ("lower", "upper"):
                row[f"{measure}_ci95_{bound}"] = detail[f"{measure}_ci95"][bound]
        writer.writerow(row)
    return stream.getvalue()


def _write_result(path: Path, text: str) -> None:
    """Replace one artifact atomically; never leave a partly written JSON/CSV."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def evaluate_run(run_id: str, split: str, *, data_root: Path = ROOT / "data/eval",
                 runs_root: Path = ROOT / "eval/runs", results_root: Path = ROOT / "eval/results") -> dict:
    safe_run_id(run_id)
    visits = load_dataset(data_root, split)
    meta, flags = load_run(runs_root / run_id, run_id, split, visits)
    scores = aggregate([(visit.key, flags[visit.key.visit_id]) for visit in visits])
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise InputError(f"Cannot record git_commit: {error}") from error
    result = EvalResult(
        **meta.model_dump(), git_commit=commit,
        timestamp=datetime.now(timezone.utc).isoformat(), n_visits=scores.n_visits,
        per_type=scores.per_type, overall=scores.overall,
        false_flags_per_visit=scores.false_flags_per_visit,
        n_clean_visits=scores.n_clean_visits, false_flags_on_clean_visits=scores.false_flags_on_clean_visits,
        mean_reading_grade=None, plan_coverage=None,
    ).model_dump(mode="json")
    result["extras"] = scores.extras
    result["extras"]["verification_policy"] = "verified_only_for_all_systems (SPEC section 10)"
    # FAKE/ is the generator's reserved model prefix. Scores from these runs are
    # harness checks, never evidence of engine quality.
    result["extras"]["synthetic_run"] = meta.model.startswith("FAKE/")
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    table = results_csv(result)
    results_root.mkdir(parents=True, exist_ok=True)
    _write_result(results_root / f"{run_id}.json", payload)
    _write_result(results_root / f"{run_id}.csv", table)
    # Return the same JSON-native structure that callers read from disk (the
    # match audit uses immutable tuples internally).
    return json.loads(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="Run directory name under eval/runs")
    parser.add_argument("--split", required=True, choices=["dev", "test"])
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/eval")
    parser.add_argument("--runs-root", type=Path, default=ROOT / "eval/runs")
    parser.add_argument("--results-root", type=Path, default=ROOT / "eval/results")
    args = parser.parse_args(argv)
    try:
        result = evaluate_run(args.run, args.split, data_root=args.data_root,
                              runs_root=args.runs_root, results_root=args.results_root)
    except (InputError, OSError) as error:
        print(f"Evaluation failed:\n{error}", file=sys.stderr)
        return 2
    print(f"Wrote {args.results_root / (args.run + '.json')} and {args.run}.csv")
    if result["extras"]["synthetic_run"]:
        print("FAKE run: these results validate the harness, not the detection engine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

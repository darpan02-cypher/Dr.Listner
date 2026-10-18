"""End-to-end file contract checks using oracle data, never the live engine."""
import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from eval.fake_runs import SCENARIOS, generate_flags, write_fake_run
from eval.io import ROOT, InputError, load_dataset
from eval.metrics import aggregate
from eval.run_eval import evaluate_run, main
from src.schemas import EvalResult, Flag, GapType


@pytest.fixture
def run(tmp_path):
    write_fake_run("oracle", "dev", runs_root=tmp_path / "runs")
    return tmp_path


def evaluate(directory, run_id="oracle", split="dev"):
    return evaluate_run(run_id, split, runs_root=directory / "runs", results_root=directory / "results")


@pytest.mark.parametrize("split", ["dev", "test"])
def test_oracle_cli_schema_csv_and_reproducibility(tmp_path, split):
    run_id = f"fake-{split}"
    write_fake_run(run_id, split, runs_root=tmp_path / "runs")
    command = [sys.executable, "-m", "scripts.run_eval", "--run", run_id, "--split", split,
               "--runs-root", str(tmp_path / "runs"), "--results-root", str(tmp_path / "results")]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert "FAKE run" in completed.stdout
    path = tmp_path / "results" / f"{run_id}.json"
    raw = json.loads(path.read_text())
    validated = EvalResult.model_validate({k: v for k, v in raw.items() if k != "extras"})
    assert validated.split == split
    assert validated.mean_reading_grade is None and validated.plan_coverage is None
    assert validated.git_commit == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    for metric in validated.per_type.values():
        assert metric.precision == metric.recall == metric.f1 == 1.0
        assert metric.tp > 0 and metric.fp == metric.fn == 0
    assert raw["extras"]["too_early"]["total"]["n_too_early"] == 0
    assert raw["extras"]["synthetic_run"] is True
    csv_path = path.with_suffix(".csv")
    first_csv = csv_path.read_bytes()
    rows = list(csv.DictReader(first_csv.decode().splitlines()))
    assert len(rows) == len(GapType) + 1
    for row in rows:
        metric = raw["overall"] if row["type"] == "overall" else raw["per_type"][row["type"]]
        assert int(row["tp"]) == metric["tp"]
        assert float(row["recall"]) == metric["recall"]
        assert int(row["n_gaps"]) == metric["tp"] + metric["fn"]
    rerun = evaluate(tmp_path, run_id, split)
    for payload in (raw, rerun):
        payload.pop("timestamp")
        payload.pop("git_commit")
    assert raw == rerun
    assert first_csv == csv_path.read_bytes()


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_fake_scenarios_exact_effects_and_real_quotes(scenario):
    visits = load_dataset(ROOT / "data/eval", "dev")
    output = generate_flags(visits, scenario, count=1)
    baseline = aggregate([(v.key, generate_flags([v], "oracle")[v.key.visit_id]) for v in visits])
    scored = aggregate([(v.key, output[v.key.visit_id]) for v in visits])
    n = baseline.overall.tp
    expected = {
        "oracle": (n, 0, 0), "drop": (n - 1, 0, 1), "extra": (n, 1, 0),
        "wrong-type": (n - 1, 1, 1), "clean": (n, 1, 0), "early": (n, 0, 0), "duplicates": (n, 1, 0),
    }
    assert (scored.overall.tp, scored.overall.fp, scored.overall.fn) == expected[scenario]
    assert scored.false_flags_on_clean_visits == (1 if scenario == "clean" else 0)
    assert scored.extras["too_early"]["total"]["n_too_early"] == (1 if scenario == "early" else 0)
    for visit in visits:
        for item in output[visit.key.visit_id]:
            Flag.model_validate(item.model_dump())
            for pointer in item.evidence:
                if pointer.source == "transcript":
                    assert pointer.quote == visit.transcript.turn(int(pointer.ref)).text
                elif pointer.source == "chart":
                    assert pointer.quote == visit.chart.entry(pointer.ref).display


def test_fake_drop_type_filter_and_no_overwrite(tmp_path):
    visits = load_dataset(ROOT / "data/eval", "dev")
    flags = generate_flags(visits, "drop", 2, GapType.MISSED_QUESTION)
    result = aggregate([(v.key, flags[v.key.visit_id]) for v in visits])
    assert result.per_type[GapType.MISSED_QUESTION].fn == 2
    assert result.per_type[GapType.UNANSWERED_CONCERN].fn == 0
    with pytest.raises(InputError, match="eligible"):
        generate_flags(visits, "drop", 1000)
    with pytest.raises(InputError, match="only applies"):
        generate_flags(visits, "clean", kind=GapType.MISSED_QUESTION)
    write_fake_run("fake", "dev", runs_root=tmp_path)
    with pytest.raises(InputError, match="already exists"):
        write_fake_run("fake", "dev", runs_root=tmp_path)


@pytest.mark.parametrize("kind", list(GapType))
def test_wrong_type_mutation_for_every_original_type(kind):
    visits = load_dataset(ROOT / "data/eval", "dev")
    flags = generate_flags(visits, "wrong-type", 1, kind)
    result = aggregate([(v.key, flags[v.key.visit_id]) for v in visits])
    assert result.overall.fp == result.overall.fn == 1
    assert result.per_type[kind].fn == 1


def test_fake_run_files_are_reproducible(tmp_path):
    first = write_fake_run("fake", "dev", "duplicates", runs_root=tmp_path / "first")
    second = write_fake_run("fake", "dev", "duplicates", runs_root=tmp_path / "second")
    for path in first.rglob("*.json"):
        assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()


@pytest.mark.parametrize("corruption,expected", [
    ("json", "Expecting"), ("shape", "evidence"), ("object", "valid list"),
    ("missing", "missing flags file"), ("visit", "wrong visit_id"), ("extra", "unexpected visit"),
])
def test_bad_flags_report_file_and_write_no_results(run, capsys, corruption, expected):
    directory = run / "runs/oracle/flags"
    path = directory / "eval-dev-03.json"
    if corruption == "json":
        path.write_text("{")
    elif corruption == "shape":
        data = json.loads(path.read_text())
        data[0]["evidence"] = []
        path.write_text(json.dumps(data))
    elif corruption == "object":
        path.write_text("{}")
    elif corruption == "missing":
        path.unlink()
    elif corruption == "visit":
        data = json.loads(path.read_text())
        data[0]["visit_id"] = "wrong"
        path.write_text(json.dumps(data))
    else:
        path = directory / "unknown.json"
        path.write_text("[]")
    code = main(["--run", "oracle", "--split", "dev", "--runs-root", str(run / "runs"),
                 "--results-root", str(run / "results")])
    assert code == 2
    error = capsys.readouterr().err
    assert str(path) in error and expected in error
    assert not (run / "results").exists()


def test_metadata_mismatch_and_run_path_escape(run):
    path = run / "runs/oracle/run_meta.json"
    meta = json.loads(path.read_text())
    meta["split"] = "test"
    path.write_text(json.dumps(meta))
    with pytest.raises(InputError, match="run_id and split"):
        evaluate(run)
    with pytest.raises(InputError, match="single name"):
        evaluate(run, "../escape")


def test_empty_flag_lists_are_valid_and_csv_nulls_are_blank(run):
    for path in (run / "runs/oracle/flags").glob("*.json"):
        path.write_text("[]")
    result = evaluate(run)
    assert result["overall"]["precision"] is None
    assert result["overall"]["recall"] == 0.0
    assert result["overall"]["fp"] == result["overall"]["tp"] == 0
    rows = list(csv.DictReader((run / "results/oracle.csv").open()))
    assert all(row["precision"] == row["precision_ci95_lower"] == row["precision_ci95_upper"] == "" for row in rows)


def test_baseline_uses_same_verified_only_policy(run):
    meta_path = run / "runs/oracle/run_meta.json"
    meta = json.loads(meta_path.read_text())
    meta["system"] = "baseline"
    meta_path.write_text(json.dumps(meta))
    path = run / "runs/oracle/flags/eval-dev-03.json"
    flags = json.loads(path.read_text())
    flags[0]["verified"] = False
    path.write_text(json.dumps(flags))
    result = evaluate(run)
    assert result["system"] == "baseline"
    assert result["extras"]["excluded_unverified"]["total"] == 1
    assert result["overall"]["fn"] == 1


def test_missing_dataset_fails_explicitly(tmp_path):
    with pytest.raises(InputError, match="no answer-key"):
        load_dataset(tmp_path, "dev")


def test_multiple_invalid_flag_files_reported_together(run):
    directory = run / "runs/oracle/flags"
    for name in ("eval-dev-01.json", "eval-dev-02.json"):
        (directory / name).write_text("null")
    with pytest.raises(InputError) as error:
        evaluate(run)
    assert "eval-dev-01.json" in str(error.value) and "eval-dev-02.json" in str(error.value)

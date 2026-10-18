"""Evidence exports and reporting must preserve saved data without rescoring."""
import csv
import json
from pathlib import Path

import pytest

from eval.fake_runs import write_fake_run
from eval.io import ROOT, InputError, load_dataset
from eval.report import make_results_table
from eval.run_eval import evaluate_run
from scripts.make_results_table import main
from src.schemas import GapType


def run_fixture(tmp_path, scenario="oracle", kind=None):
    write_fake_run("fake", "dev", scenario, kind=kind, runs_root=tmp_path / "runs")
    return evaluate_run("fake", "dev", runs_root=tmp_path / "runs", results_root=tmp_path / "results")


def error_rows(tmp_path):
    with (tmp_path / "results/fake_errors.csv").open(newline="") as source:
        return list(csv.DictReader(source))


def test_oracle_errors_csv_has_header_only(tmp_path):
    run_fixture(tmp_path)
    assert error_rows(tmp_path) == []
    assert "reason_code" in (tmp_path / "results/fake_errors.csv").read_text()


@pytest.mark.parametrize("kind", list(GapType))
def test_fn_rows_contain_correct_ground_truth_evidence(tmp_path, kind):
    result = run_fixture(tmp_path, "drop", kind)
    rows = error_rows(tmp_path)
    assert len(rows) == result["overall"]["fn"] == 1
    row = rows[0]
    assert row["outcome"] == "FN" and row["type"] == kind.value
    assert row["flag_id"] == row["flag_index"] == ""
    visit = next(v for v in load_dataset(ROOT / "data/eval", "dev") if v.key.visit_id == row["visit_id"])
    gap = visit.key.planted_gaps[int(row["gap_index"])]
    assert gap.gap_id == row["gap_id"]
    assert json.loads(row["turn_indices"]) == gap.turn_indices
    evidence = json.loads(row["evidence"])
    if kind == GapType.MISSED_QUESTION:
        assert row["index_space"] == "base_transcript"
        assert evidence == [dict(source="checklist", ref=gap.checklist_item_id, quote=None)]
    else:
        assert row["index_space"] == "final_transcript"
        for pointer in evidence:
            if pointer["source"] == "transcript":
                assert pointer["quote"] == visit.transcript.turn(int(pointer["ref"])).text
            else:
                assert pointer["quote"] == visit.chart.entry(pointer["ref"]).display


def test_fp_csv_preserves_emitted_quotes_and_duplicate_reasons(tmp_path):
    write_fake_run("fake", "dev", "duplicates", runs_root=tmp_path / "runs")
    path = tmp_path / "runs/fake/flags/eval-dev-03.json"
    flags = json.loads(path.read_text())
    emitted_quote = 'Literal "quote", comma, and\nsecond line <PERSON>.'
    flags[-1]["evidence"].append(dict(source="transcript", ref="1", quote=emitted_quote))
    flags[-1]["dismissed"] = True
    path.write_text(json.dumps(flags))
    result = evaluate_run("fake", "dev", runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    rows = error_rows(tmp_path)
    assert len(rows) == result["overall"]["fp"] == 1
    row = rows[0]
    assert row["reason_code"] == "duplicate" and row["outcome"] == "FP"
    assert row["flag_index"] == "1" and row["dismissed"] == "True"
    assert row["gap_id"] == "" and "gap[0]" in row["reason"]
    assert json.loads(row["evidence"])[-1]["quote"] == emitted_quote
    first = (tmp_path / "results/fake_errors.csv").read_bytes()
    evaluate_run("fake", "dev", runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    assert first == (tmp_path / "results/fake_errors.csv").read_bytes()


def test_unverified_matching_flag_is_fn_not_fp(tmp_path):
    run_fixture(tmp_path)
    path = tmp_path / "runs/fake/flags/eval-dev-03.json"
    flags = json.loads(path.read_text())
    flags[0]["verified"] = False
    path.write_text(json.dumps(flags))
    evaluate_run("fake", "dev", runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    assert [row["outcome"] for row in error_rows(tmp_path)] == ["FN"]


def test_wrong_type_exports_both_fp_and_fn(tmp_path):
    result = run_fixture(tmp_path, "wrong-type")
    rows = error_rows(tmp_path)
    assert len(rows) == result["overall"]["fp"] + result["overall"]["fn"] == 2
    assert [row["outcome"] for row in rows] == ["FP", "FN"]


def test_table_reads_only_result_json_and_preserves_saved_metrics(tmp_path, monkeypatch):
    run_fixture(tmp_path, "drop", GapType.MISSED_QUESTION)
    results = tmp_path / "results"
    path = results / "fake.json"
    saved = json.loads(path.read_text())
    # Sentinel values prove that the renderer does not reconstruct rates/counts.
    saved["per_type"]["missed_question"]["precision"] = 0.123
    saved["extras"]["per_type"]["missed_question"]["n_predictions"] = 987
    saved["extras"]["per_type"]["missed_question"]["precision_ci95"] = {"lower": 0.01, "upper": 0.45}
    path.write_text(json.dumps(saved))
    original = Path.read_text
    reads = []
    def restricted_read(file, *args, **kwargs):
        assert file.parent == results and file.suffix == ".json"
        reads.append(file)
        return original(file, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", restricted_read)
    output = make_results_table(results)
    assert reads == [path]
    assert "12.3%" in output and "987" in output and "1.0%–45.0%" in output
    assert "FAKE: harness check only" in output and "Source: fake.json" in output
    assert "| overall |" in output
    assert len([line for line in output.splitlines() if line.startswith("| ")]) == len(GapType) + 2


def test_table_nulls_and_metadata_escaping(tmp_path):
    write_fake_run("fake", "dev", runs_root=tmp_path / "runs")
    for path in (tmp_path / "runs/fake/flags").glob("*.json"):
        path.write_text("[]")
    meta_path = tmp_path / "runs/fake/run_meta.json"
    meta = json.loads(meta_path.read_text())
    meta["model"] = "FAKE/a|b\n<test>"
    meta_path.write_text(json.dumps(meta))
    evaluate_run("fake", "dev", runs_root=tmp_path / "runs", results_root=tmp_path / "results")
    output = make_results_table(tmp_path / "results")
    assert "a\\|b &lt;test&gt;" in output
    assert "—" in output and "None" not in output and "nan%" not in output


@pytest.mark.parametrize("bad", ["extras", "interval", "type"])
def test_table_rejects_incomplete_results_without_partial_output(tmp_path, capsys, bad):
    run_fixture(tmp_path)
    path = tmp_path / "results/fake.json"
    saved = json.loads(path.read_text())
    if bad == "extras":
        saved.pop("extras")
    elif bad == "interval":
        saved["extras"]["overall"]["recall_ci95"] = {"lower": 0.9, "upper": 0.1}
    else:
        saved["per_type"].pop("comprehension_breakdown")
    path.write_text(json.dumps(saved))
    assert main(["--results-root", str(tmp_path / "results")]) == 2
    output = capsys.readouterr()
    assert not output.out and str(path) in output.err


def test_table_empty_and_unknown_run_are_clear_errors(tmp_path):
    with pytest.raises(InputError, match="no matching"):
        make_results_table(tmp_path)
    run_fixture(tmp_path)
    with pytest.raises(InputError, match="no matching"):
        make_results_table(tmp_path / "results", "absent")


def test_table_selects_run_without_reading_other_files(tmp_path, capsys):
    run_fixture(tmp_path)
    (tmp_path / "results/unrelated.json").write_text("not JSON")
    assert main(["--results-root", str(tmp_path / "results"), "--run", "fake"]) == 0
    assert "fake" in capsys.readouterr().out

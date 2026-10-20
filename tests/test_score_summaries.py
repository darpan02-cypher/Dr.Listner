import json

from scripts.score_summaries import score


class FakeLLM:
    def __init__(self, yes_words):
        self.yes = yes_words

    def generate(self, prompt, schema, system=None):
        item = prompt.split("Plan item:")[1].split("\n")[0].lower()
        return schema(covered=any(w in prompt.split("Plan item:")[0].lower() for w in self.yes if w in item), reason="x")


def test_score_writes_fields(tmp_path):
    from eval.io import load_dataset
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    v = load_dataset(root / "data/eval", "dev")[0]
    runs, res = tmp_path / "runs", tmp_path / "results"
    (runs / "r" / "summaries").mkdir(parents=True)
    res.mkdir()
    (runs / "r" / "summaries" / f"{v.key.visit_id}.json").write_text(json.dumps({"text": "You should come back in one week. Stay well."}))
    (res / "r.json").write_text(json.dumps({"run_id": "r"}))
    out = score("r", "dev", FakeLLM(["week"]), runs, res, root / "data/eval")
    assert out["n_summaries"] == 1 and out["plan_items"] >= 1
    assert out["mean_reading_grade"] is not None
    d = json.loads((res / "r.json").read_text())
    assert d["plan_coverage"] == out["plan_coverage"]
    assert len(out["missing_summaries"]) == 8

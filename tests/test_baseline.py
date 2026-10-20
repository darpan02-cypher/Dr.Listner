from pathlib import Path

from eval.io import load_dataset
from scripts.run_baseline import Missing, Note, run_visit

ROOT = Path(__file__).resolve().parent.parent


class Fake:
    def generate(self, prompt, schema, system=None):
        if schema is Note:
            return Note(note="n")
        return Missing.model_validate({"items": [
            {"type": "missed_question", "description": "d", "topic_id": "radiation"},
            {"type": "unanswered_concern", "description": "d", "turn": 3},
            {"type": "chart_contradiction", "description": "d", "turn": 3, "chart_entry_id": "nope"},
            {"type": "unanswered_concern", "description": "d", "turn": 999},
        ]})


def test_baseline_flags_are_valid_and_bad_items_dropped():
    v = load_dataset(ROOT / "data/eval", "dev")[0]
    flags = run_visit(Fake(), v, "radiation (x)")
    assert [f.type.value for f in flags] == ["missed_question", "unanswered_concern"]
    assert all(f.verified for f in flags)

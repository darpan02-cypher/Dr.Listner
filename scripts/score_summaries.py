"""Score saved patient summaries: mean reading grade and plan-item coverage.

Reads eval/runs/<run>/summaries/<visit>.json (written by scripts.export_run --summaries) and the answer keys,
then writes mean_reading_grade and plan_coverage into eval/results/<run>.json (which must already exist).
Plan coverage uses one yes/no LLM check per plan item (cached); a failed check is reported as unknown, never as covered.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from eval.io import load_dataset
from src.agents.summary import reading_grade
from src.llm.client import LLMClient, LLMError

ROOT = Path(__file__).resolve().parent.parent
SYSTEM = "You check whether a patient handout contains a specific instruction. Answer only from the handout text."


class Covered(BaseModel):
    covered: bool
    reason: str


def covers(llm, summary: str, item_text: str) -> bool:
    prompt = (
        f"Handout:\n{summary}\n\nPlan item: {item_text}\n\n"
        "Does the handout clearly tell the patient this plan item (same meaning, any wording)? "
        'Reply as JSON: {"covered": true|false, "reason": "short"}.'
    )
    return llm.generate(prompt, Covered, SYSTEM).covered


def score(run: str, split: str, llm, runs_root: Path = ROOT / "eval/runs", results_root: Path = ROOT / "eval/results",
          data_root: Path = ROOT / "data/eval") -> dict:
    sums = runs_root / run / "summaries"
    grades, covered, total, unknown, missing, detail = [], 0, 0, 0, [], {}
    for v in load_dataset(data_root, split):
        vid = v.key.visit_id
        f = sums / f"{vid}.json"
        if not f.exists():
            missing.append(vid)
            continue
        text = json.loads(f.read_text())["text"]
        grades.append(reading_grade(text))
        detail[vid] = {}
        for p in v.key.plan_items:
            total += 1
            try:
                ok = covers(llm, text, p.text)
            except LLMError:
                unknown += 1
                detail[vid][p.item_id] = None
                continue
            covered += ok
            detail[vid][p.item_id] = ok
    out = {
        "n_summaries": len(grades), "missing_summaries": missing,
        "mean_reading_grade": round(sum(grades) / len(grades), 2) if grades else None,
        "max_reading_grade": round(max(grades), 2) if grades else None,
        "plan_items": total, "plan_items_covered": covered, "plan_items_unknown": unknown,
        "plan_coverage": round(covered / total, 4) if total else None, "per_item": detail,
    }
    res = results_root / f"{run}.json"
    if not res.exists():
        raise SystemExit(f"{res} not found; run scripts.run_eval for {run} first")
    d = json.loads(res.read_text())
    d["mean_reading_grade"], d["plan_coverage"] = out["mean_reading_grade"], out["plan_coverage"]
    d.setdefault("extras", {})["summary_scoring"] = out
    res.write_text(json.dumps(d, indent=2))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    a = ap.parse_args(argv)
    out = score(a.run, a.split, LLMClient(max_retries=8))
    print(json.dumps({k: v for k, v in out.items() if k != "per_item"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

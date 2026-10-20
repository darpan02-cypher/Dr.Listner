"""Run the engine over a split and write a run directory for `scripts.run_eval`.

  python -m scripts.export_run --run dev-v1 --split dev [--summaries] [--visits eval-dev-01 ...]

Layout: eval/runs/<run>/{run_meta.json, flags/<visit>.json, summaries/<visit>.json, errors.json}.
Resumable: a visit whose flags file exists is skipped. A visit with ANY failed model call is NOT written
(so it cannot be mistaken for a clean visit); rerun and the LLM cache makes the finished calls free.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.io import InputError, load_dataset, safe_run_id
from src import config, pack
from src.agents.summary import SummaryAgent
from src.engine import EngineContext, new_state, run_batch
from src.llm.client import LLMClient, LLMError

ROOT = config.ROOT


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def export(run: str, split: str, summaries: bool = False, only: list[str] | None = None,
           data_root: Path = ROOT / "data/eval", runs_root: Path = ROOT / "eval/runs", llm=None) -> dict:
    safe_run_id(run)
    visits = load_dataset(data_root, split)
    if only:
        unknown = set(only) - {v.key.visit_id for v in visits}
        if unknown:
            raise InputError(f"unknown visits: {sorted(unknown)}")
        visits = [v for v in visits if v.key.visit_id in only]
    llm = llm or LLMClient(max_retries=8)  # Groq free tier is 8k tokens/min; ride out 429 windows
    profiles, checklist = pack.load_profiles(), pack.load_checklist()
    out = runs_root / run
    _write(out / "run_meta.json", {
        "run_id": run, "system": "drlistner", "mode": llm.mode.value, "split": split,
        "model": getattr(llm, "groq_model", "unknown") if "groq" in getattr(llm, "providers", ()) else "see providers",
    })
    done, failed = [], {}
    for v in visits:
        vid = v.key.visit_id
        if (out / "flags" / f"{vid}.json").exists():
            done.append(vid)
            continue
        ctx = EngineContext(llm=llm, chart=v.chart, checklist=checklist)
        try:
            state = run_batch(new_state(vid, profiles[v.key.profile_id]), v.transcript.turns, ctx)
            summary = None
            if summaries and not state.errors:
                summary = SummaryAgent(llm).run(v.transcript, state.flags, v.key.plan_items, state.profile)
        except LLMError as e:  # e.g. cache miss in DEMO or summary outage
            state, summary = None, None
            failed[vid] = [f"{type(e).__name__}: {e}"]
        if state is not None and state.errors:
            failed[vid] = state.errors
        if vid in failed:
            print(f"SKIP {vid}: {failed[vid]}", file=sys.stderr)
            continue
        _write(out / "flags" / f"{vid}.json", [f.model_dump(mode="json") for f in state.flags])
        if summary is not None:
            _write(out / "summaries" / f"{vid}.json", summary.model_dump(mode="json"))
        done.append(vid)
        print(f"ok {vid}: {len(state.flags)} flags")
    _write(out / "errors.json", failed)
    return {"done": done, "failed": failed}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--split", required=True, choices=["dev", "test"])
    p.add_argument("--summaries", action="store_true")
    p.add_argument("--visits", nargs="*")
    a = p.parse_args(argv)
    try:
        r = export(a.run, a.split, a.summaries, a.visits)
    except InputError as e:
        print(e, file=sys.stderr)
        return 2
    print(f"done {len(r['done'])}, failed {len(r['failed'])}")
    return 1 if r["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

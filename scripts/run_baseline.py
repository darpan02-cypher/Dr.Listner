"""Baseline: a plain scribe-style LLM, no checklist agent, chart agent, concern agent, comprehension agent or verifier.

  python -m scripts.run_baseline --run base-dev --split dev

Step 1 the model writes a scribe-style visit note. Step 2 one prompt lists anything missing, with a type per item.
Output goes to eval/runs/<run>/ in the same layout as scripts.export_run, so scripts.run_eval scores it with the
same matcher. Caveats: the matcher needs a checklist id for missed questions, so the model may only pick the
CLOSEST topic from the id list for those; flags are marked verified because no verifier exists in this system.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Literal

from pydantic import BaseModel

from eval.io import InputError, load_dataset, safe_run_id
from scripts.export_run import ROOT, _write
from src import pack
from src.agents.common import fmt_turns
from src.llm.client import LLMClient, LLMError
from src.schemas import Flag

SYSTEM = "You are a careful medical scribe reviewing a visit transcript. Use only the text given."


class Note(BaseModel):
    note: str


class Item(BaseModel):
    type: Literal["missed_question", "unanswered_concern", "chart_contradiction", "comprehension_breakdown"]
    description: str
    turn: int | None = None  # transcript turn idx for concern / contradiction / comprehension
    quote: str | None = None  # verbatim text from that turn
    topic_id: str | None = None  # closest topic id, only for missed_question
    chart_entry_id: str | None = None  # only for chart_contradiction


class Missing(BaseModel):
    items: list[Item]


def run_visit(llm, v, topics: str) -> list[Flag]:
    t = fmt_turns(v.transcript.turns)
    chart = "\n".join(f"- [{e.entry_id}] {e.display} ({e.status})" for e in v.chart.entries)
    note = llm.generate(f"Write a short clinical visit note from this transcript.\n\n{t}", Note, SYSTEM).note
    out = llm.generate(
        f"Transcript (turn numbers in brackets):\n{t}\n\nChart:\n{chart}\n\nVisit note:\n{note}\n\n"
        "List anything missing or wrong with this visit: (1) missed_question: an important chest-pain history question "
        f"that was never asked; set topic_id to the closest of: {topics}. (2) unanswered_concern: a worry the patient voiced "
        "that the clinician never answered; give turn and quote. (3) chart_contradiction: the patient said something that "
        "conflicts with the chart; give turn, quote and chart_entry_id. (4) comprehension_breakdown: the patient did not "
        "hear or understand and nobody repaired it; give turn and quote. Return an empty list if nothing is missing.",
        Missing, SYSTEM,
    )
    flags = []
    for i, it in enumerate(out.items):
        ev = []
        if it.type == "missed_question" and it.topic_id:
            ev.append({"source": "checklist", "ref": it.topic_id})
        if it.type != "missed_question" and it.turn is not None and 0 <= it.turn < len(v.transcript.turns):
            ev.append({"source": "transcript", "ref": str(it.turn), "quote": v.transcript.turns[it.turn].text})
        if it.type == "chart_contradiction":
            e = v.chart.entry(it.chart_entry_id or "")
            if e:
                ev.append({"source": "chart", "ref": e.entry_id, "quote": e.display})
        try:
            flags.append(Flag.model_validate({
                "flag_id": f"{v.key.visit_id}-base-{i}", "visit_id": v.key.visit_id, "type": it.type,
                "evidence": ev, "rationale": it.description or "baseline", "verified": True,
                "raised_at_turn": len(v.transcript.turns) - 1,
            }))
        except ValueError:
            continue  # malformed baseline item: dropped, counted in errors.json
    return flags


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--split", required=True, choices=["dev", "test"])
    a = ap.parse_args(argv)
    try:
        safe_run_id(a.run)
        visits = load_dataset(ROOT / "data/eval", a.split)
    except InputError as e:
        print(e, file=sys.stderr)
        return 2
    llm = LLMClient(max_retries=8)
    topics = ", ".join(f"{i.id} ({i.label})" for i in pack.load_checklist().items)
    out = ROOT / "eval/runs" / a.run
    _write(out / "run_meta.json", {"run_id": a.run, "system": "baseline", "mode": llm.mode.value, "split": a.split,
                                   "model": llm.groq_model if "groq" in llm.providers else "see providers"})
    failed = {}
    for v in visits:
        vid = v.key.visit_id
        if (out / "flags" / f"{vid}.json").exists():
            continue
        try:
            flags = run_visit(llm, v, topics)
        except LLMError as e:
            failed[vid] = [f"{type(e).__name__}: {e}"]
            print(f"SKIP {vid}: {e}", file=sys.stderr)
            continue
        _write(out / "flags" / f"{vid}.json", [f.model_dump(mode="json") for f in flags])
        print(f"ok {vid}: {len(flags)} flags")
    _write(out / "errors.json", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

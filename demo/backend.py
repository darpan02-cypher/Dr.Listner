"""Backends for the live demo. Both expose the same small interface used by app.py.

ScriptedBackend: hardcoded. Each spoken line is matched to the prepared script by text similarity; flags and
checklist ticks come from demo/flags.json. Safe on stage (no network), but it only reacts to scripted lines.
EngineBackend: the real engine (process_turn / finalize / SummaryAgent) on a DEMO (cache) or LIVE LLM client.
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path

from src.schemas import Chart, Checklist, Flag, GapType, PatientProfile, PlanItem, Turn

DEMO_DIR = Path(__file__).resolve().parent
MATCH_MIN = 0.6


def load_script() -> dict:
    return json.loads((DEMO_DIR / "script.json").read_text())


def load_chart() -> Chart:
    return Chart.model_validate(json.loads((DEMO_DIR / "chart.json").read_text()))


def load_flag_plan() -> dict:
    return json.loads((DEMO_DIR / "flags.json").read_text())


@dataclass
class Backend:
    visit_id: str
    chart: Chart
    checklist: Checklist
    profile: PatientProfile
    turns: list[Turn] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    coverage: dict[str, int | None] = field(default_factory=dict)
    off_script: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ended: bool = False
    summary: str = ""
    summary_grade: float | None = None
    clarify: list[str] = field(default_factory=list)

    def add_turn(self, speaker: str, text: str) -> Turn:  # pragma: no cover - interface
        raise NotImplementedError

    def end_visit(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def dismiss(self, flag_id: str) -> None:
        self.flags = [f.model_copy(update={"dismissed": True}) if f.flag_id == flag_id else f for f in self.flags]


class ScriptedBackend(Backend):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.script = load_script()["turns"]
        self.plan = load_flag_plan()
        self.pointer = 0  # next script turn we expect
        self.matched: dict[int, int] = {}  # script idx -> session idx

    def _match(self, speaker: str, text: str) -> int | None:
        best, best_r = None, 0.0
        for s in self.script[self.pointer : self.pointer + 6]:
            if s["speaker"] != speaker:
                continue
            r = difflib.SequenceMatcher(None, s["text"].lower(), text.lower()).ratio()
            if r > best_r:
                best, best_r = s["idx"], r
        return best if best_r >= MATCH_MIN else None

    def add_turn(self, speaker: str, text: str) -> Turn:
        turn = Turn(idx=len(self.turns), speaker=speaker, text=text.strip())
        self.turns.append(turn)
        sidx = self._match(speaker, text)
        if sidx is None:
            self.off_script.append(turn.idx)
            return turn
        self.pointer = sidx + 1
        self.matched[sidx] = turn.idx
        for item, at in self.plan["coverage"].items():
            if at == sidx:
                self.coverage[item] = turn.idx
        for i, f in enumerate(self.plan["flags"]):
            if f["trigger_turn"] is not None and f["trigger_turn"] <= sidx and not self._has(i):
                self._emit(i, turn.idx)
        return turn

    def _has(self, i: int) -> bool:
        return any(f.flag_id == f"demo-flag-{i}" for f in self.flags)

    def _emit(self, i: int, at: int) -> None:
        f = self.plan["flags"][i]
        ev = []
        for e in f["evidence"]:
            e = dict(e)
            if e["source"] == "transcript":
                e["ref"] = str(self.matched.get(int(e["ref"]), int(e["ref"])))
            ev.append(e)
        self.flags.append(
            Flag.model_validate(
                {"flag_id": f"demo-flag-{i}", "visit_id": self.visit_id, "type": f["type"], "evidence": ev,
                 "rationale": f["rationale"], "verified": True, "raised_at_turn": at}
            )
        )

    def end_visit(self) -> None:
        last = max(len(self.turns) - 1, 0)
        for i, f in enumerate(self.plan["flags"]):
            if f["trigger_turn"] is None and not self._has(i):
                # a flag that cites a script turn is only shown if that turn was actually spoken
                refs = [int(e["ref"]) for e in f["evidence"] if e["source"] == "transcript"]
                if all(r in self.matched for r in refs):
                    self._emit(i, last)
        self.clarify = list(self.plan["clarify"])
        self.summary = self.plan["summary"]
        self.ended = True
        self._grade()

    def _grade(self) -> None:
        try:
            from src.agents.summary import reading_grade

            self.summary_grade = round(reading_grade(self.summary), 2)
        except Exception:  # textstat missing
            self.summary_grade = None


class EngineBackend(Backend):
    """Real engine. DEMO mode only works for texts already in data/llm_cache or demo/cache."""

    def __init__(self, *a, llm=None, plan_items: list[PlanItem] | None = None, **kw):
        super().__init__(*a, **kw)
        from src import engine

        self.engine = engine
        self.llm = llm
        self.plan_items = plan_items or []
        self.state = engine.new_state(self.visit_id, self.profile)
        self.ctx = engine.EngineContext(llm=llm, chart=self.chart, checklist=self.checklist)

    def _sync(self) -> None:
        self.turns = list(self.state.turns_seen)
        self.flags = [f for f in self.state.flags if f.verified]
        self.coverage = dict(self.state.checklist_coverage)
        self.errors = list(self.state.errors)

    def add_turn(self, speaker: str, text: str) -> Turn:
        turn = Turn(idx=len(self.state.turns_seen), speaker=speaker, text=text.strip())
        self.state = self.engine.process_turn(self.state, turn, self.ctx)
        self._sync()
        return turn

    def end_visit(self) -> None:
        from src.agents.summary import SummaryAgent
        from src.schemas import Transcript

        self.state = self.engine.finalize(self.state, self.ctx)
        self._sync()
        tr = Transcript(visit_id=self.visit_id, chart_id=self.chart.chart_id, turns=self.state.turns_seen)
        try:
            res = SummaryAgent(self.llm).run(tr, self.flags, self.plan_items, self.profile)
            self.summary, self.summary_grade = res.text, res.grade
        except Exception as e:  # LLMError or missing textstat: show, do not crash the demo
            self.errors.append(f"summary: {type(e).__name__}")
        self.clarify = [f.rationale for f in self.flags if not f.dismissed][:3]
        self.ended = True

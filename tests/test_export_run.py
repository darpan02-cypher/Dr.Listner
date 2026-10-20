import json
from src import config
from scripts.export_run import export
from tests.fakes import FakeLLM
from tests.test_engine_agents import _llm
from src.agents.chart_agent import ChartOut


class Fake(FakeLLM):
    mode = config.Mode.DEMO
    providers = ()


def _fake():
    f = Fake(**{k: v for k, v in _llm().by.items()})
    f.by["ChartOut"] = ChartOut(conflicts=[])  # reusable, not a queue
    f.by["Verdict"] = _llm().by["Verdict"]
    return f


def test_export_writes_scorable_layout_and_is_resumable(tmp_path):
    runs = tmp_path / "runs"
    r = export("t1", "dev", only=["eval-dev-01"], runs_root=runs, llm=_fake())
    assert r["done"] == ["eval-dev-01"] and not r["failed"]
    meta = json.loads((runs / "t1/run_meta.json").read_text())
    assert meta["system"] == "drlistner" and meta["split"] == "dev"
    flags = json.loads((runs / "t1/flags/eval-dev-01.json").read_text())
    assert isinstance(flags, list)
    again = export("t1", "dev", only=["eval-dev-01"], runs_root=runs, llm=Fake())  # would KeyError if it ran
    assert again["done"] == ["eval-dev-01"]


def test_visit_with_model_failure_is_not_written(tmp_path):
    from src.llm.client import DemoCacheMiss

    class Boom(Fake):
        def generate(self, *a, **k):
            raise DemoCacheMiss("miss")

    runs = tmp_path / "runs"
    r = export("t2", "dev", only=["eval-dev-01"], runs_root=runs, llm=Boom())
    assert "eval-dev-01" in r["failed"] and not (runs / "t2/flags/eval-dev-01.json").exists()

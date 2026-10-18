from src import pack
from src.engine import EngineContext, finalize, new_state, process_turn, run_batch
from src.agents.chart_agent import ChartOut, Conflict
from src.agents.checklist import ChecklistOut
from src.agents.comprehension import Breakdown, RepairOut, TeachbackOut
from src.agents.concern import Concern, ConcernOut
from src.agents.verifier import Verdict
from src.schemas import Chart, ChartEntry, GapType, Turn
from tests.fakes import FakeLLM

CHART = Chart(chart_id="c", age=70, sex="male",
              entries=[ChartEntry(entry_id="e1", resource_type="Condition", display="Type 2 diabetes")])
TURNS = [Turn(idx=0, speaker="clinician", text="Any diabetes?"),
         Turn(idx=1, speaker="patient", text="No, none."),
         Turn(idx=2, speaker="clinician", text="Any fainting?"),
         Turn(idx=3, speaker="patient", text="What?"),
         Turn(idx=4, speaker="clinician", text="Next. Take pills daily. Any other questions?"),
         Turn(idx=5, speaker="patient", text="I worry about my job.")]


def _ctx(llm, **kw):
    return EngineContext(llm=llm, chart=CHART, checklist=pack.load_checklist(), scrub=False, **kw)


def _llm():
    return FakeLLM(
        ChartOut=[ChartOut(conflicts=[Conflict(chart_entry_id="e1", turn_quote="No, none.", rationale="Denied; chart lists Type 2 diabetes.")]),
                  ChartOut(conflicts=[]),  # turn 3
                  ChartOut(conflicts=[])],  # turn 5
        RepairOut=RepairOut(breakdowns=[Breakdown(turn_idx=3, quote="What?", cue="repeat")]),
        TeachbackOut=TeachbackOut(gives_instructions=False, teach_back_done=False),
        ChecklistOut=ChecklistOut(items=[]),
        ConcernOut=ConcernOut(concerns=[Concern(turn_idx=5, quote="I worry about my job.", addressed=False)]),
        Verdict=Verdict(supported=True, reason="ok"),
    )


def test_types_3_4_raise_during_visit_and_1_2_only_at_finalize():
    prof = pack.load_profiles()["hoh_lowlit_alone"]
    ctx = _ctx(_llm())
    s = new_state("v", prof)
    for t in TURNS:
        s = process_turn(s, t, ctx)
        assert not any(f.type in (GapType.MISSED_QUESTION, GapType.UNANSWERED_CONCERN) for f in s.flags)
    by_type = {f.type: f for f in s.flags}
    assert by_type[GapType.CHART_CONTRADICTION].raised_at_turn == 1  # passive, immediately
    assert by_type[GapType.COMPREHENSION_BREAKDOWN].raised_at_turn == 4  # next clinician turn
    assert s.wrapped_up  # "Any other questions?" seen
    s = finalize(s, ctx)
    types = [f.type for f in s.flags]
    assert types.count(GapType.UNANSWERED_CONCERN) == 1 and types.count(GapType.MISSED_QUESTION) == 10
    assert all(f.verified for f in s.flags)
    assert s.checklist_coverage and all(v is None for v in s.checklist_coverage.values())
    assert len(types) == len(set(f.flag_id for f in s.flags))  # no duplicates across passes


def test_run_batch_with_ctx_equals_manual_fold_and_inactive_detectors_are_skipped():
    prof = pack.load_profiles()["hoh_lowlit_alone"]
    a = run_batch(new_state("v", prof), TURNS, _ctx(_llm()))
    ctx = _ctx(_llm())
    s = new_state("v", prof)
    for t in TURNS:
        s = process_turn(s, t, ctx)
    assert a == finalize(s, ctx)
    only3 = prof.model_copy(update={"active_detectors": [GapType.CHART_CONTRADICTION]})
    b = run_batch(new_state("v", only3), TURNS, _ctx(_llm()))
    assert {f.type for f in b.flags} == {GapType.CHART_CONTRADICTION}


def test_verifier_drop_removes_flag_but_keeps_candidate():
    prof = pack.load_profiles()["hoh_lowlit_alone"]
    llm = _llm()
    llm.by["Verdict"] = Verdict(supported=False, reason="no")
    ctx = _ctx(llm)
    s = run_batch(new_state("v", prof), TURNS, ctx)
    assert s.flags == [] and len(ctx.candidates) > 0


class _Down:
    """LLM that is unavailable for given schemas."""
    def __init__(self, inner, down):
        self.inner, self.down = inner, set(down)
    def generate(self, prompt, schema, system=None):
        from src.llm.client import LLMUnavailable
        if schema.__name__ in self.down:
            raise LLMUnavailable("down")
        return self.inner.generate(prompt, schema, system)


def test_model_failure_is_recorded_not_raised_and_not_read_as_clean():
    prof = pack.load_profiles()["hoh_lowlit_alone"]
    s = run_batch(new_state("v", prof), TURNS, _ctx(_Down(_llm(), {"ChecklistOut", "ConcernOut"})))
    assert "checklist: LLMUnavailable" in s.errors and "concern: LLMUnavailable" in s.errors
    assert not any(f.type is GapType.MISSED_QUESTION for f in s.flags)
    assert s.checklist_coverage == {}  # unknown, not "all missed"


def test_verifier_outage_keeps_programmatically_valid_flags_unverified():
    prof = pack.load_profiles()["hoh_lowlit_alone"]
    s = run_batch(new_state("v", prof), TURNS, _ctx(_Down(_llm(), {"Verdict"})))
    assert s.flags and not any(f.verified for f in s.flags)
    assert any(e.startswith("verifier") for e in s.errors)

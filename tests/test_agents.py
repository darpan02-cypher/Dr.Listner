import pytest
from src import deid, pack
from src.agents.chart_agent import ChartAgent, ChartOut, Conflict
from src.agents.checklist import ChecklistAgent, ChecklistOut, ItemCoverage
from src.agents.common import has_clinical_advice, norm, quote_in
from src.agents.comprehension import Breakdown, ComprehensionAgent, RepairOut, TeachbackOut
from src.agents.concern import Concern, ConcernAgent, ConcernOut
from src.agents.summary import SummaryAgent, SummaryOut
from src.agents.verifier import Verdict, VerifierAgent, programmatic_ok
from tests.fakes import FakeLLM
from src.schemas import Chart, ChartEntry, EvidencePointer, Flag, GapType, PlanItem, Transcript, Turn


@pytest.fixture
def tr():
    return Transcript(visit_id="v1", chart_id="c1", turns=[
        Turn(idx=0, speaker="clinician", text="Tell me what brought you in."),
        Turn(idx=1, speaker="patient", text="Chest pain since yesterday."),
        Turn(idx=2, speaker="clinician", text="Do you smoke?"),
        Turn(idx=3, speaker="patient", text="No, never.  I worry about my  job."),
        Turn(idx=4, speaker="clinician", text="Okay, take your pills daily."),
    ])


@pytest.fixture
def chart():
    return Chart(chart_id="c1", age=70, sex="male",
                 entries=[ChartEntry(entry_id="e1", resource_type="Condition", display="Type 2 diabetes")])


@pytest.fixture
def checklist():
    return pack.load_checklist()


# ---- helpers ----
def test_quote_in_is_whitespace_normalized_but_exact_otherwise():
    assert quote_in("worry about my job", "I worry about my  job.")
    assert not quote_in("Worry about my job", "I worry about my job")
    assert not quote_in("", "x") and norm(" a \n b ") == "a b"


def test_clinical_advice_lint():
    assert has_clinical_advice("This may be a heart attack")
    assert has_clinical_advice("should start aspirin")
    assert not has_clinical_advice("The patient said no diabetes but the chart lists diabetes.")


# ---- ChecklistAgent ----
def test_checklist_flags_uncovered_and_rejects_bad_citations(tr, checklist):
    ids = [i.id for i in checklist.items]
    cov = [ItemCoverage(item_id=ids[0], covered=True, turn_idx=1, quote="Chest pain since yesterday."),
           ItemCoverage(item_id=ids[1], covered=True, turn_idx=1, quote="invented quote"),  # bad citation
           ItemCoverage(item_id=ids[2], covered=False)]
    flags, coverage = ChecklistAgent(FakeLLM(ChecklistOut=ChecklistOut(items=cov))).run(tr, checklist)
    assert coverage[ids[0]] == 1 and coverage[ids[1]] is None
    flagged = {f.evidence[0].ref for f in flags}
    assert ids[0] not in flagged and ids[1] in flagged and ids[2] in flagged
    assert flagged == set(ids[1:])  # items the model never mentioned count as uncovered
    assert all(f.type is GapType.MISSED_QUESTION and f.raised_at_turn == 4 for f in flags)


# ---- ConcernAgent ----
def test_concern_unaddressed_flagged_addressed_not_and_bad_speaker_dropped(tr):
    out = ConcernOut(concerns=[
        Concern(turn_idx=3, quote="I worry about my job", addressed=False),
        Concern(turn_idx=1, quote="Chest pain", addressed=True, addressed_by=2),
        Concern(turn_idx=4, quote="take your pills", addressed=False),  # clinician turn: dropped
        Concern(turn_idx=3, quote="not in the text", addressed=False),  # bad quote: dropped
    ])
    flags, _ = ConcernAgent(FakeLLM(ConcernOut=out)).run(tr)
    assert [f.evidence[0].ref for f in flags] == ["3"]


def test_concern_addressed_by_earlier_turn_does_not_count(tr):
    out = ConcernOut(concerns=[Concern(turn_idx=3, quote="worry", addressed=True, addressed_by=0)])
    assert len(ConcernAgent(FakeLLM(ConcernOut=out)).run(tr)[0]) == 1


# ---- ChartAgent ----
def test_chart_contradiction_pointers_and_filters(tr, chart):
    t = tr.turns[:4]
    ok = Conflict(chart_entry_id="e1", turn_quote="No, never.", rationale="Patient denies; chart lists Type 2 diabetes.")
    bad = [Conflict(chart_entry_id="zz", turn_quote="No, never.", rationale="x"),
           Conflict(chart_entry_id="e1", turn_quote="made up", rationale="x"),
           Conflict(chart_entry_id="e1", turn_quote="No, never.", rationale="This is probably a heart attack")]
    agent = ChartAgent(FakeLLM(ChartOut=ChartOut(conflicts=[ok, *bad])))
    flags = agent.check_turn("v1", t, 3, chart)
    assert len(flags) == 1
    f = flags[0]
    assert {e.source for e in f.evidence} == {"transcript", "chart"} and f.raised_at_turn == 3
    assert agent.check_turn("v1", t, 2, chart) == []  # clinician turn: never judged


# ---- ComprehensionAgent ----
def test_repair_needs_later_clinician_turn_and_valid_quote():
    turns = [Turn(idx=0, speaker="clinician", text="Any fainting?"),
             Turn(idx=1, speaker="patient", text="What?"),
             Turn(idx=2, speaker="clinician", text="Moving on. Any nausea?")]
    llm = FakeLLM(RepairOut=RepairOut(breakdowns=[Breakdown(turn_idx=1, quote="What?", cue="repeat request")]))
    flags = ComprehensionAgent(llm).check_repair("v", turns)
    assert flags[0].type is GapType.COMPREHENSION_BREAKDOWN and flags[0].evidence[0].ref == "1"
    # no clinician turn after the patient turn -> undecidable -> no flag
    assert ComprehensionAgent(llm).check_repair("v", turns[:2]) == []


def test_teachback_flag_points_at_plan_turn(tr):
    out = TeachbackOut(gives_instructions=True, teach_back_done=False, instruction_turn=4, quote="take your pills daily")
    f = ComprehensionAgent(FakeLLM(TeachbackOut=out)).check_teachback("v1", tr.turns)
    assert [x.evidence[0].ref for x in f] == ["4"]
    for done in (TeachbackOut(gives_instructions=True, teach_back_done=True, instruction_turn=4, quote="take your pills"),
                 TeachbackOut(gives_instructions=False, teach_back_done=False)):
        assert ComprehensionAgent(FakeLLM(TeachbackOut=done)).check_teachback("v1", tr.turns) == []


# ---- VerifierAgent ----
def _flag(**kw):
    base = dict(flag_id="f", visit_id="v1", type=GapType.UNANSWERED_CONCERN, rationale="r",
                evidence=[EvidencePointer(source="transcript", ref="3", quote="worry about my job")])
    return Flag(**{**base, **kw})


def test_programmatic_checks(tr, chart, checklist):
    assert programmatic_ok(_flag(), tr, chart, checklist)
    assert not programmatic_ok(_flag(evidence=[EvidencePointer(source="transcript", ref="3", quote="nope")]), tr, chart, checklist)
    assert not programmatic_ok(_flag(evidence=[EvidencePointer(source="transcript", ref="99", quote="x")]), tr, chart, checklist)
    assert not programmatic_ok(_flag(rationale="This could be a heart attack"), tr, chart, checklist)
    mq = Flag(flag_id="m", visit_id="v1", type=GapType.MISSED_QUESTION, rationale="r",
              evidence=[EvidencePointer(source="checklist", ref=checklist.items[0].id)])
    assert programmatic_ok(mq, tr, chart, checklist)
    mq_bad = mq.model_copy(update={"evidence": [EvidencePointer(source="checklist", ref="nope")]})
    assert not programmatic_ok(mq_bad, tr, chart, checklist)


def test_verifier_sets_verified_only_when_llm_agrees_and_skips_llm_on_programmatic_fail(tr, chart, checklist):
    yes = FakeLLM(Verdict=Verdict(supported=True, reason="ok"))
    out = VerifierAgent(yes).verify(_flag(), tr, chart, checklist)
    assert out is not None and out.verified
    assert VerifierAgent(FakeLLM(Verdict=Verdict(supported=False, reason="no"))).verify(_flag(), tr, chart, checklist) is None
    never = FakeLLM()  # any generate() would KeyError
    bad = _flag(evidence=[EvidencePointer(source="transcript", ref="3", quote="nope")])
    assert VerifierAgent(never).verify(bad, tr, chart, checklist) is None and never.prompts == []


# ---- SummaryAgent ----
def test_summary_loop_stops_when_target_met_and_ships_best(tr):
    prof = pack.load_profiles()["hoh_lowlit_alone"]
    easy = "Take your pills each day. Come back in one week."
    hard = ("Pharmacological adherence necessitates uninterrupted administration of the prescribed "
            "medications, notwithstanding any apprehension regarding concurrent occupational obligations.")
    plan = [PlanItem(item_id="p", text="Come back in one week.")]
    llm = FakeLLM(SummaryOut=[SummaryOut(summary=hard), SummaryOut(summary=easy)])
    r = SummaryAgent(llm).run(tr, [], plan, prof)
    assert r.text == easy and r.iterations == 2 and r.grades[0] > r.grades[1]
    assert "reading grade" in llm.prompts[1]  # score fed back
    llm = FakeLLM(SummaryOut=[SummaryOut(summary=hard)] * 3)
    r = SummaryAgent(llm).run(tr, [], plan, prof)
    assert r.iterations == 3 and r.text == hard  # max 3, best attempt shipped


# ---- deid (real Presidio + spaCy small model) ----
def test_deid_scrubs_identifiers_keeps_clinical_time_and_is_turn_preserving():
    s = deid.scrub("I'm John Smith, call 704-555-1234. The pain began yesterday afternoon.")
    assert "John" not in s and "704" not in s and "<PERSON>" in s
    assert "yesterday afternoon" in s
    t = Transcript(visit_id="v", chart_id="c", turns=[Turn(idx=0, speaker="patient", text="My name is Mary Jones."),
                                                      Turn(idx=1, speaker="clinician", text="Chest pain, okay.")])
    out = deid.scrub_transcript(t)
    assert [x.idx for x in out.turns] == [0, 1] and "Jones" not in out.turns[0].text
    assert out.turns[1].text == "Chest pain, okay." and t.turns[0].text == "My name is Mary Jones."

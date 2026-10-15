import json
import pytest
from pydantic import ValidationError
from src import config
from src.schemas import *


def test_transcript_ok_and_contiguity():
    t = Transcript(visit_id="v1", chart_id="c1", turns=[Turn(idx=0, speaker="clinician", text="Hi"), Turn(idx=1, speaker="patient", text="Hello")])
    assert t.turn(1).speaker == "patient" and t.turn(5) is None
    with pytest.raises(ValidationError):
        Transcript(visit_id="v1", chart_id="c1", turns=[Turn(idx=1, speaker="patient", text="x")])


def test_real_data_flag_rejected():
    with pytest.raises(ValidationError):
        Transcript(visit_id="v", chart_id="c", synthetic=False, turns=[Turn(idx=0, speaker="patient", text="x")])


def test_flag_shapes():
    ck = EvidencePointer(source="checklist", ref="radiation")
    Flag(flag_id="f1", visit_id="v", type=GapType.MISSED_QUESTION, evidence=[ck], rationale="not asked")
    with pytest.raises(ValidationError):  # missing checklist pointer
        Flag(flag_id="f", visit_id="v", type=GapType.MISSED_QUESTION, evidence=[EvidencePointer(source="transcript", ref="1", quote="q")], rationale="r")
    with pytest.raises(ValidationError):  # contradiction needs both sides
        Flag(flag_id="f", visit_id="v", type=GapType.CHART_CONTRADICTION, evidence=[EvidencePointer(source="transcript", ref="1", quote="q")], rationale="r")
    with pytest.raises(ValidationError):  # transcript evidence needs quote
        EvidencePointer(source="transcript", ref="1")
    with pytest.raises(ValidationError):  # non-numeric turn ref
        EvidencePointer(source="transcript", ref="abc", quote="q")


def test_contradiction_flag_ok():
    Flag(flag_id="f", visit_id="v", type=GapType.CHART_CONTRADICTION, rationale="r", evidence=[
        EvidencePointer(source="transcript", ref="3", quote="no heart history"),
        EvidencePointer(source="chart", ref="cond-7", quote="Coronary stent")])


def test_answer_key_rules():
    k = AnswerKey(visit_id="v", split="dev", planted_gaps=[])
    assert k.is_clean
    with pytest.raises(ValidationError):
        PlantedGap(gap_id="g", type=GapType.MISSED_QUESTION, edit_op="delete_turns", turn_indices=[4], description="d")
    with pytest.raises(ValidationError):
        PlantedGap(gap_id="g", type=GapType.UNANSWERED_CONCERN, edit_op="insert_concern", description="d")


def test_eval_result_validates():
    m = TypeMetrics(tp=1, fp=0, fn=1, precision=1.0, recall=0.5, f1=2 / 3)
    r = EvalResult(run_id="r", system="drlistner", split="dev", mode="DEMO", model="m", git_commit="abc", timestamp="2026-10-15T00:00:00Z", n_visits=3, per_type={GapType.MISSED_QUESTION: m}, overall=m, false_flags_per_visit=0.0, n_clean_visits=1, false_flags_on_clean_visits=0)
    assert EvalResult.model_validate_json(r.model_dump_json()) == r


def test_checklist_file_every_item_cited_or_unverified():
    ck = Checklist.model_validate(json.loads(config.CHECKLIST_PATH.read_text()))
    assert len(ck.items) == 8
    for it in ck.items:
        assert it.verification_status == "UNVERIFIED" or it.guideline_ref


def test_verified_requires_ref():
    with pytest.raises(ValidationError):
        ChecklistItem(id="x", label="l", description="d", example_questions=["q"], verification_status="VERIFIED", verification_note="n")

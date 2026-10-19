"""Hand-computable matcher cases; no model calls or test-split tuning."""
from dataclasses import asdict
import json

import pytest

from eval.match import match_visit
from src.schemas import AnswerKey, Chart, ChartEntry, EvidencePointer, Flag, GapType, PlantedGap, Transcript, Turn


@pytest.fixture
def visit():
    transcript = Transcript(visit_id="fixture", chart_id="chart", turns=[
        Turn(idx=0, speaker="clinician", text="How can I help today?"),
        Turn(idx=1, speaker="patient", text="I am worried about reading the visit summary."),
        Turn(idx=2, speaker="clinician", text="Have you had a heart procedure?"),
        Turn(idx=3, speaker="patient", text="I have never had a stent."),
        Turn(idx=4, speaker="clinician", text="When did the discomfort start?"),
        Turn(idx=5, speaker="patient", text="Could you repeat that?"),
        Turn(idx=6, speaker="clinician", text="Bring your medicine list to your next visit."),
        Turn(idx=7, speaker="patient", text="Okay."),
        Turn(idx=8, speaker="clinician", text="Goodbye."),
    ])
    chart = Chart(chart_id="chart", age=70, sex="female", entries=[
        ChartEntry(entry_id="stent", resource_type="Procedure", display="Coronary stent placement"),
        ChartEntry(entry_id="other", resource_type="Condition", display="High blood pressure"),
    ])
    return transcript, chart


def gap(gap_id, kind, turns=(), *, item=None, entry=None, edit=None):
    default_edit = {
        GapType.MISSED_QUESTION: "delete_turns",
        GapType.UNANSWERED_CONCERN: "insert_concern",
        GapType.CHART_CONTRADICTION: "insert_contradiction",
        GapType.COMPREHENSION_BREAKDOWN: "insert_mishearing",
    }[kind]
    return PlantedGap(gap_id=gap_id, type=kind, edit_op=edit or default_edit,
                      turn_indices=list(turns), checklist_item_id=item,
                      chart_entry_id=entry, description="Synthetic test edit.")


def key(*gaps):
    return AnswerKey(visit_id="fixture", split="dev", wrap_up_turn=6, planted_gaps=list(gaps))


def flag(visit, flag_id, kind, *, turns=(), item=None, entry=None, **fields):
    """Schema-valid fake flags with quotes copied from the fixture sources."""
    transcript, chart = visit
    evidence = [EvidencePointer(source="transcript", ref=str(i), quote=transcript.turn(i).text) for i in turns]
    if item is not None:
        evidence.append(EvidencePointer(source="checklist", ref=item))
    if entry is not None:
        evidence.append(EvidencePointer(source="chart", ref=entry, quote=chart.entry(entry).display))
    return Flag(flag_id=flag_id, visit_id=transcript.visit_id, type=kind, evidence=evidence,
                rationale="Synthetic documentation gap.", **({"verified": True} | fields))


def counts(result):
    return (sum(f.outcome == "TP" for f in result.flags),
            sum(f.outcome == "FP" for f in result.flags),
            sum(g.outcome == "FN" for g in result.gaps))


def test_oracle_covers_all_types_and_both_comprehension_edits(visit):
    answer = key(
        gap("missing", GapType.MISSED_QUESTION, [20, 21], item="radiation"),
        gap("concern", GapType.UNANSWERED_CONCERN, [1]),
        gap("contradiction", GapType.CHART_CONTRADICTION, [3], entry="stent"),
        gap("mishearing", GapType.COMPREHENSION_BREAKDOWN, [5]),
        gap("teachback", GapType.COMPREHENSION_BREAKDOWN, [6], edit="delete_teachback"),
    )
    flags = [
        flag(visit, "a", GapType.MISSED_QUESTION, item="radiation"),
        flag(visit, "b", GapType.UNANSWERED_CONCERN, turns=[1]),
        flag(visit, "c", GapType.CHART_CONTRADICTION, turns=[3], entry="stent"),
        flag(visit, "d", GapType.COMPREHENSION_BREAKDOWN, turns=[5]),
        flag(visit, "e", GapType.COMPREHENSION_BREAKDOWN, turns=[6]),
    ]
    before = ([f.model_dump() for f in flags], answer.model_dump())
    result = match_visit(flags, answer)
    assert counts(result) == (5, 0, 0)
    assert [f.gap_index for f in result.flags] == [0, 1, 2, 3, 4]
    assert [g.flag_index for g in result.gaps] == [0, 1, 2, 3, 4]
    assert [f.gap_id for f in result.flags] == [g.gap_id for g in answer.planted_gaps]
    assert [g.flag_id for g in result.gaps] == [f.flag_id for f in flags]
    assert all(f.reason_code == "matched" and f.reason for f in result.flags)
    assert ([f.model_dump() for f in flags], answer.model_dump()) == before
    assert json.dumps(asdict(result)) == json.dumps(asdict(match_visit(flags, answer)))


def test_drop_two_of_six_missed_questions(visit):
    items = ["nature", "onset", "radiation", "exertional", "relieving", "dyspnea"]
    answer = key(*(gap(item, GapType.MISSED_QUESTION, item=item) for item in items))
    flags = [flag(visit, item, GapType.MISSED_QUESTION, item=item) for item in items[2:]]
    result = match_visit(flags, answer)
    assert counts(result) == (4, 0, 2)
    assert [g.gap_id for g in result.gaps if g.outcome == "FN"] == ["nature", "onset"]
    assert all(g.flag_index is None and g.reason_code == "unmatched_gap" for g in result.gaps[:2])


@pytest.mark.parametrize("clean", [False, True])
def test_extra_flag_and_clean_visit(visit, clean):
    answer = key() if clean else key(gap("missing", GapType.MISSED_QUESTION, item="onset"))
    flags = [] if clean else [flag(visit, "found", GapType.MISSED_QUESTION, item="onset")]
    flags.append(flag(visit, "extra", GapType.MISSED_QUESTION, item="radiation"))
    result = match_visit(flags, answer)
    assert counts(result) == ((0, 1, 0) if clean else (1, 1, 0))
    extra = result.flags[-1]
    assert extra.reason_code == ("clean_visit" if clean else "evidence_mismatch")
    assert extra.gap_index is None and extra.gap_id is None


def test_wrong_type_does_not_match_shared_transcript_reference(visit):
    answer = key(gap("concern", GapType.UNANSWERED_CONCERN, [1]))
    wrong = flag(visit, "wrong", GapType.COMPREHENSION_BREAKDOWN, turns=[1])
    result = match_visit([wrong], answer)
    assert counts(result) == (0, 1, 1)
    assert result.flags[0].reason_code == "no_same_type_gap"


@pytest.mark.parametrize("same_id", [False, True])
def test_duplicate_flags_count_as_fp_even_if_ids_are_identical(visit, same_id):
    answer = key(gap("concern", GapType.UNANSWERED_CONCERN, [1]))
    first = flag(visit, "first", GapType.UNANSWERED_CONCERN, turns=[1])
    second = first.model_copy(update={"flag_id": "first" if same_id else "second"})
    result = match_visit([first, second], answer)
    assert counts(result) == (1, 1, 0)
    assert [f.flag_index for f in result.flags] == [0, 1]
    assert result.flags[1].reason_code == "duplicate"
    assert "gap[0]" in result.flags[1].reason
    assert result.flags[1].gap_index is None
    assert result.gaps[0].flag_index == 0


def test_greedy_file_order_does_not_optimize_assignment(visit):
    answer = key(gap("first", GapType.UNANSWERED_CONCERN, [1]),
                 gap("second", GapType.UNANSWERED_CONCERN, [5]))
    broad = flag(visit, "broad", GapType.UNANSWERED_CONCERN, turns=[5, 1])
    narrow = flag(visit, "narrow", GapType.UNANSWERED_CONCERN, turns=[1])
    result = match_visit([broad, narrow], answer)
    assert counts(result) == (1, 1, 1)
    assert result.flags[0].gap_id == "first"  # gap order wins over evidence order
    assert result.flags[1].reason_code == "duplicate"
    assert result.gaps[1].outcome == "FN"
    assert counts(match_visit([narrow, broad], answer)) == (2, 0, 0)
    reversed_key = key(*reversed(answer.planted_gaps))
    assert counts(match_visit([broad, narrow], reversed_key)) == (2, 0, 0)


def test_broad_flag_skips_already_assigned_gap_for_next_candidate(visit):
    answer = key(gap("first", GapType.UNANSWERED_CONCERN, [1]),
                 gap("second", GapType.UNANSWERED_CONCERN, [5]))
    first = flag(visit, "first", GapType.UNANSWERED_CONCERN, turns=[1])
    broad = flag(visit, "broad", GapType.UNANSWERED_CONCERN, turns=[1, 5])
    result = match_visit([first, broad], answer)
    assert counts(result) == (2, 0, 0)
    assert [f.gap_index for f in result.flags] == [0, 1]


@pytest.mark.parametrize("turn,entry,expected,reason", [
    (1, "stent", (1, 0, 0), "chart ref"),
    (3, "other", (1, 0, 0), "transcript turn"),
    (1, "other", (0, 1, 1), "No same-type gap"),
])
def test_contradiction_chart_or_transcript_rule(visit, turn, entry, expected, reason):
    answer = key(gap("contradiction", GapType.CHART_CONTRADICTION, [3], entry="stent"))
    candidate = flag(visit, "candidate", GapType.CHART_CONTRADICTION, turns=[turn], entry=entry)
    result = match_visit([candidate], answer)
    assert counts(result) == expected
    assert reason in result.flags[0].reason


def test_contradiction_or_rule_never_bypasses_same_type(visit):
    answer = key(gap("contradiction", GapType.CHART_CONTRADICTION, [3], entry="stent"))
    candidate = flag(visit, "wrong", GapType.UNANSWERED_CONCERN, turns=[3], entry="stent")
    assert counts(match_visit([candidate], answer)) == (0, 1, 1)


def test_missed_question_uses_checklist_not_deleted_turn_indices(visit):
    answer = key(gap("missing", GapType.MISSED_QUESTION, [1], item="onset"))
    candidate = flag(visit, "wrong-item", GapType.MISSED_QUESTION, turns=[1], item="radiation")
    assert counts(match_visit([candidate], answer)) == (0, 1, 1)


@pytest.mark.parametrize("kind,edit,turn", [
    (GapType.UNANSWERED_CONCERN, "insert_concern", 1),
    (GapType.COMPREHENSION_BREAKDOWN, "insert_mishearing", 5),
    (GapType.COMPREHENSION_BREAKDOWN, "delete_teachback", 6),
])
def test_transcript_matching_requires_correct_source_and_turn(visit, kind, edit, turn):
    answer = key(gap("gap", kind, [turn], edit=edit))
    # An identical ref on the checklist must not be treated as a transcript ref.
    wrong = flag(visit, "wrong", kind, turns=[0], item=str(turn))
    assert counts(match_visit([wrong], answer)) == (0, 1, 1)
    right = flag(visit, "right", kind, turns=[0, turn])
    assert counts(match_visit([right], answer)) == (1, 0, 0)


def test_any_recorded_turn_can_match_and_indices_are_numeric(visit):
    answer = key(gap("concern", GapType.UNANSWERED_CONCERN, [5, 1]))
    candidate = flag(visit, "match", GapType.UNANSWERED_CONCERN, turns=[1])
    candidate.evidence[0].ref = "01"
    assert counts(match_visit([candidate], answer)) == (1, 0, 0)


def test_dismissals_do_not_change_tp_or_fp_counts(visit):
    answer = key(gap("concern", GapType.UNANSWERED_CONCERN, [1]))
    flags = [flag(visit, "found", GapType.UNANSWERED_CONCERN, turns=[1], dismissed=True),
             flag(visit, "extra", GapType.UNANSWERED_CONCERN, turns=[5], dismissed=True)]
    assert counts(match_visit(flags, answer)) == (1, 1, 0)


def test_unverified_flags_excluded_without_consuming_gaps(visit):
    answer = key(gap("concern", GapType.UNANSWERED_CONCERN, [1]))
    pending = flag(visit, "pending", GapType.UNANSWERED_CONCERN, turns=[1], verified=False)
    result = match_visit([pending], answer)
    assert counts(result) == (0, 0, 1)
    assert result.flags[0].outcome == "EXCLUDED"
    assert result.flags[0].reason_code == "unverified"
    verified = pending.model_copy(update={"verified": True, "flag_id": "verified"})
    result = match_visit([pending, verified], answer)
    assert counts(result) == (1, 0, 0)
    assert result.gaps[0].flag_index == 1
    assert counts(match_visit([pending], key())) == (0, 0, 0)


@pytest.mark.parametrize("verified", [False, True])
def test_wrong_visit_rejected_before_matching(visit, verified):
    candidate = flag(visit, "other-visit", GapType.UNANSWERED_CONCERN, turns=[1], verified=verified)
    candidate.visit_id = "another-visit"
    with pytest.raises(ValueError, match=r"flags\[0\].*another-visit.*fixture"):
        match_visit([candidate], key())


def test_empty_flags_on_clean_and_gapped_visits():
    empty = match_visit([], key())
    assert counts(empty) == (0, 0, 0)
    assert empty.flags == empty.gaps == ()
    missing = match_visit([], key(gap("concern", GapType.UNANSWERED_CONCERN, [1])))
    assert counts(missing) == (0, 0, 1)
    assert missing.gaps[0].reason_code == "unmatched_gap"


def test_timing_does_not_change_reference_matching(visit):
    answer = key(gap("concern", GapType.UNANSWERED_CONCERN, [1]))
    for raised_at_turn in (None, 0, 6, 8):
        candidate = flag(visit, "concern", GapType.UNANSWERED_CONCERN, turns=[1], raised_at_turn=raised_at_turn)
        assert counts(match_visit([candidate], answer)) == (1, 0, 0)

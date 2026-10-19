"""Metrics have independent, hand-computable expectations."""
import pytest

from eval.metrics import aggregate, type_metrics, wilson_interval
from src.schemas import GapType
from tests.test_eval_match import flag, gap, key, visit


@pytest.mark.parametrize("counts,expected", [
    ((0, 0, 0), (None, None, None)),
    ((0, 0, 2), (None, 0.0, 0.0)),
    ((0, 2, 0), (0.0, None, 0.0)),
    ((0, 2, 3), (0.0, 0.0, 0.0)),
    ((4, 0, 2), (1.0, 4 / 6, 0.8)),
    ((3, 1, 2), (0.75, 0.6, 2 / 3)),
])
def test_rates_and_null_denominators(counts, expected):
    result = type_metrics(*counts)
    assert (result.precision, result.recall, result.f1) == expected


def test_wilson_known_values_and_empty_trials():
    assert wilson_interval(0, 0) == {"lower": None, "upper": None}
    half = wilson_interval(5, 10)
    assert half["lower"] == pytest.approx(0.2365930905)
    assert half["upper"] == pytest.approx(0.7634069095)
    perfect = wilson_interval(6, 6)
    assert perfect["lower"] == pytest.approx(0.6096657121)
    assert perfect["upper"] == pytest.approx(1.0)
    assert wilson_interval(0, 6)["lower"] == pytest.approx(0.0)
    assert wilson_interval(0, 6)["upper"] == pytest.approx(1 - perfect["lower"])
    with pytest.raises(ValueError):
        wilson_interval(2, 1)
    with pytest.raises(ValueError):
        type_metrics(-1, 0, 0)


def test_drop_two_of_six_and_false_flag_on_clean_visit(visit):
    items = ["nature", "onset", "radiation", "exertional", "relieving", "dyspnea"]
    answer = key(*(gap(item, GapType.MISSED_QUESTION, item=item) for item in items))
    flags = [flag(visit, item, GapType.MISSED_QUESTION, item=item) for item in items[2:]]
    clean = key().model_copy(update={"visit_id": "clean"})
    extra = flag(visit, "extra", GapType.MISSED_QUESTION, item="onset", dismissed=True).model_copy(update={"visit_id": "clean"})
    result = aggregate([(answer, flags), (clean, [extra])])
    assert result.overall.model_dump() == dict(tp=4, fp=1, fn=2, precision=0.8, recall=4 / 6, f1=8 / 11)
    assert result.per_type[GapType.MISSED_QUESTION] == result.overall
    assert result.n_visits == 2 and result.n_clean_visits == 1
    assert result.false_flags_on_clean_visits == 1
    assert result.false_flags_per_visit == 0.5
    assert result.extras["overall"]["n_gaps"] == 6
    assert result.extras["overall"]["n_predictions"] == 5
    assert result.per_type[GapType.COMPREHENSION_BREAKDOWN].recall is None


def test_overall_is_micro_average_not_mean_of_type_rates(visit):
    answer = key(gap("a", GapType.MISSED_QUESTION, item="onset"),
                 gap("b", GapType.UNANSWERED_CONCERN, [1]),
                 gap("c", GapType.UNANSWERED_CONCERN, [5]),
                 gap("d", GapType.UNANSWERED_CONCERN, [7]))
    result = aggregate([(answer, [flag(visit, "a", GapType.MISSED_QUESTION, item="onset")])])
    assert result.overall.recall == 0.25
    assert result.overall.f1 == 0.4
    assert result.per_type[GapType.MISSED_QUESTION].recall == 1.0
    assert result.per_type[GapType.UNANSWERED_CONCERN].recall == 0.0


def test_early_flags_include_fp_and_dismissals_but_exclude_unverified(visit):
    answer = key(gap("a", GapType.MISSED_QUESTION, item="onset"), gap("b", GapType.UNANSWERED_CONCERN, [1]))
    flags = [
        flag(visit, "early", GapType.MISSED_QUESTION, item="onset", raised_at_turn=5, dismissed=True),
        flag(visit, "early-fp", GapType.UNANSWERED_CONCERN, turns=[5], raised_at_turn=0),
        flag(visit, "boundary", GapType.UNANSWERED_CONCERN, turns=[1], raised_at_turn=6),
        flag(visit, "end", GapType.MISSED_QUESTION, item="radiation"),
        flag(visit, "excluded", GapType.MISSED_QUESTION, item="onset", raised_at_turn=0, verified=False),
    ]
    result = aggregate([(answer, flags)])
    assert result.extras["too_early"]["total"] == dict(n_flags=4, n_too_early=2, n_assumed_end=1, n_missing_wrap_up=0)
    assert result.extras["too_early"]["per_type"]["missed_question"]["n_too_early"] == 1
    assert result.extras["excluded_unverified"]["total"] == 1
    assert (result.overall.tp, result.overall.fp, result.overall.fn) == (2, 2, 0)
    unknown = answer.model_copy(update={"wrap_up_turn": None})
    total = aggregate([(unknown, flags)]).extras["too_early"]["total"]
    assert total == dict(n_flags=4, n_too_early=0, n_assumed_end=1, n_missing_wrap_up=3)


def test_delays_only_matched_flags_use_first_planted_turn_and_keep_negatives(visit):
    answer = key(gap("c", GapType.CHART_CONTRADICTION, [3], entry="stent"),
                 gap("m", GapType.COMPREHENSION_BREAKDOWN, [5, 1]),
                 gap("t", GapType.COMPREHENSION_BREAKDOWN, [6], edit="delete_teachback"))
    flags = [flag(visit, "c", GapType.CHART_CONTRADICTION, turns=[3], entry="stent", raised_at_turn=5),
             flag(visit, "m", GapType.COMPREHENSION_BREAKDOWN, turns=[1], raised_at_turn=1),
             flag(visit, "t", GapType.COMPREHENSION_BREAKDOWN, turns=[6]),
             flag(visit, "fp", GapType.COMPREHENSION_BREAKDOWN, turns=[0], raised_at_turn=8)]
    details = aggregate([(answer, flags)]).extras["turns_to_detection"]
    assert details["overall"] == dict(n_tp=3, n_timed=2, n_missing_raised_at_turn=1,
                                       mean=-1, median=-1.0, n_negative=1, values=[2, -4])
    assert details["per_type"]["chart_contradiction"]["mean"] == 2
    empty = aggregate([(key(), [])]).extras["turns_to_detection"]["overall"]
    assert empty["mean"] is None and empty["median"] is None and empty["n_timed"] == 0


def test_reject_empty_duplicate_and_mixed_split_inputs():
    with pytest.raises(ValueError, match="empty"):
        aggregate([])
    with pytest.raises(ValueError, match="Duplicate"):
        aggregate([(key(), []), (key(), [])])
    other = key().model_copy(update={"visit_id": "other", "split": "test"})
    with pytest.raises(ValueError, match="different splits"):
        aggregate([(key(), []), (other, [])])

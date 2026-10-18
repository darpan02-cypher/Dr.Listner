import json

import pytest

from src.dataset import pools as P
from src.dataset.eval_build import build_all
from src.dataset.eval_specs import ALL
from src.schemas import AnswerKey, Chart, GapType, Transcript


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("eval")
    manifest = build_all(ALL, out)
    return out, manifest


def load(out, split, vid):
    d = out / split
    return (
        Transcript.model_validate_json((d / "transcripts" / f"{vid}.json").read_text()),
        Transcript.model_validate_json((d / "base" / f"{vid}.json").read_text()),
        Chart.model_validate_json((d / "charts" / f"{vid}.json").read_text()),
        AnswerKey.model_validate_json((d / "answer_keys" / f"{vid}.json").read_text()),
    )


def all_visits(out):
    for s in ALL:
        yield (s, *load(out, s.split, s.id))


def test_shape_and_coverage(built):
    _, m = built
    assert m["summary"]["dev"]["visits"] == 9 and m["summary"]["test"]["visits"] == 15
    assert m["summary"]["dev"]["clean"] + m["summary"]["test"]["clean"] >= 5
    for t in GapType:
        assert m["summary"]["test"]["gaps"][t.value] >= 5  # every type, incl. gap 4, has test instances


def test_deterministic(built, tmp_path):
    out, _ = built
    build_all(ALL, tmp_path)
    for p in out.rglob("*.json"):
        assert p.read_bytes() == (tmp_path / p.relative_to(out)).read_bytes()


def test_dev_test_phrasing_disjoint(built):
    out, _ = built
    def texts(split):
        return {t.text for s, tr, *_ in all_visits(out) if s.split == split for t in tr.turns}
    shared = texts("dev") & texts("test")
    # only chart-derived answers and plan restatements may be shared
    assert all(x.startswith(("I take", "I have", "I will")) for x in shared), shared


def test_key_reconciles_with_transcripts(built):
    out, _ = built
    concern_texts = {c for c, _ in P.CONCERNS}
    resp_texts = {r for _, r in P.CONCERNS}
    deny = set(P.PASTHX_DENY) | set(P.RISK_DENIAL) | set(P.MEDS_DENY)
    wrong = {w for d in P.ITEMS.values() for w in d["wrong"]}
    repeats = {r for grp in P.REPEAT_REQ for r in grp}
    for s, final, base, chart, key in all_visits(out):
        wrap = final.turn(key.wrap_up_turn)
        assert wrap.speaker == "clinician" and any(w in wrap.text for w in P.WRAP)
        for g in key.planted_gaps:
            if g.type is GapType.MISSED_QUESTION:
                rx = P.LINT_RE[g.checklist_item_id]
                assert any(rx.search(base.turn(i).text) for i in g.turn_indices)
                assert not any(rx.search(t.text) for t in final.turns), "item still covered"
            elif g.type is GapType.UNANSWERED_CONCERN:
                i = g.turn_indices[0]
                assert final.turn(i).speaker == "patient" and final.turn(i).text in concern_texts
                assert not any(t.text in resp_texts for t in final.turns), "concern was answered"
            elif g.type is GapType.CHART_CONTRADICTION:
                assert chart.entry(g.chart_entry_id)
                assert final.turn(g.turn_indices[0]).speaker == "patient" and final.turn(g.turn_indices[0]).text in deny
            elif g.edit_op == "insert_mishearing":
                i = g.turn_indices[0]
                assert final.turn(i).text in wrong | repeats
                nxt = final.turn(i + 1)
                assert nxt is None or not any(f in nxt.text for f in P.REPEAT_FIX), "was repaired"
            else:  # delete_teachback
                i = g.turn_indices[0]
                assert i == key.wrap_up_turn
                assert not any(q in final.turn(i).text for q in P.TEACHBACK_Q)
                assert final.turn(i + 1).text in P.BARE_OK


def test_hard_negatives_really_negative(built):
    out, _ = built
    resp_texts = {r for _, r in P.CONCERNS}
    concern_texts = {c for c, _ in P.CONCERNS}
    repeats = {r for grp in P.REPEAT_REQ for r in grp}
    n_repaired = n_addressed = 0
    for s, final, base, chart, key in all_visits(out):
        planted = {g.turn_indices[0] for g in key.planted_gaps if g.edit_op == "insert_mishearing"}
        for t in final.turns:
            if t.text in repeats and t.idx not in planted:
                assert any(f in final.turn(t.idx + 1).text for f in P.REPEAT_FIX)
                n_repaired += 1
            if t.text in concern_texts and not any(g.type is GapType.UNANSWERED_CONCERN for g in key.planted_gaps):
                assert final.turn(t.idx + 1).text in resp_texts
                n_addressed += 1
    assert n_repaired >= 3 and n_addressed >= 3


def test_concern_position_not_always_last(built):
    out, _ = built
    last = mid = 0
    for s, final, base, chart, key in all_visits(out):
        for g in key.planted_gaps:
            if g.type is GapType.UNANSWERED_CONCERN:
                if g.turn_indices[0] == len(final.turns) - 2:
                    last += 1
                else:
                    mid += 1
    assert mid >= 2 and last >= 2


def test_caregiver_and_profiles(built):
    out, _ = built
    cg = [s for s, *_ in all_visits(out) if s.caregiver]
    assert len(cg) >= 5
    for s, final, base, chart, key in all_visits(out):
        has = any(t.speaker == "caregiver" for t in final.turns)
        assert has == s.caregiver and key.profile_id == s.profile

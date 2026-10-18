import pytest
from src import pack
from src.engine import new_state, process_turn, run_batch
from src.schemas import Transcript, Turn
from src.sources import ReplaySource


def _transcript():
    return Transcript(visit_id="v", chart_id="c", turns=[
        Turn(idx=0, speaker="clinician", text="Hello"),
        Turn(idx=1, speaker="patient", text="What?"),
        Turn(idx=2, speaker="caregiver", text="She did not hear you"),
    ])


def test_profiles_load():
    profs = pack.load_profiles()
    assert set(profs) == {"hoh_lowlit_alone", "hoh_lowlit_caregiver"}
    assert profs["hoh_lowlit_caregiver"].caregiver_present and not profs["hoh_lowlit_alone"].caregiver_present


def test_replay_feeds_engine_turn_by_turn_and_batch_equals_fold():
    prof = pack.load_profiles()["hoh_lowlit_alone"]
    t = _transcript()
    s = new_state("v", prof)
    for turn in ReplaySource(t).turns():
        s = process_turn(s, turn)
    assert [x.idx for x in s.turns_seen] == [0, 1, 2]
    assert run_batch(new_state("v", prof), t.turns) == s


def test_out_of_order_turn_rejected():
    prof = pack.load_profiles()["hoh_lowlit_alone"]
    s = process_turn(new_state("v", prof), Turn(idx=0, speaker="clinician", text="Hi"))
    with pytest.raises(ValueError):
        process_turn(s, Turn(idx=2, speaker="patient", text="x"))

import json
from datetime import date

import pytest

from src.dataset.build import HISTORY, base_visit, build_dataset, plant_gaps
from src.dataset.fhir import chart_from_synthea
from src.pack import load_checklist
from src.schemas import AnswerKey, Chart, Transcript


def test_dataset_reproducible_and_linked(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest = build_dataset(first)
    build_dataset(second)
    n = len(HISTORY)
    assert len(manifest["visits"]) == 3 + n + 6 + n
    assert manifest["checklist_verified"] == all(i.verification_status == "VERIFIED" for i in load_checklist().items)
    for path in first.rglob("*.json"):
        assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()
    clean = 0
    for record in manifest["visits"]:
        visit = record["visit_id"]
        transcript = Transcript.model_validate_json((first / "transcripts" / f"{visit}.json").read_text())
        chart = Chart.model_validate_json((first / "charts" / f"{visit}.json").read_text())
        key = AnswerKey.model_validate_json((first / "answer_keys" / f"{visit}.json").read_text())
        assert transcript.chart_id == chart.chart_id
        assert transcript.visit_id == key.visit_id
        assert key.split == "dev"
        clean += key.is_clean
        for gap in key.planted_gaps:
            if gap.chart_entry_id:
                assert chart.entry(gap.chart_entry_id)
            if gap.edit_op != "delete_turns":
                assert all(transcript.turn(i).speaker == "patient" for i in gap.turn_indices)
    assert clean == 3


@pytest.mark.parametrize("missing", HISTORY)
def test_mixed_edits_keep_correct_indices(missing):
    base, chart, ranges = base_visit("test")
    result, key = plant_gaps(base, chart, ranges, missing=missing, concern=True, contradiction=True)
    assert len(key.planted_gaps) == 3
    assert key.planted_gaps[0].turn_indices == ranges[missing]
    assert all(result.turn(i).text != base.turn(ranges[missing][0]).text for i in range(len(result.turns)))
    contradiction, concern = key.planted_gaps[1:]
    assert "never" in result.turn(contradiction.turn_indices[0]).text
    assert concern.turn_indices == [len(result.turns) - 1]
    assert base.turn(ranges[missing][0]).speaker == "clinician"
    assert len(base.turns) == 2 + 2 * len(HISTORY) + 4  # source was not mutated


def bundle():
    return {"resourceType": "Bundle", "entry": [
        {"fullUrl": "urn:uuid:p1", "resource": {"resourceType": "Patient", "id": "p1", "birthDate": "1980-10-20", "gender": "female"}},
        {"resource": {"resourceType": "Condition", "id": "c1", "subject": {"reference": "urn:uuid:p1"}, "code": {"coding": [{"display": "High blood pressure"}]}, "clinicalStatus": {"coding": [{"code": "active"}]}}},
        {"resource": {"resourceType": "Procedure", "id": "other", "subject": {"reference": "Patient/p2"}, "code": {"text": "Exclude this"}}},
    ]}


def test_fhir_maps_only_matching_patient():
    chart = chart_from_synthea(bundle(), synthetic=True, as_of=date(2026, 10, 18))
    assert chart.age == 45
    assert chart.sex == "female"
    assert len(chart.entries) == 1
    assert chart.entries[0].entry_id == "Condition/c1"
    assert chart.entries[0].status == "active"


def test_fhir_rejects_unattested_and_multi_patient():
    with pytest.raises(ValueError, match="synthetic"):
        chart_from_synthea(bundle(), synthetic=False, as_of=date(2026, 10, 18))
    multiple = bundle()
    multiple["entry"].append(multiple["entry"][0])
    with pytest.raises(ValueError, match="exactly one"):
        chart_from_synthea(multiple, synthetic=True, as_of=date(2026, 10, 18))

"""Convert an explicitly synthetic Synthea FHIR bundle to the app's Chart."""
from datetime import date
from typing import Any
from src.schemas import Chart, ChartEntry


def _label(value: dict) -> str | None:
    return value.get("text") or next((c.get("display") for c in value.get("coding", []) if c.get("display")), None)


def chart_from_synthea(bundle: dict[str, Any], *, synthetic: bool, as_of: date) -> Chart:
    """Caller must attest synthetic provenance; no file is fetched or stored.

    The explicit reference date keeps computed ages reproducible. Only resources
    that can be linked to the bundle's single patient are included.
    """
    if synthetic is not True:
        raise ValueError("Only explicitly synthetic bundles are accepted")
    if bundle.get("resourceType") != "Bundle":
        raise ValueError("Expected a FHIR Bundle")
    entries = bundle.get("entry", [])
    patients = [e for e in entries if e.get("resource", {}).get("resourceType") == "Patient"]
    if len(patients) != 1:
        raise ValueError("Expected exactly one patient")
    patient = patients[0]["resource"]
    patient_id = patient["id"]
    birth = date.fromisoformat(patient["birthDate"])
    age = as_of.year - birth.year - ((as_of.month, as_of.day) < (birth.month, birth.day))
    references = {f"Patient/{patient_id}", f"urn:uuid:{patient_id}"}
    if patients[0].get("fullUrl"):
        references.add(patients[0]["fullUrl"])
    supported = {"Condition", "Procedure", "MedicationRequest", "AllergyIntolerance", "Observation"}
    chart_entries = []
    seen = set()
    for entry in entries:
        resource = entry.get("resource", {})
        kind = resource.get("resourceType")
        if kind not in supported:
            continue
        subject = resource.get("subject", resource.get("patient", {})).get("reference")
        if subject not in references:
            continue
        display = _label(resource.get("code", resource.get("medicationCodeableConcept", {})))
        if not display:
            continue
        entry_id = f"{kind}/{resource['id']}"
        if entry_id in seen:
            raise ValueError(f"Duplicate chart entry: {entry_id}")
        seen.add(entry_id)
        status = resource.get("clinicalStatus", resource.get("status"))
        if isinstance(status, dict):
            status = _label(status) or next((c.get("code") for c in status.get("coding", [])), None)
        recorded = next((resource[field] for field in ("performedDateTime", "effectiveDateTime", "onsetDateTime", "authoredOn", "recordedDate") if resource.get(field)), None)
        chart_entries.append(ChartEntry(entry_id=entry_id, resource_type=kind, display=display, status=status, date=recorded))
    sex = patient.get("gender")
    return Chart(chart_id=patient_id, age=age, sex=sex if sex in {"female", "male"} else "other", entries=chart_entries)

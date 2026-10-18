# Synthetic development fixtures

Rebuild from the repository root with:

```sh
.venv/bin/python -m scripts.build_dataset
```

No API key, network call, or real patient data is used. The builder overwrites its
own numbered JSON files; use `--output /tmp/drlistner-fixtures` for a separate copy.

The 29 visits contain 3 clean controls, 10 missed-question cases (one per
checklist item), 3 unanswered-concern cases, 3 chart-contradiction cases, and 10
mixed cases. All belong to the development split. Variants share templates;
they must not be presented as an independent test set or evidence of accuracy.

- `base_transcripts/`: original scripts before gap planting.
- `transcripts/`: edited pipeline inputs.
- `charts/`: paired hand-authored synthetic charts, **not Synthea-generated**.
- `answer_keys/`: evaluation-only labels and plan items; never detection inputs.
- `manifest.json`: provenance, checklist status, and visit inventory.

Deletion indices refer to the original transcript. Inserted-concern and
contradiction indices refer to the final transcript. A contradiction removes the
original truthful answer and inserts a denial at the same position. Plan items
are retained in every visit. Answer keys come from those edits, not LLM judgments.

These scripts test software behavior, not clinical quality. The checklist items were
matched to the guideline text by Claude (not clinician-reviewed), and the scripts
have not received clinician review. No detection
agents, cached model results, or measured evaluation results are included.

## Synthea integration

An importer is available for an existing, explicitly synthetic Synthea FHIR bundle:

```sh
.venv/bin/python -m scripts.import_synthea /path/to/synthetic-bundle.json \
  --confirm-synthetic --as-of 2026-10-18 --output /tmp/synthea-chart.json
```

It requires exactly one patient, computes age at the supplied reference date,
and includes supported resources linked to that patient: Condition, Procedure,
MedicationRequest (inline medication concepts), AllergyIntolerance, Observation.
It does not retain raw patient identifiers beyond the synthetic chart ID, or raw
FHIR payloads. This is a FHIR-lite adapter, not a general FHIR validator. Synthea
has not been installed or run; import against actual generated bundles remains
to be exercised. Imported charts are not automatically paired with the fixture
transcripts, whose history and planted contradictions depend on their own charts.

Before held-out evaluation: have a clinician review the checklist, generate/import Synthea charts,
write varied matching scripts, review the scripts, and freeze an independent test
split without template siblings crossing the split.

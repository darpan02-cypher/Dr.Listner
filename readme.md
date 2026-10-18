# Dr.Listner

Prototype that checks a synthetic chest-pain visit transcript for documentation gaps. See `docs/PROJECT_REPORT.md` and `SPEC.md`. Synthetic data only; not a medical device; no HIPAA claim.

Dev setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest`

## Run the implemented foundation locally

There is no web app entry point yet. For the current code and offline dataset:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'pydantic>=2.6' requests pytest
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.build_dataset
```

These commands need no API key. See `data/synthetic/README.md` for the 29
synthetic development visits, answer keys, limitations, and Synthea import command.
The full requirements files include dependencies for later implementation phases.

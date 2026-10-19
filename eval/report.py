"""Render saved metrics without reading runs, datasets, or computing scores."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from eval.io import InputError, validate_file
from src.schemas import EvalResult, GapType


class Interval(BaseModel):
    lower: float | None = Field(ge=0, le=1)
    upper: float | None = Field(ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        if (self.lower is None) != (self.upper is None):
            raise ValueError("Both interval bounds must be null or both numeric")
        if self.lower is not None and self.lower > self.upper:
            raise ValueError("Interval lower bound exceeds upper bound")
        return self


class CountDetails(BaseModel):
    n_visits: int = Field(ge=1)
    n_gaps: int = Field(ge=0)
    n_predictions: int = Field(ge=0)
    precision_ci95: Interval
    recall_ci95: Interval


class ReportExtras(BaseModel):
    per_type: dict[GapType, CountDetails]
    overall: CountDetails
    synthetic_run: bool


class SavedResult(EvalResult):
    extras: ReportExtras

    @model_validator(mode="after")
    def complete(self):
        if set(self.per_type) != set(GapType) or set(self.extras.per_type) != set(GapType):
            raise ValueError("Saved results must contain every gap type and its count/CI details")
        return self


def _cell(value: object) -> str:
    return (str(value).replace("\\", "\\\\").replace("|", "\\|")
            .replace("\r", " ").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;"))


def _percent(value: float | None) -> str:
    # Formatting a saved ratio as a percentage is the only arithmetic here.
    return "—" if value is None else f"{value:.1%}"


def _interval(value: Interval) -> str:
    return "—" if value.lower is None else f"{_percent(value.lower)}–{_percent(value.upper)}"


def make_results_table(results_root: Path, run_id: str | None = None) -> str:
    """Read only immediate *.json result files; reject missing metric extras.

    Counts, rates, and intervals are taken directly from each saved result.
    Never fill in missing numbers or recompute them from other fields.
    """
    paths = sorted(results_root.glob("*.json"))
    if run_id is not None:
        paths = [path for path in paths if path.stem == run_id]
    if not paths:
        raise InputError(f"{results_root}: no matching result JSON files")
    blocks = []
    for path in paths:
        result = validate_file(path, SavedResult)
        if path.stem != result.run_id:
            raise InputError(f"{path}: run_id does not match filename")
        provenance = "FAKE: harness check only" if result.extras.synthetic_run else "Engine run"
        caption = " · ".join(_cell(value) for value in (
            result.run_id, result.system, result.split, result.mode, result.model, provenance,
        ))
        lines = [caption, "", "Source: " + _cell(path.name), "",
                 "| Type | Visits | Gaps | Predictions | TP | FP | FN | Precision | Recall | F1 | Precision CI | Recall CI |",
                 "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
        for name in [kind.value for kind in GapType] + ["overall"]:
            metric = result.overall if name == "overall" else result.per_type[GapType(name)]
            detail = result.extras.overall if name == "overall" else result.extras.per_type[GapType(name)]
            values = [name, detail.n_visits, detail.n_gaps, detail.n_predictions, metric.tp, metric.fp, metric.fn,
                      _percent(metric.precision), _percent(metric.recall), _percent(metric.f1),
                      _interval(detail.precision_ci95), _interval(detail.recall_ci95)]
            lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"

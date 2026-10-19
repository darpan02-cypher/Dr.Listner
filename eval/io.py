"""File-contract validation shared by the scorer and synthetic run generator."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from src.schemas import AnswerKey, Chart, Flag, GapType, Transcript

ROOT = Path(__file__).resolve().parent.parent


class InputError(ValueError):
    """An invalid or incomplete evaluation input; safe to report at the CLI."""


def safe_run_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise InputError("run_id must be a single name using letters, digits, underscore, dot, or hyphen")
    return value


class RunMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    system: Literal["drlistner", "baseline"]
    mode: Literal["DEMO", "LIVE"]
    model: str = Field(min_length=1)
    split: Literal["dev", "test"]


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputError(f"{path}: {error}") from error


def validate_file(path: Path, schema):
    data = read_json(path)
    try:
        return TypeAdapter(schema).validate_python(data)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}"
            for e in error.errors(include_url=False, include_input=False)
        )
        raise InputError(f"{path}: {details}") from error


@dataclass(frozen=True)
class DatasetVisit:
    key: AnswerKey
    transcript: Transcript
    chart: Chart


def load_dataset(data_root: Path, split: str) -> list[DatasetVisit]:
    if split not in {"dev", "test"}:
        raise InputError("split must be dev or test")
    directory = data_root / split
    files = {folder: {p.stem: p for p in (directory / folder).glob("*.json")}
             for folder in ("answer_keys", "transcripts", "charts")}
    ids = set(files["answer_keys"])
    if not ids:
        raise InputError(f"{directory / 'answer_keys'}: no answer-key JSON files")
    errors = []
    for folder, paths in files.items():
        for visit_id in sorted(ids - paths.keys()):
            errors.append(f"{directory / folder / (visit_id + '.json')}: missing required file")
        for visit_id in sorted(paths.keys() - ids):
            errors.append(f"{paths[visit_id]}: no corresponding answer key")
    visits = []
    for visit_id in sorted(ids):
        if any(visit_id not in paths for paths in files.values()):
            continue
        key_path = files["answer_keys"][visit_id]
        try:
            key = validate_file(key_path, AnswerKey)
            transcript = validate_file(files["transcripts"][visit_id], Transcript)
            chart = validate_file(files["charts"][visit_id], Chart)
            if key.visit_id != visit_id or transcript.visit_id != visit_id:
                raise InputError(f"{directory}: visit_id must match filename {visit_id!r}")
            if key.split != split:
                raise InputError(f"{key_path}: split {key.split!r} does not match {split!r}")
            if transcript.chart_id != chart.chart_id:
                raise InputError(f"{directory}: chart_id mismatch for {visit_id}")
            if key.wrap_up_turn is not None and transcript.turn(key.wrap_up_turn) is None:
                raise InputError(f"{key_path}: wrap_up_turn points outside the transcript")
            if len({g.gap_id for g in key.planted_gaps}) != len(key.planted_gaps):
                raise InputError(f"{key_path}: duplicate gap_id")
            for gap in key.planted_gaps:
                if gap.type != GapType.MISSED_QUESTION and any(transcript.turn(i) is None for i in gap.turn_indices):
                    raise InputError(f"{key_path}: gap {gap.gap_id!r} references missing transcript turns")
                if gap.chart_entry_id is not None and chart.entry(gap.chart_entry_id) is None:
                    raise InputError(f"{key_path}: gap {gap.gap_id!r} references a missing chart entry")
            visits.append(DatasetVisit(key, transcript, chart))
        except InputError as error:
            errors.append(str(error))
    if errors:
        raise InputError("\n".join(errors))
    return visits


def load_run(run_dir: Path, run_id: str, split: str, visits: list[DatasetVisit]) -> tuple[RunMeta, dict[str, list[Flag]]]:
    meta_path = run_dir / "run_meta.json"
    meta = validate_file(meta_path, RunMeta)
    if meta.run_id != run_id or meta.split != split:
        raise InputError(f"{meta_path}: run_id and split must match requested {run_id!r}, {split!r}")
    expected = {visit.key.visit_id for visit in visits}
    paths = {path.stem: path for path in (run_dir / "flags").glob("*.json")}
    errors = [f"{paths[vid]}: unexpected visit" for vid in sorted(paths.keys() - expected)]
    flags = {}
    for visit_id in sorted(expected):
        path = run_dir / "flags" / f"{visit_id}.json"
        if visit_id not in paths:
            errors.append(f"{path}: missing flags file (write [] for no flags)")
            continue
        try:
            parsed = validate_file(path, list[Flag])
            for index, flag in enumerate(parsed):
                if flag.visit_id != visit_id:
                    raise InputError(f"{path}: flag[{index}] has wrong visit_id {flag.visit_id!r}")
            flags[visit_id] = parsed
        except InputError as error:
            errors.append(str(error))
    if errors:
        raise InputError("\n".join(errors))
    return meta, flags

"""Pydantic contracts shared by every agent. See SPEC.md section 2."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------- Transcript ----------
class Turn(BaseModel):
    idx: int = Field(ge=0)
    speaker: Literal["clinician", "patient", "caregiver"]
    text: str = Field(min_length=1)
    t_start: float | None = Field(default=None, ge=0)  # seconds from visit start
    t_end: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _times(self) -> "Turn":
        if self.t_start is not None and self.t_end is not None and self.t_end < self.t_start:
            raise ValueError("t_end before t_start")
        return self


class Transcript(BaseModel):
    visit_id: str
    chart_id: str
    turns: list[Turn]
    synthetic: Literal[True] = True  # real transcripts are rejected by construction

    @model_validator(mode="after")
    def _contiguous(self) -> "Transcript":
        if not self.turns:
            raise ValueError("transcript has no turns")
        if [t.idx for t in self.turns] != list(range(len(self.turns))):
            raise ValueError("turn idx must be 0..n-1 in order")
        return self

    def turn(self, idx: int) -> Turn | None:
        return self.turns[idx] if 0 <= idx < len(self.turns) else None


# ---------- Chart (FHIR-lite view of a Synthea bundle) ----------
class ChartEntry(BaseModel):
    entry_id: str
    resource_type: str  # Condition, Procedure, MedicationRequest, AllergyIntolerance, Observation...
    display: str  # human-readable, e.g. "Coronary stent placement"
    status: str | None = None
    date: str | None = None
    fhir: dict[str, Any] | None = None  # original resource, optional


class Chart(BaseModel):
    chart_id: str
    age: int = Field(ge=0, le=120)
    sex: Literal["female", "male", "other"]
    entries: list[ChartEntry]
    synthetic: Literal[True] = True

    def entry(self, entry_id: str) -> ChartEntry | None:
        return next((e for e in self.entries if e.entry_id == entry_id), None)


# ---------- Flag ----------
class GapType(str, Enum):
    MISSED_QUESTION = "missed_question"  # type 1
    UNANSWERED_CONCERN = "unanswered_concern"  # type 2
    CHART_CONTRADICTION = "chart_contradiction"  # type 3
    COMPREHENSION_BREAKDOWN = "comprehension_breakdown"  # type 4 (draft cues, not clinically validated)


class EvidencePointer(BaseModel):
    source: Literal["transcript", "chart", "checklist"]
    ref: str  # turn idx (as str) | chart entry_id | checklist item id
    quote: str | None = None  # verbatim text; required for transcript/chart

    @model_validator(mode="after")
    def _quote_required(self) -> "EvidencePointer":
        if self.source in ("transcript", "chart") and not self.quote:
            raise ValueError(f"{self.source} evidence needs a verbatim quote")
        if self.source == "transcript" and not self.ref.isdigit():
            raise ValueError("transcript ref must be a turn index")
        return self


class Flag(BaseModel):
    flag_id: str
    visit_id: str
    type: GapType
    evidence: list[EvidencePointer] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    verified: bool = False  # set True only by VerifierAgent
    dismissed: bool = False  # UI state
    raised_at_turn: int | None = Field(default=None, ge=0)  # turn idx when first emitted (turns-to-detection)

    @model_validator(mode="after")
    def _evidence_shape(self) -> "Flag":
        srcs = {e.source for e in self.evidence}
        if self.type is GapType.MISSED_QUESTION and "checklist" not in srcs:
            raise ValueError("missed_question needs a checklist evidence pointer")
        if self.type is GapType.UNANSWERED_CONCERN and "transcript" not in srcs:
            raise ValueError("unanswered_concern needs a transcript evidence pointer")
        if self.type is GapType.CHART_CONTRADICTION and not {"transcript", "chart"} <= srcs:
            raise ValueError("chart_contradiction needs transcript and chart evidence")
        if self.type is GapType.COMPREHENSION_BREAKDOWN and "transcript" not in srcs:
            raise ValueError("comprehension_breakdown needs a transcript evidence pointer")
        return self


# ---------- Checklist ----------
class ChecklistItem(BaseModel):
    id: str
    label: str
    description: str
    example_questions: list[str] = Field(min_length=1)
    guideline_ref: str | None = None
    guideline_quote: str | None = None  # short verbatim excerpt supporting the item
    verification_status: Literal["VERIFIED", "UNVERIFIED"]
    verification_note: str

    @model_validator(mode="after")
    def _cited_or_unverified(self) -> "ChecklistItem":
        if self.verification_status == "VERIFIED" and not self.guideline_ref:
            raise ValueError(f"{self.id}: VERIFIED requires guideline_ref")
        return self


class Checklist(BaseModel):
    checklist_id: str
    version: str
    source: str
    items: list[ChecklistItem]

    @field_validator("items")
    @classmethod
    def _unique_ids(cls, v: list[ChecklistItem]) -> list[ChecklistItem]:
        ids = [i.id for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate checklist item ids")
        return v


# ---------- Answer key ----------
class PlantedGap(BaseModel):
    gap_id: str
    type: GapType
    edit_op: Literal[
        "delete_turns", "insert_concern", "insert_contradiction", "insert_mishearing", "delete_teachback"
    ]
    turn_indices: list[int] = Field(default_factory=list)  # turns deleted (pre-edit idx) or inserted (post-edit idx)
    checklist_item_id: str | None = None  # type 1
    chart_entry_id: str | None = None  # type 3
    description: str

    @model_validator(mode="after")
    def _shape(self) -> "PlantedGap":
        if self.type is GapType.MISSED_QUESTION and not self.checklist_item_id:
            raise ValueError("missed_question gap needs checklist_item_id")
        if self.type is GapType.CHART_CONTRADICTION and not self.chart_entry_id:
            raise ValueError("chart_contradiction gap needs chart_entry_id")
        if self.type is not GapType.MISSED_QUESTION and not self.turn_indices:
            raise ValueError("concern/contradiction gap needs turn_indices")
        return self


class PlanItem(BaseModel):
    item_id: str
    text: str  # a care-plan item the patient summary must cover


class AnswerKey(BaseModel):
    visit_id: str
    split: Literal["dev", "test"]
    profile_id: str | None = None
    wrap_up_turn: int | None = Field(default=None, ge=0)  # turn idx where wrap-up begins (eval trigger)
    planted_gaps: list[PlantedGap]
    plan_items: list[PlanItem] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.planted_gaps


# ---------- Patient profile & visit state ----------
class PatientProfile(BaseModel):
    profile_id: str
    label: str
    hearing_level: Literal["normal", "mild", "moderate", "severe"]
    literacy: Literal["adequate", "low"]
    caregiver_present: bool
    active_detectors: list[GapType]
    summary_max_words: int = Field(gt=0)
    summary_target_grade: float = Field(gt=0)
    teach_back_questions: int = Field(ge=0)


class OpenConcern(BaseModel):
    turn_idx: int
    text: str
    answered: bool = False


class VisitState(BaseModel):
    """State folded by engine.process_turn. Batch mode = fold over every turn."""

    visit_id: str
    profile: PatientProfile
    turns_seen: list[Turn] = Field(default_factory=list)
    checklist_coverage: dict[str, int | None] = Field(default_factory=dict)  # item id -> turn idx that covered it
    open_concerns: list[OpenConcern] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    wrapped_up: bool = False
    errors: list[str] = Field(default_factory=list)  # detector/verifier calls that failed (LLM unavailable, cache miss)


# ---------- Eval ----------
class TypeMetrics(BaseModel):
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)
    precision: float | None = None  # None when tp+fp == 0
    recall: float | None = None  # None when tp+fn == 0
    f1: float | None = None


class EvalResult(BaseModel):
    run_id: str
    system: Literal["drlistner", "baseline"]
    split: Literal["dev", "test"]
    mode: Literal["DEMO", "LIVE"]
    model: str
    git_commit: str
    timestamp: str  # ISO 8601
    n_visits: int = Field(ge=1)
    per_type: dict[GapType, TypeMetrics]
    overall: TypeMetrics
    false_flags_per_visit: float = Field(ge=0)
    n_clean_visits: int = Field(ge=0)
    false_flags_on_clean_visits: int = Field(ge=0)
    mean_reading_grade: float | None = None
    plan_coverage: float | None = Field(default=None, ge=0, le=1)

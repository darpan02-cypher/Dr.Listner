"""Condition-pack loading (only packs/chest_pain exists)."""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .schemas import Checklist, PatientProfile


def load_checklist(path: Path | None = None) -> Checklist:
    return Checklist.model_validate(json.loads((path or config.CHECKLIST_PATH).read_text()))


def load_profiles(pack_dir: Path | None = None) -> dict[str, PatientProfile]:
    d = (pack_dir or config.PACK_DIR) / "profiles"
    profs = [PatientProfile.model_validate(json.loads(f.read_text())) for f in sorted(d.glob("*.json"))]
    return {p.profile_id: p for p in profs}

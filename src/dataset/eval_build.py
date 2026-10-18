"""Eval dataset builder (dev + test). Deterministic; answer key comes from the edits.

A complete, gap-free base visit is assembled from phrase pools, then gaps are planted
by deterministic edits on named segments. Index conventions (SPEC.md): deletion
indices refer to the base transcript; insertion/replacement indices refer to the
final transcript. Hearing-loss repeat requests that the clinician repairs, and
concerns that the clinician addresses, are hard negatives (no gap).

Limits: charts are hand-authored FHIR-lite (not Synthea); phrasing comes from pools
written by us (no clinician review); gap-4 cues are our own draft.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from src import config
from src.pack import load_checklist
from src.schemas import AnswerKey, Chart, ChartEntry, GapType, PlanItem, PlantedGap, Transcript, Turn

from . import pools as P

HISTORY_ORDER = [
    ["nature", "onset", "radiation"],
    ["exertional", "relieving"],
    ["dyspnea", "diaphoresis", "syncope"],
    ["risk_factors", "family_history"],
]
MISHEAR_ITEMS = {i for i in P.ITEMS if i != "risk_factors"}


@dataclass
class Spec:
    id: str
    split: str
    profile: str = "hoh_lowlit_alone"
    cardiac: str = "none"  # stent | cabg | none
    conds: tuple[str, ...] = ("htn",)
    smoking: str = "never"
    meds_extra: tuple[str, ...] = ()
    missed: tuple[str, ...] = ()
    concern: str = "none"  # none | addressed_mid | addressed_late | unaddr_mid | unaddr_late
    contradiction: str | None = None  # cardiac | risk | meds
    mishear: tuple[str, str] | None = None  # (item, "wrong" | "repeat")
    repaired: tuple[str, ...] = ()
    teachback_missing: bool = False
    caregiver: bool = field(init=False, default=False)

    def __post_init__(self):
        self.caregiver = self.profile == "hoh_lowlit_caregiver"


def _rng(spec: Spec) -> random.Random:
    return random.Random(int(hashlib.sha256(spec.id.encode()).hexdigest()[:12], 16))


MED_FOR = {"htn": ("med-lisinopril", "Lisinopril"), "dm": ("med-metformin", "Metformin"), "hld": ("med-atorvastatin", "Atorvastatin"), "afib": ("med-apixaban", "Apixaban")}
COND_ENTRY = {"htn": ("cond-htn", "High blood pressure"), "dm": ("cond-dm", "Type 2 diabetes"), "hld": ("cond-hld", "High cholesterol"), "afib": ("cond-afib", "Atrial fibrillation")}


def make_chart(spec: Spec, rng: random.Random) -> Chart:
    ents = [ChartEntry(entry_id=COND_ENTRY[c][0], resource_type="Condition", display=COND_ENTRY[c][1], status="active") for c in spec.conds]
    if spec.cardiac == "stent":
        ents += [ChartEntry(entry_id="proc-stent", resource_type="Procedure", display="Coronary stent placement", status="completed", date="2019-05-14"),
                 ChartEntry(entry_id="med-clopidogrel", resource_type="MedicationRequest", display="Clopidogrel", status="active")]
    elif spec.cardiac == "cabg":
        ents.append(ChartEntry(entry_id="proc-cabg", resource_type="Procedure", display="Coronary artery bypass graft", status="completed", date="2012-03-02"))
    for c in spec.conds:
        mid, mname = MED_FOR[c]
        ents.append(ChartEntry(entry_id=mid, resource_type="MedicationRequest", display=mname, status="active"))
    ents.append(ChartEntry(entry_id="obs-smoking", resource_type="Observation", display="Former smoker" if spec.smoking == "former" else "Never smoker", status="final"))
    return Chart(chart_id=f"chart-{spec.id}", age=rng.randint(66, 89), sex=rng.choice(["female", "male"]), entries=ents)


Seg = dict  # {"name", "item", "turns": [(speaker, text)]}


def _pick(pool, rng, split):
    return rng.choice(P.half(pool, split))


def _med_list(chart: Chart) -> str:
    names = [e.display for e in chart.entries if e.resource_type == "MedicationRequest"]
    return "I take " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]) + "."


def _risk_answer(spec: Spec, rng) -> str:
    parts = [P.COND_PHRASE[c] for c in spec.conds]
    txt = ", and ".join(parts) + ". " + P.SMOKING[spec.smoking]
    return txt


def _segment_history(spec: Spec, item: str, rng, chart: Chart) -> Seg:
    d = P.ITEMS[item]
    qs = P.half(d["q"], spec.split)
    q = rng.choice(qs)
    if item == "risk_factors":
        a = _risk_answer(spec, rng)
    else:
        a = rng.choice(P.half(d["a"], spec.split))
    turns = [("clinician", q)]
    if item in spec.repaired:
        req = rng.choice(P.REPEAT_REQ[0 if spec.split == "dev" else 1])
        q2 = rng.choice([x for x in qs if x != q])
        turns += [("patient", req), ("clinician", rng.choice(P.half(P.REPEAT_FIX, spec.split)) + " " + q2)]
    turns.append(("patient", a))
    return {"name": f"h:{item}", "item": item, "turns": turns}


def build_base(spec: Spec) -> tuple[list[Seg], Chart, list[tuple[str, str, str]]]:
    rng = _rng(spec)
    chart = make_chart(spec, rng)
    sp = spec.split
    hoh_q, hoh_a = rng.choice(P.half(P.HOH_OPEN, sp))
    opening = [("clinician", hoh_q), ("patient", hoh_a)]
    if spec.caregiver:
        opening.append(("caregiver", _pick(P.CAREGIVER_OPEN, rng, sp)))
    opening += [("clinician", _pick(P.OPEN_Q, rng, sp)), ("patient", _pick(P.OPEN_A, rng, sp))]
    segs: list[Seg] = [{"name": "open", "item": None, "turns": opening}]
    order = []
    for grp in HISTORY_ORDER:
        g = grp[:]
        rng.shuffle(g)
        order += g
    # history items, with the mid-visit concern after a random item
    concern_slot = rng.randrange(2, len(order) - 1)
    cpair = rng.choice(P.half(P.CONCERNS, sp))
    for i, item in enumerate(order):
        segs.append(_segment_history(spec, item, rng, chart))
        if i == concern_slot and spec.concern.endswith("_mid"):
            segs.append({"name": "concern", "item": None, "turns": [("patient", cpair[0]), ("clinician", cpair[1])]})
    # past history and meds
    pa = rng.choice(P.half(P.PASTHX_TRUE[spec.cardiac], sp))
    segs.append({"name": "pasthx", "item": None, "turns": [("clinician", _pick(P.PASTHX_Q, rng, sp)), ("patient", pa)]})
    segs.append({"name": "meds", "item": None, "turns": [("clinician", _pick(P.MEDS_Q, rng, sp)), ("patient", _med_list(chart))]})
    # wrap-up, plan, teach-back, closing
    n_plan = rng.choice([2, 3])
    plan = rng.sample(P.PLAN, n_plan)
    ordinals = ["First", "Second", "Third"]
    steps = " ".join(f"{ordinals[i]}, {p[0]}." for i, p in enumerate(plan))
    tbq = _pick(P.TEACHBACK_Q, rng, sp)
    wrap_text = f"{_pick(P.WRAP, rng, sp)} {steps}"
    restate = "I will " + ", ".join(p[3] for p in plan[:-1]) + (" and " if len(plan) > 1 else "") + plan[-1][3] + "."
    # One clinician turn: wrap-up marker + plan + teach-back question. "alt" is the same turn without the teach-back question.
    segs.append({"name": "wrap", "item": None, "turns": [("clinician", f"{wrap_text} {tbq}")], "alt": wrap_text})
    segs.append({"name": "tb", "item": None, "turns": [("patient", restate)]})
    if spec.caregiver:
        segs.append({"name": "cg_close", "item": None, "turns": [("caregiver", _pick(P.CAREGIVER_CLOSE, rng, sp))]})
    any_turns = [("clinician", _pick(P.ANY_Q, rng, sp))]
    if spec.concern.endswith("_late"):
        any_turns += [("patient", cpair[0])]
        any_turns += [("clinician", cpair[1])]
        segs.append({"name": "late", "item": None, "turns": any_turns})
    else:
        segs.append({"name": "late", "item": None, "turns": any_turns + [("patient", _pick(P.NO_Q, rng, sp))]})
    segs.append({"name": "close", "item": None, "turns": [("clinician", _pick(P.CLOSE, rng, sp))]})
    return segs, chart, [(p[1], p[2], p[3]) for p in plan]


def _flatten(segs: list[Seg], visit_id: str, chart_id: str) -> tuple[Transcript, dict[str, list[int]]]:
    turns, ranges = [], {}
    for s in segs:
        start = len(turns)
        for spk, txt in s["turns"]:
            turns.append(Turn(idx=len(turns), speaker=spk, text=txt))
        ranges[s["name"]] = list(range(start, len(turns)))
    return Transcript(visit_id=visit_id, chart_id=chart_id, turns=turns), ranges


def _seg(segs, name):
    return next(s for s in segs if s["name"] == name)


def build_visit(spec: Spec) -> tuple[Transcript, dict[str, list[int]], Transcript, Chart, AnswerKey]:
    rng = _rng(spec)
    segs, chart, plan = build_base(spec)
    base, base_ranges = _flatten(segs, spec.id, chart.chart_id)
    edited = [dict(s, turns=list(s["turns"])) for s in segs]
    gaps: list[PlantedGap] = []
    pending: list[tuple] = []  # (gap fields, seg name, local offset) resolved after final flatten

    for item in spec.missed:
        edited = [s for s in edited if s["name"] != f"h:{item}"]
        gaps.append(PlantedGap(gap_id=f"{spec.id}-missed-{item}", type=GapType.MISSED_QUESTION, edit_op="delete_turns",
                               turn_indices=base_ranges[f"h:{item}"], checklist_item_id=item,
                               description=f"Deleted the {item} question and answer from the base transcript."))
    if spec.concern.startswith("unaddr"):
        name = "concern" if spec.concern.endswith("_mid") else "late"
        s = _seg(edited, name)
        if name == "concern":
            s["turns"] = s["turns"][:1]
        else:
            s["turns"] = s["turns"][:2] + []  # question, concern; response removed
        pending.append(("concern", name, 0 if name == "concern" else 1))
    if spec.contradiction == "cardiac":
        ent = "proc-stent" if spec.cardiac == "stent" else "proc-cabg"
        _seg(edited, "pasthx")["turns"][1] = ("patient", rng.choice(P.half(P.PASTHX_DENY, spec.split)))
        pending.append(("contradiction", "pasthx", 1, ent))
    elif spec.contradiction == "risk":
        _seg(edited, "h:risk_factors")["turns"][-1] = ("patient", rng.choice(P.half(P.RISK_DENIAL, spec.split)))
        pending.append(("contradiction", "h:risk_factors", len(_seg(edited, "h:risk_factors")["turns"]) - 1, COND_ENTRY[spec.conds[0]][0]))
    elif spec.contradiction == "meds":
        first = next(e.entry_id for e in chart.entries if e.resource_type == "MedicationRequest")
        _seg(edited, "meds")["turns"][1] = ("patient", rng.choice(P.half(P.MEDS_DENY, spec.split)))
        pending.append(("contradiction", "meds", 1, first))
    if spec.mishear:
        item, kind = spec.mishear
        s = _seg(edited, f"h:{item}")
        if kind == "wrong":
            s["turns"][-1] = ("patient", P.half(P.ITEMS[item]["wrong"], spec.split)[0])
        else:
            s["turns"][-1] = ("patient", rng.choice(P.REPEAT_REQ[0 if spec.split == "dev" else 1]))
        pending.append(("mishear", f"h:{item}", len(s["turns"]) - 1))
    if spec.teachback_missing:
        w = _seg(edited, "wrap")
        w["turns"] = [("clinician", w["alt"])]
        _seg(edited, "tb")["turns"] = [("patient", rng.choice(P.half(P.BARE_OK, spec.split)))]
        pending.append(("teachback", "wrap", 0))

    final, fr = _flatten(edited, spec.id, chart.chart_id)
    for p in pending:
        kind = p[0]
        idx = fr[p[1]][p[2]]
        if kind == "concern":
            gaps.append(PlantedGap(gap_id=f"{spec.id}-concern", type=GapType.UNANSWERED_CONCERN, edit_op="insert_concern", turn_indices=[idx],
                                   description="Patient concern with the clinician's response deleted."))
        elif kind == "contradiction":
            gaps.append(PlantedGap(gap_id=f"{spec.id}-contradiction-{spec.contradiction}", type=GapType.CHART_CONTRADICTION, edit_op="insert_contradiction",
                                   turn_indices=[idx], chart_entry_id=p[3], description=f"Truthful answer replaced by a denial ({spec.contradiction})."))
        elif kind == "mishear":
            gaps.append(PlantedGap(gap_id=f"{spec.id}-comprehension-mishear", type=GapType.COMPREHENSION_BREAKDOWN, edit_op="insert_mishearing",
                                   turn_indices=[idx], description=f"Patient answer replaced by a {spec.mishear[1]} reply to the {spec.mishear[0]} question; no repair follows."))
        elif kind == "teachback":
            gaps.append(PlantedGap(gap_id=f"{spec.id}-comprehension-teachback", type=GapType.COMPREHENSION_BREAKDOWN, edit_op="delete_teachback",
                                   turn_indices=[idx], description="Teach-back question removed from the plan turn; the patient replies with a bare acknowledgement."))
    key = AnswerKey(visit_id=spec.id, split=spec.split, profile_id=spec.profile, wrap_up_turn=fr["wrap"][0], planted_gaps=gaps,
                    plan_items=[PlanItem(item_id=i, text=t) for i, t, _ in plan])
    return base, base_ranges, final, chart, key


def lint_base(base: Transcript, ranges: dict[str, list[int]]) -> list[str]:
    """Each item's keywords may appear only in that item's own segment."""
    errs = []
    for item, rx in P.LINT_RE.items():
        own = set(ranges.get(f"h:{item}", []))
        for t in base.turns:
            if t.idx not in own and rx.search(t.text):
                errs.append(f"{base.visit_id}: '{item}' words in turn {t.idx}: {t.text!r}")
    return errs


def build_all(specs: list[Spec], out: Path) -> dict:
    ck = load_checklist()
    if set(P.ITEMS) != {i.id for i in ck.items}:
        raise ValueError("pools do not match checklist ids")
    errs, recs = [], []
    for spec in specs:
        base, base_ranges, final, chart, key = build_visit(spec)
        errs += lint_base(base, base_ranges)
        for folder, obj in (("base", base), ("transcripts", final), ("charts", chart), ("answer_keys", key)):
            path = out / spec.split / folder / f"{spec.id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(obj.model_dump_json(indent=2) + "\n")
        recs.append({"visit_id": spec.id, "split": spec.split, "profile": spec.profile, "turns": len(final.turns),
                     "gaps": {t.value: sum(g.type is t for g in key.planted_gaps) for t in GapType}})
    if errs:
        raise ValueError("leakage lint failed:\n" + "\n".join(errs))
    summary = {}
    for split in ("dev", "test"):
        r = [x for x in recs if x["split"] == split]
        summary[split] = {"visits": len(r), "clean": sum(not any(x["gaps"].values()) for x in r),
                          "gaps": {t.value: sum(x["gaps"][t.value] for x in r) for t in GapType}}
    manifest = {"version": 1, "synthetic": True, "checklist_version": ck.version,
                "source": "phrase pools + deterministic edits; hand-authored charts; not Synthea; no clinician review",
                "split_rule": "dev draws from first half of each phrase pool, test from the second half",
                "summary": summary, "visits": recs}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest

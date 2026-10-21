"""Dr.Listner dashboard (landing page + live console), wired to the real backends.

Synthetic data only; not a medical device. Run: streamlit run app2.py
Backends: Scripted (hardcoded, safe on stage) or Engine (real agents on the LLM cache or live providers).
Input: typed lines, browser mic, or live Deepgram capture with doctor/patient labels.
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

os.environ.setdefault("STT_PORT", "8766")  # keep clear of app.py's relay port

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from demo.backend import EngineBackend, ScriptedBackend, load_chart, load_flag_plan, load_script
from src import config
from src.pack import load_checklist, load_profiles
from src.schemas import PlanItem
from src.stt_deepgram import LiveSTT, mic_html

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Dr.Listner", page_icon="🩺", layout="wide", initial_sidebar_state="collapsed")

TYPE_LABEL = {
    "missed_question": "Not asked",
    "unanswered_concern": "Concern",
    "chart_contradiction": "Chart",
    "comprehension_breakdown": "Comprehension",
}
TYPE_BADGE = {"missed_question": "flag-gap", "unanswered_concern": "flag-conc",
              "chart_contradiction": "flag-chart", "comprehension_breakdown": "flag-comp"}
# gap-check toggle -> gap type it controls
GAP_CHECKS = {"Red-flag Qs": "missed_question", "Concerns": "unanswered_concern",
              "Chart check": "chart_contradiction", "Comprehension": "comprehension_breakdown"}
LIVE_TYPES = {"chart_contradiction", "comprehension_breakdown"}  # the only types shown during the visit
SPEAKER_CLS = {"clinician": "doc", "patient": "pat", "caregiver": "care"}
SPEAKER_NAME = {"clinician": "DOCTOR", "patient": "PATIENT", "caregiver": "CAREGIVER"}
INPUTS = ["Typed", "Browser mic", "Live mic"]
MUTED = "color:#8d96ad"

# ------------------------------------------------------------------- styling
st.markdown("""
<style>
#MainMenu, header, footer {visibility:hidden;}
.stApp {background:#eef1f6;}
.block-container {padding-top:1rem; max-width:1700px;}
.panel {background:#fff; border:1px solid #dfe4ee; border-radius:6px; margin-bottom:14px; overflow:hidden;}
.panel-h {padding:14px 20px; font-size:.78rem; font-weight:700; letter-spacing:.12em;
          color:#1f2a44; border-bottom:1px solid #e8ecf4; text-transform:uppercase;}
.panel-b {padding:14px 20px; font-size:.92rem; color:#2c3a5e;}
.row {display:flex; gap:12px; padding:9px 20px; border-bottom:1px solid #f0f2f8; align-items:flex-start; font-size:.9rem;}
.row.partial {opacity:.55; font-style:italic;}
.ts {color:#5b72c4; font-size:.78rem; min-width:34px; padding-top:2px;}
.badge {font-size:.64rem; font-weight:700; color:#fff; padding:3px 8px; border-radius:3px; letter-spacing:.05em; min-width:72px; text-align:center;}
.doc{background:#2f6b57;} .pat{background:#5b3fd1;} .care{background:#b9702a;}
.flag-chart{background:#c0392b;} .flag-comp{background:#d68910;} .flag-gap{background:#2e4a9e;} .flag-conc{background:#8e44ad;}
.txt {flex:1; color:#1f2a44;}
.kv {display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed #edf0f7;}
.kv b {font-size:.72rem; letter-spacing:.1em; color:#2f4590; text-transform:uppercase;}
.tile {display:inline-block; width:48%; background:#f5f7fc; border-radius:6px; padding:10px 12px; margin:0 1% 8px 0;}
.tile small{display:block; color:#6a78a0; font-size:.7rem; letter-spacing:.1em; text-transform:uppercase;}
.tile span{font-size:1.15rem; font-weight:600; color:#1f2a44;}
.chip {display:inline-block; background:#e9edf9; color:#2f4590; border-radius:12px; padding:2px 10px; font-size:.75rem; margin:2px 4px 2px 0;}
.chip.warn{background:#fdeaea; color:#a93226;}
.tick{padding:3px 0; font-size:.88rem;} .ok{color:#2f6b57;} .miss{color:#9aa4bf;} .miss-final{color:#c0392b; font-weight:600;}
.banner{background:#fff6dd; border:1px solid #f0d98a; color:#7a5d00; padding:6px 14px; border-radius:6px; font-size:.78rem; margin-bottom:10px;}
.orb-wrap{text-align:center; padding:14px 0 6px;}
.orb{width:120px; height:120px; border-radius:50%; margin:0 auto;
     background:radial-gradient(circle at 35% 30%, #fff, #bcd3ff 45%, #5b8cff);
     box-shadow:0 0 30px rgba(91,140,255,.5); animation:pulse 2.2s ease-in-out infinite;}
.orb.off{background:radial-gradient(circle at 35% 30%, #fff, #d9dde6 55%, #aab1c2); box-shadow:none; animation:none;}
@keyframes pulse{0%,100%{transform:scale(1); box-shadow:0 0 22px rgba(91,140,255,.4);}50%{transform:scale(1.07); box-shadow:0 0 44px rgba(91,140,255,.75);}}
.orb-label{margin-top:10px; letter-spacing:.15em; font-weight:700; color:#3b6df0;} .orb-label.off{color:#8d96ad;}
.side-h{font-size:.72rem; font-weight:700; letter-spacing:.14em; color:#1f2a44; margin:14px 0 6px; text-transform:uppercase;}
div[data-testid="stButton"] button {width:100%; border-radius:6px; border:1px solid #dfe4ee; background:#fff; color:#1f2a44; font-size:.85rem; min-height:48px;}
div[data-testid="stButton"] button[kind="primary"] {background:#e6f6ff; border-color:#8fd3f4; color:#1479a8;}
.hero{background:linear-gradient(135deg,#1f2a44,#3b4f9a); color:#fff; padding:44px 40px; border-radius:10px; margin-bottom:18px;}
.hero h1{margin:0 0 8px; font-size:2.4rem; color:#fff;} .hero p{font-size:1.05rem; color:#d8e0ff; max-width:760px;}
.card{background:#fff; border:1px solid #dfe4ee; border-radius:8px; padding:18px 20px; height:100%;}
.card h4{margin:0 0 6px; color:#1f2a44;} .card p{margin:0; color:#4a5878; font-size:.9rem;}
.hit{background:#fff4f2;}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------- data
@st.cache_resource
def _static():
    return load_checklist(), load_profiles(), load_chart(), load_script()


@st.cache_resource
def _stt() -> LiveSTT:
    return LiveSTT()


checklist, profiles, chart, script = _static()
stt = _stt()
ss = st.session_state


def new_backend(kind: str, profile_id: str, mode: str):
    args = (script["visit_id"], chart, checklist, profiles[profile_id])
    if kind == "Scripted":
        return ScriptedBackend(*args)
    from src.llm.client import LLMClient

    plan = [PlanItem(**p) for p in load_flag_plan()["plan_items"]]
    return EngineBackend(*args, llm=LLMClient(mode=config.Mode(mode)), plan_items=plan)


def start_visit() -> None:
    ss.be = new_backend(ss.kind, ss.profile_id, ss.mode)
    ss.cfg = (ss.kind, ss.profile_id, ss.mode)
    ss.script_pos = 0
    ss.last_mic = None
    ss.dismissed_all = False
    stt.reset_speakers()


ss.setdefault("page", "landing")
ss.setdefault("kind", "Scripted")
ss.setdefault("mode", "DEMO")
ss.setdefault("profile_id", next(iter(profiles)))
ss.setdefault("input", "Typed")
ss.setdefault("view", "Clinician")
ss.setdefault("det", {k: True for k in GAP_CHECKS})
if "be" not in ss:
    start_visit()


def panel(title: str, body: str, pad: bool = True) -> str:
    return f'<div class="panel"><div class="panel-h">{title}</div><div class="{"panel-b" if pad else ""}">{body}</div></div>'


def chips(xs, cls: str = "") -> str:
    return "".join(f'<span class="chip {cls}">{html.escape(x)}</span>' for x in xs) or f'<span style="{MUTED}">none on chart</span>'


def refresh() -> None:
    """Rerun just the console fragment when called from one, else the whole app."""
    try:
        st.rerun(scope="fragment")
    except st.errors.StreamlitAPIException:
        st.rerun()


def add_turn(speaker: str, text: str) -> None:
    if text and text.strip() and not ss.be.ended:
        ss.be.add_turn(speaker, text)


# ---------------------------------------------------------------- landing page
def landing() -> None:
    st.markdown("""<div class="hero"><h1>Dr.Listner</h1>
    <p>AI scribes record what was said. Dr.Listner flags what was never asked or answered,
    and hands the patient a plain-language plan they can follow.</p></div>""", unsafe_allow_html=True)
    st.markdown('<div class="banner">Synthetic / role-play data only. Documentation completeness tool: it never diagnoses or recommends treatment.</div>', unsafe_allow_html=True)

    st.subheader("Four gap types")
    gaps = [("1 · Red-flag question not asked", "Checklist items (onset, radiation, sweating, family history...) with no matching question."),
            ("2 · Concern left unanswered", "A worry the patient voiced that the clinician never addressed."),
            ("3 · Contradicts the chart", "Patient says no heart history; chart lists a prior stent."),
            ("4 · Comprehension not repaired", "Patient did not hear or understand and no repeat, rephrase or teach-back followed.")]
    for c, (h, p) in zip(st.columns(4), gaps):
        c.markdown(f'<div class="card"><h4>{h}</h4><p>{p}</p></div>', unsafe_allow_html=True)

    st.subheader("How it works")
    steps = [("Listen", "Live captions from the microphone with doctor and patient labels. Quiet during the visit: only chart and comprehension badges."),
             ("Check", "Chart, concern, checklist and comprehension agents; a verifier drops any flag without real evidence."),
             ("Hand off", "One end-of-visit gaps list for the clinician and a plain-language plan with read-aloud for the patient.")]
    for c, (h, p) in zip(st.columns(3), steps):
        c.markdown(f'<div class="card"><h4>{h}</h4><p>{p}</p></div>', unsafe_allow_html=True)

    st.subheader("Who it helps most")
    st.write("Older adults with hearing loss, low health literacy or cognitive impairment, with an optional caregiver in the room. Starting with outpatient chest pain.")
    st.markdown("&nbsp;")
    if st.button("Launch console  →", type="primary"):
        ss.page = "console"
        st.rerun()


# --------------------------------------------------------------------- console
def left_panel() -> None:
    be, p = ss.be, profiles[ss.profile_id]
    st.markdown('<div class="banner">Role-play demo — do not speak real patient information</div>', unsafe_allow_html=True)
    by_type: dict[str, list[str]] = {}
    for e in chart.entries:
        by_type.setdefault(e.resource_type, []).append(e.display)
    cited = {e.ref for f in be.flags for e in f.evidence if e.source == "chart"}
    cited_names = [e.display for e in chart.entries if e.entry_id in cited]
    tiles = [("Age", str(chart.age)), ("Sex", chart.sex.title()), ("Hearing", p.hearing_level.title()), ("Literacy", p.literacy.title())]
    tile_html = "".join(f'<div class="tile"><small>{k}</small><span>{html.escape(v)}</span></div>' for k, v in tiles)
    body = (f'<div style="font-size:1.25rem;font-weight:700;color:#1f2a44">{chart.age}-year-old {chart.sex}</div>'
            f'<div style="color:#6a78a0;margin-bottom:10px">{html.escape(p.label)} · synthetic chart</div>'
            f'<div class="kv"><b>Caregiver</b><span>{"Present" if p.caregiver_present else "Not present"}</span></div>'
            f'<div style="margin-top:12px">{tile_html}</div>'
            f'<div class="side-h">Conditions</div>{chips(by_type.get("Condition", []))}'
            f'<div class="side-h">Medications</div>{chips(by_type.get("MedicationRequest", []))}'
            f'<div class="side-h">Procedures</div>{chips(by_type.get("Procedure", []), "warn")}'
            f'<div class="side-h">Observations</div>{chips(by_type.get("Observation", []))}')
    if cited_names:
        body += f'<div class="side-h">Cited by a flag</div>{chips(cited_names, "warn")}'
    st.markdown(panel("Patient Dashboard", body), unsafe_allow_html=True)

    rows = ""
    closed = be.ended and (be.coverage or isinstance(be, ScriptedBackend))
    for it in checklist.items:
        at = be.coverage.get(it.id)
        if at is not None:
            rows += f'<div class="tick ok">✔ {html.escape(it.label)} <small>· turn {at}</small></div>'
        elif closed:
            rows += f'<div class="tick miss-final">✖ {html.escape(it.label)} — not asked</div>'
        else:
            rows += f'<div class="tick miss">○ {html.escape(it.label)}</div>'
    rows += '<div style="margin-top:8px;font-size:.72rem;color:#8d96ad">2021 AHA/ACC chest pain guideline; matched by Claude, not clinician-reviewed.</div>'
    st.markdown(panel("Chest-pain checklist coverage", rows), unsafe_allow_html=True)


def transcript_panel(live: bool) -> None:
    be = ss.be
    marks: dict[int, list[str]] = {}
    for f in be.flags:
        if f.dismissed or not ss.det[next(k for k, v in GAP_CHECKS.items() if v == f.type.value)]:
            continue
        for e in f.evidence:
            if e.source == "transcript":
                marks.setdefault(int(e.ref), []).append(f.type.value)
    rows = ""
    for t in be.turns:
        badges = "".join(f' <span class="badge {TYPE_BADGE[k]}" style="display:inline-block;min-width:0">⚑ {TYPE_LABEL[k].lower()}</span>' for k in marks.get(t.idx, []))
        rows += (f'<div class="row {"hit" if t.idx in marks else ""}"><span class="ts">#{t.idx}</span>'
                 f'<span class="badge {SPEAKER_CLS[t.speaker]}">{SPEAKER_NAME[t.speaker]}</span>'
                 f'<span class="txt">{html.escape(t.text)}{badges}</span></div>')
    if live and (stt.pending or stt.partial):
        role = stt.pending_role or stt.partial[0]
        text = f"{stt.pending} {stt.partial[1] if stt.partial else ''}".strip()
        rows += (f'<div class="row partial"><span class="ts">…</span><span class="badge {SPEAKER_CLS[role]}">{SPEAKER_NAME[role]}</span>'
                 f'<span class="txt">{html.escape(text)}</span></div>')
    if not rows:
        rows = f'<div class="row"><span class="txt" style="{MUTED}">Waiting for the first line. Speak, type, or play the next scripted line.</span></div>'
    if be.off_script and isinstance(be, ScriptedBackend):
        rows += f'<div class="row"><span class="txt" style="{MUTED}">{len(be.off_script)} line(s) did not match the script, so no flags can react to them.</span></div>'
    st.markdown(panel("Live Transcript", rows, pad=False), unsafe_allow_html=True)


def flag_row(f, when: str) -> str:
    ev = ""
    for e in f.evidence:
        if e.source == "transcript":
            ev += f'<br><small style="{MUTED}">Transcript, turn {e.ref}: “{html.escape(e.quote or "")}”</small>'
        elif e.source == "chart":
            ev += f'<br><small style="{MUTED}">Chart ({html.escape(e.ref)}): {html.escape(e.quote or "")}</small>'
        else:
            item = next((i for i in checklist.items if i.id == e.ref), None)
            ev += f'<br><small style="{MUTED}">Checklist: {html.escape(item.label if item else e.ref)}'
            if item and item.guideline_ref:
                ev += f" · {html.escape(item.guideline_ref)}"
            ev += "</small>"
    return (f'<div class="row"><span class="ts">{when}</span><span class="badge {TYPE_BADGE[f.type.value]}">{TYPE_LABEL[f.type.value].upper()}</span>'
            f'<span class="txt">{html.escape(f.rationale)}{ev}'
            f'<br><small style="{MUTED}">{"Verified" if f.verified else "Not verified (verifier unavailable)"}</small></span></div>')


def flags_panel() -> None:
    be = ss.be
    shown = [f for f in be.flags if not f.dismissed and ss.det[next(k for k, v in GAP_CHECKS.items() if v == f.type.value)]]
    order = ["missed_question", "unanswered_concern", "comprehension_breakdown", "chart_contradiction"]
    shown.sort(key=lambda f: order.index(f.type.value))
    items = "".join(flag_row(f, "end" if be.ended else f"t{f.raised_at_turn}") for f in shown)
    if not items:
        msg = ("No gaps found. This does not mean the visit was complete." if be.ended and not be.flags
               else "No flags. The tool stays quiet during the visit; only chart and comprehension badges appear.")
        items = f'<div class="row"><span class="txt" style="{MUTED}">{msg}</span></div>'
    st.markdown(panel("Flags & Live Suggestions", items, pad=False), unsafe_allow_html=True)

    if be.ended:
        if be.clarify:
            clar = "".join(f'<div class="row"><span class="txt">{i}. {html.escape(c)}</span></div>' for i, c in enumerate(be.clarify[:3], 1))
            st.markdown(panel("Before the patient leaves (max 3)", clar, pad=False), unsafe_allow_html=True)
        for f in shown:
            if st.button(f"Dismiss: {TYPE_LABEL[f.type.value]} · {f.rationale[:48]}", key=f"dis-{f.flag_id}"):
                be.dismiss(f.flag_id)
                refresh()


def patient_view() -> None:
    be, p = ss.be, profiles[ss.profile_id]
    if not be.ended:
        st.markdown(panel("Patient summary", f'<span style="{MUTED}">Your summary appears here when the visit ends.</span>'), unsafe_allow_html=True)
        return
    if not be.summary:
        st.markdown(panel("Patient summary", f'<span style="{MUTED}">The summary could not be written (model unavailable).</span>'), unsafe_allow_html=True)
        return
    g = f"{be.summary_grade:.1f}" if be.summary_grade is not None else "n/a"
    body = (f'<div style="font-size:1.15rem;line-height:1.6">{html.escape(be.summary).replace(chr(10), "<br>")}</div>'
            f'<small style="{MUTED}">Reading grade {g} (target {p.summary_target_grade:g} or lower) · {len(be.summary.split())} words (limit {p.summary_max_words})</small>')
    st.markdown(panel("Patient summary", body), unsafe_allow_html=True)
    read_aloud = f"""<button id=r style="font-size:18px;padding:8px 16px">🔊 Read aloud</button>
        <button id=s style="font-size:18px;padding:8px 16px">⏹ Stop</button>
        <script>const t={json.dumps(be.summary).replace("</", "<\\/")};
        document.getElementById('r').onclick=()=>{{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);u.rate=0.85;speechSynthesis.speak(u)}};
        document.getElementById('s').onclick=()=>speechSynthesis.cancel();</script>"""
    components.html(read_aloud, height=60)
    qs = ["In your own words, when do you come back to the clinic?", "What will you do if the pain gets worse?"]
    body = "".join(f'<div class="row"><span class="txt">{qs[i % 2]}</span></div>' for i in range(p.teach_back_questions))
    st.markdown(panel("Say it back", body, pad=False), unsafe_allow_html=True)


def evaluation_view() -> None:
    st.markdown('<div class="banner">Saved results from eval/results. This view only displays stored values; it never computes a score.</div>', unsafe_allow_html=True)
    files = sorted((ROOT / "eval" / "results").glob("*.json"))
    if not files:
        st.info("No saved results yet.")
    for fp in files:
        d = json.loads(fp.read_text())
        fake = str(d.get("model", "")).startswith("FAKE")
        with st.expander(f"{d['run_id']} · {d['split']} · {d['system']}" + (" · HARNESS CHECK, NOT ACCURACY" if fake else ""), expanded=not fake):
            rows = [{"type": k, **v} for k, v in {**d["per_type"], "overall": d["overall"]}.items()]
            st.dataframe(pd.DataFrame(rows).set_index("type"), width="stretch")
            st.caption(f"Visits: {d.get('n_visits')} · false flags per visit: {d.get('false_flags_per_visit')} · model: {d.get('model')} · mode: {d.get('mode')}")
    st.caption("Limits: synthetic data, hand-authored charts, no clinician review, small per-type counts, comprehension cues are our own draft.")


def input_controls() -> None:
    be = ss.be
    if be.ended:
        return
    mode = ss.input
    if mode != "Live mic":
        speaker = st.radio("Speaking now", ["clinician", "patient", "caregiver"], horizontal=True, key="speaker")
    if mode == "Typed":
        with st.form("typed", clear_on_submit=True):
            text = st.text_input("Type a line", key="typed_text")
            if st.form_submit_button("Send line"):
                add_turn(speaker, text)
                refresh()
    elif mode == "Browser mic":
        try:
            from streamlit_mic_recorder import speech_to_text

            spoken = speech_to_text(language="en", start_prompt="🎤 Speak", stop_prompt="⏹ Stop", just_once=True, key="mic")
            if spoken and spoken != ss.last_mic:
                ss.last_mic = spoken
                add_turn(speaker, spoken)
                refresh()
        except ImportError:
            st.caption("Browser mic needs `streamlit-mic-recorder`.")
    else:
        st.caption(f"Live capture: {stt.status}. Voices detected: {len(stt.speaker_role)} "
                   "(first = doctor, second = patient; until two are heard, roles are judged from the wording).")
        if stt.error:
            st.error(stt.error)


def right_panel() -> None:
    be = ss.be
    on = not be.ended
    st.markdown(f'<div class="orb-wrap"><div class="orb {"" if on else "off"}"></div>'
                f'<div class="orb-label {"" if on else "off"}">{"VISIT ACTIVE" if on else "VISIT ENDED"}</div></div>',
                unsafe_allow_html=True)

    st.markdown('<div class="side-h">Visit control</div>', unsafe_allow_html=True)
    if st.button("▶ Play next scripted line", key="play", disabled=be.ended, help="Rehearsal helper: sends the next prepared line"):
        pos = ss.script_pos
        if pos < len(script["turns"]):
            s = script["turns"][pos]
            add_turn(s["speaker"], s["text"])
            ss.script_pos = pos + 1
        refresh()
    a, b = st.columns(2)
    if a.button("■ End visit", key="end", type="primary", disabled=be.ended or not be.turns):
        with st.spinner("Wrapping up…"):
            be.end_visit()
        refresh()
    if b.button("↺ New visit", key="new"):
        start_visit()
        st.rerun()
    if ss.get("cfg") != (ss.kind, ss.profile_id, ss.mode):
        st.caption("Settings changed. Press New visit to apply.")

    st.markdown('<div class="side-h">Gap checks</div>', unsafe_allow_html=True)
    keys = list(ss.det)
    for row in (keys[:2], keys[2:]):
        for c, k in zip(st.columns(2), row):
            if c.button(k, key=f"det_{k}", type="primary" if ss.det[k] else "secondary"):
                ss.det[k] = not ss.det[k]
                refresh()

    st.markdown('<div class="side-h">Input source</div>', unsafe_allow_html=True)
    for c, lv in zip(st.columns(3), INPUTS):
        if c.button(lv, key=f"lv_{lv}", type="primary" if ss.input == lv else "secondary"):
            ss.input = lv
            st.rerun()  # full rerun: the live-mic iframe is added/removed outside the fragment
    if ss.input == "Live mic" and st.button("⇄ Swap doctor / patient", key="swap", help="Use if the labels came out backwards"):
        stt.swapped = not stt.swapped
        stt.reset_speakers()

    st.markdown('<div class="side-h">Backend</div>', unsafe_allow_html=True)
    st.radio("Backend", ["Scripted", "Engine"], horizontal=True, key="kind", label_visibility="collapsed",
             help="Scripted reacts only to the prepared script and needs no network. Engine runs the real agents.")
    st.radio("LLM mode", ["DEMO", "LIVE"], horizontal=True, key="mode", disabled=ss.kind != "Engine",
             help="Engine only. DEMO = cache only, no network. LIVE = Groq/Gemini/Ollama; slow on free tiers.")
    st.markdown('<div class="side-h">Patient profile</div>', unsafe_allow_html=True)
    st.selectbox("Profile", list(profiles), key="profile_id", format_func=lambda k: profiles[k].label, label_visibility="collapsed")
    st.markdown('<div class="side-h">View</div>', unsafe_allow_html=True)
    st.radio("View", ["Clinician", "Patient", "Evaluation"], horizontal=True, key="view", label_visibility="collapsed")
    st.markdown("&nbsp;")
    if st.button("← Product page", key="back"):
        ss.page = "landing"
        st.rerun()


def console() -> None:
    live = ss.input == "Live mic" and not ss.be.ended
    if live:
        stt.start()
        components.html(mic_html(), height=60)  # outside the fragment so it never remounts

    @st.fragment(run_every=1 if live else None)
    def body() -> None:
        be = ss.be
        if live:
            for role, text in stt.collect([(t.speaker, t.text) for t in be.turns]):
                add_turn(role, text)
        L, M, R = st.columns([4.2, 5.4, 2.6], gap="medium")
        with L:
            left_panel()
        with M:
            if ss.view == "Patient":
                patient_view()
            elif ss.view == "Evaluation":
                evaluation_view()
            else:
                phase = "Ended" if be.ended else ("In visit" if be.turns else "Not started")
                st.markdown(panel("Visit Status",
                    f'<div class="kv"><b>Backend</b><span>{ss.cfg[0]}{" · " + ss.cfg[2] if ss.cfg[0] == "Engine" else ""}</span></div>'
                    f'<div class="kv"><b>Input</b><span>{ss.input}</span></div>'
                    f'<div class="kv"><b>Profile</b><span>{html.escape(profiles[ss.cfg[1]].label)}</span></div>'
                    f'<div class="kv"><b>Turns</b><span>{len(be.turns)}</span></div>'
                    f'<div class="kv"><b>Phase</b><span>{phase}</span></div>'
                    + (f'<div class="kv"><b>Engine notes</b><span>{html.escape("; ".join(be.errors))}</span></div>' if be.errors else "")),
                    unsafe_allow_html=True)
                transcript_panel(live)
                input_controls()
                flags_panel()
        with R:
            right_panel()
        st.caption("Synthetic data only. Documentation check, not a diagnosis. Not a medical device.")

    body()


(landing if ss.page == "landing" else console)()

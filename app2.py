"""Dr.Listner live console (landing page is landing/index.html), wired to the real backends.

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
from src.stt_deepgram import LiveSTT, orb_html

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Dr.Listner", page_icon=str(ROOT / "landing" / "logo" / "favicon.ico"), layout="wide", initial_sidebar_state="collapsed")

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
INPUTS = ["Typed", "Browser mic"]  # fallbacks; the orb is the live (Deepgram) capture
MUTED = "color:var(--muted)"

# ------------------------------------------------------------------- styling
THEMES = {
    "light": "--bg:#e6f2ec;--card:#fff;--ink:#12332f;--ink2:#25504a;--muted:#7f968f;--muted2:#5d7a73;--line:#cfe3da;--line2:#e5f0eb;--tile:#f0f8f4;--chip:#dcefe7;--accent2:#0B6E6E;--ts:#3e8f87;--hit:#fff1ec;--warnbg:#fdece6;--warntx:#b24a2f;--pribg:#d6efe7;--pribd:#7cc4b8;--pritx:#0B6E6E;--banbg:#fff6dd;--banbd:#f0d98a;--bantx:#7a5d00;",
    "dark": "--bg:#0f1524;--card:#182036;--ink:#e6ebf7;--ink2:#c3cce4;--muted:#7f8aa8;--muted2:#98a3c0;--line:#2a3554;--line2:#222c47;--tile:#1f2944;--chip:#26335a;--accent2:#9db4ff;--ts:#8fa6ff;--hit:#3a1f26;--warnbg:#3d1f24;--warntx:#ff9a8f;--pribg:#12344a;--pribd:#2a7fa8;--pritx:#7fd0f5;--banbg:#3a3114;--banbd:#6b5a1f;--bantx:#f1d27a;",
}
theme = "dark" if st.session_state.get("dark") else "light"
st.markdown("<style>:root{" + THEMES[theme] + "}</style>", unsafe_allow_html=True)
st.markdown("""
<style>
#MainMenu, header, footer {visibility:hidden;}
.stApp {background:var(--bg); color:var(--ink);}
.stApp h1,.stApp h2,.stApp h3,.stApp label,.stApp p,.stApp li,[data-testid="stCaptionContainer"],div[role="radiogroup"] label p {color:var(--ink);}
.hero h1,.hero p {color:#fff;} .hero p {color:#d8e0ff;}
[data-baseweb="select"] > div,[data-baseweb="input"] > div,[data-baseweb="base-input"] {background:var(--card) !important; color:var(--ink) !important;}
[data-baseweb="select"] *,[data-baseweb="input"] input {color:var(--ink) !important;}
[data-testid="stForm"] {border-color:var(--line);}
.block-container {padding-top:1rem; max-width:1700px;}
.panel {background:var(--card); border:1px solid var(--line); border-radius:6px; margin-bottom:14px; overflow:hidden;}
.panel-h {padding:14px 20px; font-size:.78rem; font-weight:700; letter-spacing:.12em;
          color:var(--ink); border-bottom:1px solid var(--line2); text-transform:uppercase;}
.panel-b {padding:14px 20px; font-size:.92rem; color:var(--ink2);}
.row {display:flex; gap:12px; padding:9px 20px; border-bottom:1px solid var(--line2); align-items:flex-start; font-size:.9rem;}
.row.partial {opacity:.55; font-style:italic;}
.ts {color:var(--ts); font-size:.78rem; min-width:34px; padding-top:2px;}
.badge {font-size:.64rem; font-weight:700; color:#fff; padding:3px 8px; border-radius:3px; letter-spacing:.05em; min-width:72px; text-align:center;}
.doc{background:#2f6b57;} .pat{background:#4a5fa8;} .care{background:#b9702a;}
.flag-chart{background:#c0392b;} .flag-comp{background:#d68910;} .flag-gap{background:#0B6E6E;} .flag-conc{background:#8e44ad;}
.txt {flex:1; color:var(--ink);}
.kv {display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed var(--line2);}
.kv b {font-size:.72rem; letter-spacing:.1em; color:var(--accent2); text-transform:uppercase;}
.tile {display:inline-block; width:48%; background:var(--tile); border-radius:6px; padding:10px 12px; margin:0 1% 8px 0;}
.tile small{display:block; color:var(--muted2); font-size:.7rem; letter-spacing:.1em; text-transform:uppercase;}
.tile span{font-size:1.15rem; font-weight:600; color:var(--ink);}
.chip {display:inline-block; background:var(--chip); color:var(--accent2); border-radius:12px; padding:2px 10px; font-size:.75rem; margin:2px 4px 2px 0;}
.chip.warn{background:var(--warnbg); color:var(--warntx);}
.tick{padding:3px 0; font-size:.88rem;} .ok{color:#2f6b57;} .miss{color:var(--muted);} .miss-final{color:#c0392b; font-weight:600;}
.banner{background:var(--banbg); border:1px solid var(--banbd); color:var(--bantx); padding:6px 14px; border-radius:6px; font-size:.78rem; margin-bottom:10px;}
.orb-wrap{text-align:center; padding:14px 0 6px;}
.orb{width:120px; height:120px; border-radius:50%; margin:0 auto;
     background:radial-gradient(circle at 35% 30%, #fff, #bfe6dc 45%, #0B6E6E);
     box-shadow:0 0 30px rgba(11,110,110,.5); animation:pulse 2.2s ease-in-out infinite;}
.orb.off{background:radial-gradient(circle at 35% 30%, #fff, #d9dde6 55%, #aab1c2); box-shadow:none; animation:none;}
@keyframes pulse{0%,100%{transform:scale(1); box-shadow:0 0 22px rgba(11,110,110,.4);}50%{transform:scale(1.07); box-shadow:0 0 44px rgba(11,110,110,.75);}}
.orb-label{margin-top:10px; letter-spacing:.15em; font-weight:700; color:#0B6E6E;} .orb-label.off{color:var(--muted);}
.side-h{font-size:.72rem; font-weight:700; letter-spacing:.14em; color:var(--ink); margin:14px 0 6px; text-transform:uppercase;}
div[data-testid="stButton"] button {width:100%; border-radius:6px; border:1px solid var(--line); background:var(--card); color:var(--ink); font-size:.85rem; min-height:48px;}
div[data-testid="stButton"] button[kind="primary"] {background:var(--pribg); border-color:var(--pribd); color:var(--pritx);}
.hero{background:linear-gradient(135deg,var(--ink),#3b4f9a); color:#fff; padding:44px 40px; border-radius:10px; margin-bottom:18px;}
.hero h1{margin:0 0 8px; font-size:2.4rem; color:#fff;} .hero p{font-size:1.05rem; color:#d8e0ff; max-width:760px;}
.card{background:var(--card); border:1px solid var(--line); border-radius:8px; padding:18px 20px; height:100%;}
.card h4{margin:0 0 6px; color:var(--ink);} .card p{margin:0; color:var(--ink2); font-size:.9rem;}
.hit{background:var(--hit);}
.scroll{height:430px; overflow-y:auto; display:flex; flex-direction:column-reverse;}  /* column-reverse keeps it pinned to the newest line */
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------- data
@st.cache_resource
def _static():
    profs = {k: v for k, v in load_profiles().items() if not v.caregiver_present}  # mock visit has no caregiver
    return load_checklist(), profs, load_chart(), load_script()


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


DEV = st.query_params.get("dev") == "1"  # ?dev=1 brings back the rehearsal and debug controls
ss.setdefault("kind", os.environ.get("DRL_BACKEND", "Scripted"))  # Scripted | Engine
ss.setdefault("mode", os.environ.get("DRL_MODE", "DEMO"))  # Engine only: DEMO (cache) | LIVE
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


# --------------------------------------------------------------------- console
def left_panel() -> None:
    be, p = ss.be, profiles[ss.profile_id]
    by_type: dict[str, list[str]] = {}
    for e in chart.entries:
        by_type.setdefault(e.resource_type, []).append(e.display)
    cited = {e.ref for f in be.flags for e in f.evidence if e.source == "chart"}
    cited_names = [e.display for e in chart.entries if e.entry_id in cited]
    tiles = [("Age", str(chart.age)), ("Sex", chart.sex.title()), ("Hearing", p.hearing_level.title()), ("Literacy", p.literacy.title())]
    tile_html = "".join(f'<div class="tile"><small>{k}</small><span>{html.escape(v)}</span></div>' for k, v in tiles)
    body = (f'<div style="font-size:1.25rem;font-weight:700;color:var(--ink)">{chart.age}-year-old {chart.sex}</div>'
            f'<div style="color:var(--muted2);margin-bottom:10px">{html.escape(p.label)} · synthetic chart</div>'
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
    rows += '<div style="margin-top:8px;font-size:.72rem;color:var(--muted)">2021 AHA/ACC chest pain guideline; matched by Claude, not clinician-reviewed.</div>'
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
    st.markdown(panel("Live Transcript", f'<div class="scroll"><div>{rows}</div></div>', pad=False), unsafe_allow_html=True)


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
    mode = ss.input if DEV else "Typed"
    if not DEV:
        with st.expander("Type instead"):
            speaker = st.radio("Speaking now", ["clinician", "patient"], horizontal=True, key="speaker")
            with st.form("typed", clear_on_submit=True):
                text = st.text_input("Type a line", key="typed_text")
                if st.form_submit_button("Send line"):
                    add_turn(speaker, text)
                    refresh()
        return
    speaker = st.radio("Speaking now (typed / browser mic)", ["clinician", "patient"], horizontal=True, key="speaker")
    if mode == "Typed":
        with st.form("typed", clear_on_submit=True):
            text = st.text_input("Type a line", key="typed_text")
            if st.form_submit_button("Send line"):
                add_turn(speaker, text)
                refresh()
    else:
        try:
            from streamlit_mic_recorder import speech_to_text

            spoken = speech_to_text(language="en", start_prompt="🎤 Speak", stop_prompt="⏹ Stop", just_once=True, key="mic")
            if spoken and spoken != ss.last_mic:
                ss.last_mic = spoken
                add_turn(speaker, spoken)
                refresh()
        except ImportError:
            st.caption("Browser mic needs `streamlit-mic-recorder`.")


def right_panel() -> None:
    be = ss.be
    on = not be.ended
    st.markdown('<div class="side-h">Visit control</div>', unsafe_allow_html=True)
    if DEV and st.button("▶ Play next scripted line", key="play", disabled=be.ended, help="Rehearsal helper: sends the next prepared line"):
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
        st.rerun()  # full rerun: removes the orb, which closes the mic
    if b.button("↺ New visit", key="new"):
        start_visit()
        st.rerun()
    # Swap button hidden for now; re-enable if speaker labels come out backwards.
    # if st.button("⇄ Swap doctor / patient", key="swap", help="Use if the speaker labels came out backwards"):
    #     stt.swapped = not stt.swapped
    #     stt.reset_speakers()

    st.markdown('<div class="side-h">Patient</div>', unsafe_allow_html=True)
    st.selectbox("Profile", list(profiles), key="profile_id", format_func=lambda k: profiles[k].label, label_visibility="collapsed")
    st.markdown('<div class="side-h">View</div>', unsafe_allow_html=True)
    st.radio("View", ["Clinician", "Patient"] + (["Evaluation"] if DEV else []), horizontal=True, key="view", label_visibility="collapsed")
    if ss.get("_view_seen", ss.view) != ss.view:  # the main panels live in another fragment, so redraw the whole page
        ss._view_seen = ss.view
        st.rerun()
    ss._view_seen = ss.view

    if DEV:
        st.markdown('<div class="side-h">Dev: gap checks</div>', unsafe_allow_html=True)
        keys = list(ss.det)
        for row in (keys[:2], keys[2:]):
            for c, k in zip(st.columns(2), row):
                if c.button(k, key=f"det_{k}", type="primary" if ss.det[k] else "secondary"):
                    ss.det[k] = not ss.det[k]
                    st.rerun()
        st.markdown('<div class="side-h">Dev: input source</div>', unsafe_allow_html=True)
        for c, lv in zip(st.columns(2), INPUTS):
            if c.button(lv, key=f"lv_{lv}", type="primary" if ss.input == lv else "secondary"):
                ss.input = lv
                st.rerun()
        st.markdown('<div class="side-h">Dev: backend</div>', unsafe_allow_html=True)
        st.radio("Backend", ["Scripted", "Engine"], horizontal=True, key="kind", label_visibility="collapsed",
                 help="Scripted reacts only to the prepared script and needs no network. Engine runs the real agents.")
        st.radio("LLM mode", ["DEMO", "LIVE"], horizontal=True, key="mode", disabled=ss.kind != "Engine",
                 help="Engine only. DEMO = cache only, no network. LIVE = Groq/Gemini/Ollama; slow on free tiers.")
        if ss.get("cfg") != (ss.kind, ss.profile_id, ss.mode):
            st.caption("Settings changed. Press New visit to apply.")


def console() -> None:
    live = not ss.be.ended
    main_col, side_col = st.columns([9.6, 2.6], gap="medium")

    @st.fragment(run_every=1 if live else None)
    def main() -> None:
        be = ss.be
        if live and not be.ended:
            for role, text in stt.collect([(t.speaker, t.text) for t in be.turns]):
                add_turn(role, text)
        L, M = st.columns([4.2, 5.4], gap="medium")
        with L:
            left_panel()
        with M:
            if ss.view == "Patient":
                patient_view()
            elif ss.view == "Evaluation":
                evaluation_view()
            else:
                if DEV:
                    phase = "Ended" if be.ended else ("In visit" if be.turns else "Not started")
                    capture = f"{stt.status} · {len(stt.speaker_role)} voice(s)" if stt.status != "idle" else "idle"
                    st.markdown(panel("Visit Status (dev)",
                        f'<div class="kv"><b>Backend</b><span>{ss.cfg[0]}{" · " + ss.cfg[2] if ss.cfg[0] == "Engine" else ""}</span></div>'
                        f'<div class="kv"><b>Live capture</b><span>{capture}</span></div>'
                        f'<div class="kv"><b>Turns</b><span>{len(be.turns)}</span></div>'
                        f'<div class="kv"><b>Phase</b><span>{phase}</span></div>'
                        + (f'<div class="kv"><b>Engine notes</b><span>{html.escape("; ".join(be.errors))}</span></div>' if be.errors else "")),
                        unsafe_allow_html=True)
                if stt.error:
                    st.error(stt.error)
                transcript_panel(live)
                input_controls()
                flags_panel()
        st.caption("Synthetic data only. Documentation check, not a diagnosis. Not a medical device.")

    @st.fragment(run_every=1 if live else None)
    def side() -> None:
        right_panel()

    with side_col:
        if live:
            stt.start()
            components.html(orb_html(bool(ss.get("dark"))), height=170)  # outside the fragments so it never remounts
            st.caption("Tap the orb to start live captions. First voice heard is the doctor, the second the patient.")
        else:
            st.markdown('<div class="orb-wrap"><div class="orb off"></div><div class="orb-label off">VISIT ENDED</div></div>', unsafe_allow_html=True)
        side()
    with main_col:
        main()


_logo, _tog = st.columns([9, 1], vertical_alignment="center")
_logo.image(str(ROOT / "landing" / "logo" / ("dr-listener-logo-dark.svg" if ss.get("dark") else "dr-listener-logo.svg")), width=190)
_tog.toggle("🌙 Dark", key="dark")
console()

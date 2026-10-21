"""Dr.Listner Streamlit demo. Synthetic data only; not a medical device.

Run: streamlit run app.py
Backends: Scripted (hardcoded, safe on stage) or Engine (real agents on the LLM cache or live providers).
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from demo.backend import EngineBackend, ScriptedBackend, load_chart, load_flag_plan, load_script
from src import config
from src.stt_deepgram import LiveSTT, mic_html
from src.pack import load_checklist, load_profiles
from src.schemas import PlanItem

ROOT = Path(__file__).resolve().parent
TYPE_LABEL = {
    "missed_question": "Question not asked",
    "unanswered_concern": "Worry not answered",
    "chart_contradiction": "Conflicts with chart",
    "comprehension_breakdown": "Not understood / not repaired",
}
TYPE_ICON = {"missed_question": "❓", "unanswered_concern": "💬", "chart_contradiction": "📋", "comprehension_breakdown": "👂"}

st.set_page_config(page_title="Dr.Listner", page_icon="🩺", layout="wide")


@st.cache_resource
def _stt() -> LiveSTT:
    return LiveSTT()


@st.cache_resource
def _static():
    return load_checklist(), load_profiles(), load_chart(), load_script()


def new_backend(kind: str, profile_id: str, mode: str):
    checklist, profiles, chart, script = _static()
    args = (script["visit_id"], chart, checklist, profiles[profile_id])
    if kind == "Scripted (hardcoded demo)":
        return ScriptedBackend(*args)
    from src.llm.client import LLMClient

    plan = [PlanItem(**p) for p in load_flag_plan()["plan_items"]]
    return EngineBackend(*args, llm=LLMClient(mode=config.Mode(mode)), plan_items=plan)


# ---------- sidebar ----------
checklist, profiles, chart, script = _static()
stt = _stt()
with st.sidebar:
    st.title("🩺 Dr.Listner")
    kind = st.radio("Backend", ["Scripted (hardcoded demo)", "Engine (real agents)"], help="Scripted reacts only to the prepared script and needs no network.")
    mode = "DEMO"
    if kind.startswith("Engine"):
        mode = st.radio("LLM mode", ["DEMO", "LIVE"], help="DEMO = cache only, no network. LIVE = Groq/Gemini/Ollama; slow on free tiers.")
    profile_id = st.selectbox("Patient profile", list(profiles), format_func=lambda k: profiles[k].label)
    p = profiles[profile_id]
    st.caption(f"Hearing: {p.hearing_level} · Literacy: {p.literacy} · Caregiver: {'yes' if p.caregiver_present else 'no'}")
    if st.button("Start new visit", width="stretch") or "be" not in st.session_state:
        st.session_state.be = new_backend(kind, profile_id, mode)
        st.session_state.cfg = (kind, profile_id, mode)
        st.session_state.script_pos = 0
        st.session_state.last_mic = None
        stt.reset_speakers()
    if st.session_state.get("cfg") != (kind, profile_id, mode):
        st.info("Settings changed. Press Start new visit to apply.")
    be = st.session_state.be
    st.divider()
    st.subheader("Reading view")
    font = st.slider("Text size", 16, 36, 20)
    contrast = st.checkbox("High contrast")
    st.divider()
    if be.errors:
        st.warning("Engine notes: " + "; ".join(be.errors))
    st.caption("Synthetic data only. Documentation check, not a diagnosis. Not a medical device.")

st.markdown(
    f"""<style>
    .big {{ font-size: {font}px; line-height: 1.5; }}
    .turn {{ padding: 8px 12px; border-radius: 10px; margin: 6px 0; }}
    .clinician {{ background: rgba(60,130,246,.12); margin-right: 22%; }}
    .patient {{ background: rgba(34,160,90,.14); margin-left: 22%; text-align: right; }}
    .caregiver {{ background: rgba(200,140,30,.14); margin-left: 22%; text-align: right; }}
    .partial {{ opacity: .55; font-style: italic; }}
    .hit {{ outline: 2px solid #d9534f; }}
    {'.stApp{background:#000;color:#fff} .big{color:#fff}' if contrast else ''}
    </style>""",
    unsafe_allow_html=True,
)
st.warning("Synthetic demo. Dr.Listner checks documentation completeness only. It does not diagnose or recommend treatment.", icon="⚠️")

tab_live, tab_wrap, tab_patient, tab_eval = st.tabs(["Live visit", "Wrap-up", "Patient view", "Evaluation"])


def add_turn(speaker: str, text: str):
    if text and text.strip() and not be.ended:
        be.add_turn(speaker, text)


def flagged_turns() -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for f in be.flags:
        for e in f.evidence:
            if e.source == "transcript":
                out.setdefault(int(e.ref), []).append(TYPE_ICON[f.type.value])
    return out


# ---------- live visit ----------
with tab_live:
    left, mid, right = st.columns([5, 3, 3])
    with left:
        st.subheader("Conversation")
        live_on = st.session_state.get("input_mode") == "Live mic (Deepgram)"

        @st.fragment(run_every=1 if live_on else None)
        def conversation():
            if live_on:
                got = False
                while not stt.finals.empty():
                    role, text = stt.finals.get()
                    add_turn(role, text)
                    got = True
                if got:
                    st.rerun()  # full rerun so flags and checklist react to the new turns
            marks = flagged_turns()
            if not be.turns and not (live_on and stt.partial):
                st.caption("Waiting for the first line. Speak or type below.")
            for t in be.turns:
                badge = "".join(marks.get(t.idx, []))
                cls = "hit" if t.idx in marks else ""
                st.markdown(
                    f'<div class="turn {t.speaker} {cls} big"><b>{t.speaker.title()}</b> '
                    f'<small>#{t.idx}</small> {badge}<br>{html.escape(t.text)}</div>',
                    unsafe_allow_html=True,
                )
            if live_on and stt.partial:
                role, text = stt.partial
                st.markdown(
                    f'<div class="turn {role} partial big"><b>{role.title()}</b> …<br>{html.escape(text)}</div>',
                    unsafe_allow_html=True,
                )

        conversation()
        if be.off_script and isinstance(be, ScriptedBackend):
            st.caption(f"{len(be.off_script)} line(s) did not match the script, so no flags can react to them.")
        if not be.ended:
            input_mode = st.radio("Input", ["Type / browser mic", "Live mic (Deepgram)"], horizontal=True, key="input_mode")
            if input_mode == "Live mic (Deepgram)":
                stt.start()
                components.html(mic_html(), height=60)
                k1, k2 = st.columns([1, 3])
                if k1.button("⇄ Swap roles", help="Use if the doctor and patient labels came out backwards"):
                    stt.swapped = not stt.swapped
                    stt.reset_speakers()
                k2.caption(f"Status: {stt.status}. First voice heard = clinician, second = patient.")
                if stt.error:
                    st.error(stt.error)
            speaker = st.radio("Speaking now", ["clinician", "patient"], horizontal=True, key="speaker")
            c1, c2 = st.columns([4, 1])
            with c1, st.form("typed", clear_on_submit=True):
                text = st.text_input("Type a line (fallback to the microphone)", key="typed_text")
                if st.form_submit_button("Send line"):
                    add_turn(speaker, text)
                    st.rerun()
            with c2:
                try:
                    from streamlit_mic_recorder import speech_to_text

                    spoken = speech_to_text(language="en", start_prompt="🎤 Speak", stop_prompt="⏹ Stop", just_once=True, key="mic")
                    if spoken and spoken != st.session_state.last_mic:
                        st.session_state.last_mic = spoken
                        add_turn(speaker, spoken)
                        st.rerun()
                except ImportError:
                    st.caption("Mic needs `streamlit-mic-recorder`.")
            r1, r2 = st.columns(2)
            if r1.button("▶ Play next scripted line", help="Rehearsal helper: sends the next prepared line"):
                pos = st.session_state.script_pos
                if pos < len(script["turns"]):
                    s = script["turns"][pos]
                    add_turn(s["speaker"], s["text"])
                    st.session_state.script_pos = pos + 1
                    st.rerun()
            if r2.button("■ End visit", type="primary", disabled=not be.turns):
                with st.spinner("Wrapping up…"):
                    be.end_visit()
                st.rerun()
        else:
            st.success("Visit ended. Open the Wrap-up and Patient view tabs.")
    with mid:
        st.subheader("Red-flag checklist")
        for it in checklist.items:
            at = be.coverage.get(it.id)
            if at is not None:
                st.markdown(f"✅ **{it.label}** · turn {at}")
            elif be.ended and (be.coverage or isinstance(be, ScriptedBackend)):
                st.markdown(f"⚠️ **{it.label}** · not asked")
            else:
                st.markdown(f"⬜ {it.label}")
        st.caption("Items are from the 2021 AHA/ACC chest pain guideline; matched by Claude, not clinician-reviewed.")
    with right:
        st.subheader("Chart")
        cited = {e.ref for f in be.flags for e in f.evidence if e.source == "chart"}
        st.caption(f"{chart.age}-year-old {chart.sex} · synthetic")
        for e in chart.entries:
            mark = "🔴 " if e.entry_id in cited else ""
            st.markdown(f"{mark}**{e.display}** · {e.resource_type} · {e.status}")
        live = [f for f in be.flags if f.type.value in live_types]
        if live and not be.ended:
            st.subheader("Heads-up")
            for f in live:
                st.info(f"{TYPE_ICON[f.type.value]} {TYPE_LABEL[f.type.value]} (turn {f.raised_at_turn})")

# ---------- wrap-up ----------
with tab_wrap:
    if not be.ended:
        st.info("The gaps list appears when the visit ends. Missed questions and unanswered worries are never raised earlier.")
    else:
        flags = [f for f in be.flags if not f.dismissed]
        order = ["missed_question", "unanswered_concern", "comprehension_breakdown", "chart_contradiction"]
        c = st.columns(3)
        c[0].metric("Gaps flagged", len(flags))
        c[1].metric("Dismissed", len([f for f in be.flags if f.dismissed]))
        c[2].metric("Raised too early", 0, help="Types 1 and 2 are only raised after the last turn.")
        if not be.flags:
            st.success("No gaps found. This does not mean the visit was complete.")
        for ty in order:
            for f in [f for f in be.flags if f.type.value == ty]:
                with st.container(border=True):
                    st.markdown(f"### {TYPE_ICON[ty]} {TYPE_LABEL[ty]}" + ("  ·  *dismissed*" if f.dismissed else ""))
                    st.write(f.rationale)
                    for e in f.evidence:
                        if e.source == "transcript":
                            st.caption(f"Transcript, turn {e.ref}: “{e.quote}”")
                        elif e.source == "chart":
                            st.caption(f"Chart ({e.ref}): {e.quote}")
                        else:
                            item = next((i for i in checklist.items if i.id == e.ref), None)
                            st.caption(f"Checklist: {item.label if item else e.ref}")
                            if item and item.guideline_ref:
                                st.caption(f"Guideline: {item.guideline_ref}")
                    st.caption("Verified" if f.verified else "Not verified (verifier unavailable)")
                    if not f.dismissed and st.button("Dismiss", key=f"d-{f.flag_id}"):
                        be.dismiss(f.flag_id)
                        st.rerun()
        if be.clarify:
            st.subheader("Before the patient leaves")
            for line in be.clarify[:3]:
                st.markdown(f"- {line}")

# ---------- patient view ----------
with tab_patient:
    if not be.ended:
        st.info("Your summary appears here when the visit ends.")
    elif not be.summary:
        st.warning("The summary could not be written (model unavailable).")
    else:
        st.markdown(f'<div class="big">{html.escape(be.summary).replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
        words = len(be.summary.split())
        g = f"{be.summary_grade:.1f}" if be.summary_grade is not None else "n/a"
        st.caption(f"Reading grade {g} (target {p.summary_target_grade:g} or lower) · {words} words (limit {p.summary_max_words})")
        read_aloud = f"""<button id=r style="font-size:20px;padding:10px 18px">🔊 Read aloud</button>
            <button id=s style="font-size:20px;padding:10px 18px">⏹ Stop</button>
            <script>const t={json.dumps(be.summary).replace("</", "<\\/")};
            document.getElementById('r').onclick=()=>{{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);u.rate=0.85;speechSynthesis.speak(u)}};
            document.getElementById('s').onclick=()=>speechSynthesis.cancel();</script>"""
        if hasattr(st, "iframe"):  # components.v1.html is deprecated in current Streamlit
            st.iframe(read_aloud, height=70)
        else:
            components.html(read_aloud, height=70)
        st.subheader("Say it back")
        for i in range(p.teach_back_questions):
            st.markdown(["- In your own words, when do you come back to the clinic?", "- What will you do if the pain gets worse?"][i % 2])

# ---------- evaluation ----------
with tab_eval:
    st.caption("Saved results from eval/results. This tab only displays stored values; it never computes a score.")
    files = sorted((ROOT / "eval" / "results").glob("*.json"))
    if not files:
        st.info("No saved results yet.")
    for fp in files:
        d = json.loads(fp.read_text())
        fake = str(d.get("model", "")).startswith("FAKE")
        with st.expander(f"{d['run_id']} · {d['split']} · {d['system']}" + (" · HARNESS CHECK, NOT ACCURACY" if fake else ""), expanded=not fake):
            rows = [{"type": k, **v} for k, v in {**d["per_type"], "overall": d["overall"]}.items()]
            df = pd.DataFrame(rows).set_index("type")
            st.dataframe(df, width="stretch")
            st.caption(f"Visits: {d.get('n_visits')} · false flags per visit: {d.get('false_flags_per_visit')} · model: {d.get('model')} · mode: {d.get('mode')}")
    st.caption("Limits: synthetic data, hand-authored charts, no clinician review, small per-type counts, comprehension cues are our own draft.")

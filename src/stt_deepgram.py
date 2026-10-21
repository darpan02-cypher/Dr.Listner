"""Live speech-to-text via Deepgram, with speaker diarization.

Browser mic -> ws://127.0.0.1:PORT (this module) -> Deepgram. The API key stays on the server.
Finished utterances land in `LiveSTT.finals`; the app drains them into `Backend.add_turn`.
Role mapping: the first voice heard is the clinician, the second the patient, the third the caregiver.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

PORT = int(os.environ.get("STT_PORT", "8765"))
ROLES = ["clinician", "patient", "caregiver"]
IDLE_FLUSH_S = 2.5
ANSWER_START = re.compile(r"^(no|nope|yes|yeah|yep|okay|ok|oh|well|sure)\b[.,!]", re.I)


def _url() -> str:
    q = {
        "model": os.environ.get("DEEPGRAM_MODEL", "nova-3"),
        "language": "en",
        "diarize": "true",
        "smart_format": "true",
        "interim_results": "true",
        "endpointing": "700",
        "encoding": "linear16",
        "sample_rate": "16000",
        "channels": "1",
    }
    return "wss://api.deepgram.com/v1/listen?" + urlencode(q)


@dataclass
class LiveSTT:
    finals: queue.Queue = field(default_factory=queue.Queue)  # (role, text)
    partial: tuple[str, str] | None = None
    status: str = "idle"
    error: str = ""
    speaker_role: dict[int, str] = field(default_factory=dict)
    swapped: bool = False
    started: bool = False
    pending: str = ""  # fragments waiting to form a full sentence
    pending_role: str = ""
    pending_ts: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def role_for(self, speaker: int) -> str:
        with self._lock:
            if speaker not in self.speaker_role:
                self.speaker_role[speaker] = ROLES[min(len(self.speaker_role), len(ROLES) - 1)]
            role = self.speaker_role[speaker]
        if self.swapped and role in ("clinician", "patient"):
            role = "patient" if role == "clinician" else "clinician"
        return role

    def reset_speakers(self) -> None:
        with self._lock:
            self.speaker_role.clear()
        self.partial = None

    def collect(self, history: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Merge raw fragments into whole utterances; return the (role, text) turns that are ready.

        A turn is released when the text ends a sentence (. ? !) or the speaker has paused for IDLE_FLUSH_S.
        """
        ready: list[tuple[str, str]] = []
        hist = list(history)

        def release():
            text, first_role = self.pending.strip(), self.pending_role
            self.pending, self.pending_role = "", ""
            if not text:
                return
            role = first_role
            if len(self.speaker_role) < 2:  # diarization has only heard one voice: judge from wording and context
                role = classify_role(hist, text) or ("clinician" if text.endswith("?") else first_role)
            hist.append((role, text))
            ready.append((role, text))

        while not self.finals.empty():
            role, text = self.finals.get()
            if self.pending and len(self.speaker_role) >= 2 and role != self.pending_role:
                release()  # diarization says a different voice started talking
            if self.pending and ANSWER_START.match(text):
                release()  # "No. ..." / "Yes, ..." after an unfinished line is a reply from the other person
            if not self.pending:
                self.pending_role = role
            self.pending = f"{self.pending} {text}".strip()
            self.pending_ts = time.time()
            if self.pending[-1] in ".?!":
                release()
        if self.pending and time.time() - self.pending_ts > IDLE_FLUSH_S:
            release()
        return ready

    # ---- Deepgram message handling ----
    def _runs(self, words: list[dict]) -> list[tuple[int, str]]:
        runs: list[tuple[int, list[str]]] = []
        for w in words:
            sp = int(w.get("speaker", 0))
            tok = w.get("punctuated_word") or w.get("word", "")
            if runs and runs[-1][0] == sp:
                runs[-1][1].append(tok)
            else:
                runs.append((sp, [tok]))
        return [(sp, " ".join(t)) for sp, t in runs]

    def on_result(self, msg: dict) -> None:
        if msg.get("type") != "Results":
            return
        alt = (msg.get("channel", {}).get("alternatives") or [{}])[0]
        words = alt.get("words") or []
        if not words:
            return
        runs = self._runs(words)
        if msg.get("is_final"):
            for sp, text in runs:
                self.finals.put((self.role_for(sp), text))
            self.partial = None
        else:
            sp, text = runs[-1]
            self.partial = (self.role_for(sp), text)

    async def _handle(self, browser) -> None:
        key = os.environ.get("DEEPGRAM_API_KEY", "")
        if not key:
            self.error = "DEEPGRAM_API_KEY is not set."
            return
        self.status, self.error = "connecting", ""
        try:
            async with connect(_url(), additional_headers={"Authorization": f"Token {key}"}) as dg:
                self.status = "listening"

                async def up():
                    async for chunk in browser:
                        if isinstance(chunk, bytes):
                            await dg.send(chunk)
                    await dg.send(json.dumps({"type": "CloseStream"}))

                async def down():
                    async for raw in dg:
                        self.on_result(json.loads(raw))

                t_up, t_down = asyncio.create_task(up()), asyncio.create_task(down())
                await asyncio.wait({t_up, t_down}, return_when=asyncio.FIRST_COMPLETED)
                t_up.cancel()
                t_down.cancel()
        except Exception as e:  # network, auth (401), bad audio format
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self.status, self.partial = "idle", None

    def start(self) -> None:
        if self.started:
            return
        self.started = True

        def run():
            async def main():
                async with serve(self._handle, "127.0.0.1", PORT):
                    await asyncio.Future()

            try:
                asyncio.run(main())
            except OSError as e:
                self.error = f"Cannot open port {PORT}: {e}"
                self.started = False

        threading.Thread(target=run, daemon=True, name="deepgram-stt").start()


def classify_role(history: list[tuple[str, str]], text: str) -> str | None:
    """Judge who spoke `text` (clinician or patient) from the wording and the conversation so far.

    Used when diarization has heard only one voice. Returns None if the call fails.
    """
    import requests

    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        return None
    ctx = "\n".join(f"{r}: {t}" for r, t in history[-8:]) or "(start of visit)"
    prompt = (
        "A doctor-patient visit is transcribed from ONE microphone, so speakers are guessed. "
        "Decide who said the NEW line.\n"
        "- The clinician asks about symptoms, duration, severity, medicines, lifestyle; examines; explains; instructs.\n"
        "- The patient describes their own symptoms, answers questions, and voices worries or limitations.\n"
        "- A question is almost always the clinician; an answer to the previous question comes from the OTHER speaker.\n"
        "- A line that continues the previous line's thought (same sentence, same topic) is the same speaker.\n"
        "Reply with exactly one word: clinician or patient.\n\n"
        f"Conversation so far (earlier labels may contain mistakes):\n{ctx}\n\nNEW line: {text}"
    )
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": os.environ.get("ROLE_MODEL", "openai/gpt-oss-20b"), "temperature": 0,
                  "reasoning_effort": "low", "messages": [{"role": "user", "content": prompt}]},
            timeout=10,
        )
        ans = r.json()["choices"][0]["message"]["content"].strip().lower()
    except Exception:
        return None
    return "clinician" if ans.startswith("clin") else "patient" if ans.startswith("pat") else None


MIC_HTML = """
<div style="font-family:system-ui;display:flex;gap:10px;align-items:center">
  <button id="b" style="padding:8px 16px;font-size:16px;border-radius:8px;border:1px solid #888;cursor:pointer">🎤 Start live capture</button>
  <span id="s" style="font-size:14px;color:#666">idle</span>
</div>
<script>
const PORT = __PORT__;
let ws, ctx, proc, stream, on = false;
const b = document.getElementById('b'), s = document.getElementById('s');
function down(buf, inRate) {
  const r = inRate / 16000, n = Math.floor(buf.length / r), out = new Int16Array(n);
  for (let i = 0; i < n; i++) { const v = Math.max(-1, Math.min(1, buf[Math.floor(i * r)])); out[i] = v < 0 ? v * 0x8000 : v * 0x7fff; }
  return out.buffer;
}
async function start() {
  try { stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}}); }
  catch (e) { s.textContent = 'Mic blocked: ' + e.message; return; }
  ws = new WebSocket('ws://127.0.0.1:' + PORT);
  ws.binaryType = 'arraybuffer';
  ws.onerror = () => { s.textContent = 'Cannot reach the local STT server'; stop(); };
  ws.onclose = () => { if (on) stop(); };
  ws.onopen = () => {
    ctx = new AudioContext();
    const src = ctx.createMediaStreamSource(stream);
    proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = e => { if (ws.readyState === 1) ws.send(down(e.inputBuffer.getChannelData(0), ctx.sampleRate)); };
    src.connect(proc); proc.connect(ctx.destination);
    on = true; b.textContent = '⏹ Stop'; s.textContent = '● listening';
  };
}
function stop() {
  on = false; b.textContent = '🎤 Start live capture';
  try { proc && proc.disconnect(); ctx && ctx.close(); stream && stream.getTracks().forEach(t => t.stop()); ws && ws.close(); } catch (e) {}
  if (!s.textContent.startsWith('Cannot') && !s.textContent.startsWith('Mic')) s.textContent = 'stopped';
}
b.onclick = () => on ? stop() : start();
</script>
"""


def mic_html() -> str:
    return MIC_HTML.replace("__PORT__", str(PORT))


ORB_HTML = """
<style>
  body{margin:0;font-family:system-ui;text-align:center;background:transparent;color:__INK__}
  #orb{width:110px;height:110px;border-radius:50%;margin:10px auto 6px;cursor:pointer;border:none;display:block;
       background:radial-gradient(circle at 35% 30%,#fff,#d9dde6 55%,#aab1c2);transition:transform .15s}
  #orb:hover{transform:scale(1.04)}
  #orb.on{background:radial-gradient(circle at 35% 30%,#fff,#bfe6dc 45%,#0B6E6E);box-shadow:0 0 30px rgba(11,110,110,.5);animation:pulse 2.2s ease-in-out infinite}
  @keyframes pulse{0%,100%{transform:scale(1);box-shadow:0 0 22px rgba(11,110,110,.4)}50%{transform:scale(1.07);box-shadow:0 0 44px rgba(11,110,110,.75)}}
  #l{letter-spacing:.14em;font-weight:700;font-size:12px;color:__MUTED__}
  #l.on{color:#0B6E6E}
  #s{font-size:11px;color:__MUTED__;margin-top:3px;min-height:14px}
</style>
<button id="orb" aria-label="Start or stop live capture"></button>
<div id="l">TAP TO START LIVE CAPTURE</div><div id="s"></div>
<script>
const PORT = __PORT__;
let ws, ctx, proc, stream, on = false;
const o = document.getElementById('orb'), l = document.getElementById('l'), s = document.getElementById('s');
function down(buf, inRate) {
  const r = inRate / 16000, n = Math.floor(buf.length / r), out = new Int16Array(n);
  for (let i = 0; i < n; i++) { const v = Math.max(-1, Math.min(1, buf[Math.floor(i * r)])); out[i] = v < 0 ? v * 0x8000 : v * 0x7fff; }
  return out.buffer;
}
function ui(active, msg) { on = active; o.classList.toggle('on', active); l.classList.toggle('on', active);
  l.textContent = active ? 'LISTENING · TAP TO STOP' : 'TAP TO START LIVE CAPTURE'; s.textContent = msg || ''; }
async function start() {
  try { stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}}); }
  catch (e) { ui(false, 'Mic blocked: ' + e.message); return; }
  ws = new WebSocket('ws://127.0.0.1:' + PORT);
  ws.binaryType = 'arraybuffer';
  ws.onerror = () => { stop('Cannot reach the local STT server'); };
  ws.onclose = () => { if (on) stop(); };
  ws.onopen = () => {
    ctx = new AudioContext(); ctx.resume();
    const src = ctx.createMediaStreamSource(stream);
    proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = e => { if (ws.readyState === 1) ws.send(down(e.inputBuffer.getChannelData(0), ctx.sampleRate)); };
    src.connect(proc); proc.connect(ctx.destination);
    ui(true);
  };
}
function stop(msg) {
  try { proc && proc.disconnect(); ctx && ctx.close(); stream && stream.getTracks().forEach(t => t.stop()); ws && ws.close(); } catch (e) {}
  ui(false, msg);
}
o.onclick = () => on ? stop() : start();
</script>
"""


def orb_html(dark: bool = False) -> str:
    ink, muted = ("#e6ebf7", "#7f8aa8") if dark else ("#1f2a44", "#8d96ad")
    return ORB_HTML.replace("__PORT__", str(PORT)).replace("__INK__", ink).replace("__MUTED__", muted)

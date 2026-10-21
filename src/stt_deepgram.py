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
import threading
from dataclasses import dataclass, field
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

PORT = int(os.environ.get("STT_PORT", "8765"))
ROLES = ["clinician", "patient", "caregiver"]


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

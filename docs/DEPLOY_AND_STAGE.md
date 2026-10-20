# Deploy and stage checklist

## Deploy (Streamlit Community Cloud)
1. Push to GitHub. Main file: `app.py`. Python 3.12 or newer. `requirements.txt` already lists everything, including the spaCy model wheel.
2. Secrets (app settings, never in the repo): `GROQ_API_KEY` (and `GEMINI_API_KEY` if used). Set `DRLISTNER_MODE = "DEMO"` for the public link.
3. Default to the **Scripted** backend on the hosted link. It needs no key and no network.
4. Local memory check (this laptop, not Streamlit Cloud): scripted flow peaks at about 230 MB; the de-identification path (Presidio + spaCy) adds about 180 MB on its own. Both are under the 690 MB minimum, but confirm on the real host after deploying.
5. The app wakes with one click after 12 hours idle. Open the link before presenting.

## Stage checklist (role-play demo)
- Chrome, microphone allowed for the site, quiet room, headset mic if possible.
- Backend: Scripted. Press Start new visit. Test the mic button once with a throwaway line, then Start new visit again.
- Speaker toggle: switch it before each person talks, or use "Play next scripted line" as the fallback.
- Say the lines close to word for word (see demo/README.md). Pause about a second between turns.
- Expected: heads-up at turn 16 (not repaired) and turn 21 (chart conflict); at End visit, 5 gap cards and the summary.
- Fallbacks: typed-line box, "Play next scripted line", screen recording of a clean run.

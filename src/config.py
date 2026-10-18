"""Runtime configuration: DEMO/LIVE mode, paths, secrets."""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (gitignored file); real env vars win."""
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except OSError:
        pass


_load_dotenv(ROOT / ".env")
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "llm_cache"
CHECKLIST_PATH = DATA_DIR / "checklist" / "chest_pain.json"


class Mode(str, Enum):
    DEMO = "DEMO"  # cached results only, zero network calls
    LIVE = "LIVE"  # Gemini primary, Ollama fallback


def get_mode() -> Mode:
    raw = os.environ.get("DRLISTNER_MODE", "DEMO").upper()
    try:
        return Mode(raw)
    except ValueError:
        raise ValueError(f"DRLISTNER_MODE must be DEMO or LIVE, got {raw!r}")


def get_secret(name: str) -> str | None:
    """Env first, then Streamlit secrets. Never read from the repo."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        import streamlit as st

        return st.secrets.get(name)  # type: ignore[no-any-return]
    except Exception:
        return None


# Model names are configurable; verify current free-tier names in AI Studio.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
# Provider order for LIVE mode.
PROVIDERS = tuple(p.strip() for p in os.environ.get("LLM_PROVIDERS", "groq,gemini,ollama").split(",") if p.strip())

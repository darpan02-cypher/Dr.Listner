"""Live smoke test: python -m scripts.smoke_llm  (needs GEMINI_API_KEY and/or a running Ollama)."""
import sys
from pydantic import BaseModel
from src import config
from src.llm.client import LLMClient, LLMError


class Ping(BaseModel):
    word: str


if __name__ == "__main__":
    c = LLMClient(mode=config.Mode.LIVE, cache_dir=config.ROOT / ".smoke_cache")
    try:
        out = c.generate('Return {"word": "pong"}.', Ping)
        print("OK via", c.last_source, out)
    except LLMError as e:
        print("FAILED:", e)
        sys.exit(1)

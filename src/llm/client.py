"""The ONLY place LLM calls are made.

LIVE: cache -> providers in order (default Groq -> Gemini -> Ollama; JSON mode, retries) -> LLMUnavailable.
DEMO: cache only; a miss raises DemoCacheMiss. Zero network calls.

The cache stores model, key hash and response text, not the prompt, so no
transcript text is written by this layer. Key = sha256(model, system, prompt, schema).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Callable, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from .. import config

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRY_STATUS = {429, 500, 502, 503, 504}


class LLMError(Exception): ...
class DemoCacheMiss(LLMError): ...
class LLMUnavailable(LLMError): ...


class _Retryable(Exception):
    def __init__(self, msg: str = "", delay: float | None = None):
        super().__init__(msg)
        self.delay = delay  # server-requested wait (Retry-After), seconds


MAX_RETRY_AFTER_S = 90.0


def _retry_after(r) -> float | None:
    try:
        v = float((getattr(r, "headers", None) or {}).get("retry-after"))
    except (TypeError, ValueError):
        return None
    return min(max(v, 0.0), MAX_RETRY_AFTER_S)


class LLMClient:
    def __init__(
        self,
        mode: config.Mode | None = None,
        cache_dir: Path | None = None,
        gemini_model: str | None = None,
        ollama_model: str | None = None,
        groq_model: str | None = None,
        providers: tuple[str, ...] | None = None,
        max_retries: int = 3,
        backoff_s: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        timeout_s: float = 60.0,
    ):
        self.mode = mode or config.get_mode()
        self.cache_dir = Path(cache_dir or config.CACHE_DIR)
        self.gemini_model = gemini_model or config.GEMINI_MODEL
        self.ollama_model = ollama_model or config.OLLAMA_MODEL
        self.groq_model = groq_model or config.GROQ_MODEL
        self.providers = providers or config.PROVIDERS
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self._sleep = sleep
        self.timeout_s = timeout_s
        self.last_source: str | None = None  # "cache" | "gemini" | "ollama"

    # ---- public ----
    def generate(self, prompt: str, schema: type[T], system: str | None = None) -> T:
        schema_json = json.dumps(schema.model_json_schema(), sort_keys=True)
        full = self._with_schema(prompt, schema_json)
        # Cache lookup: Gemini key first, then Ollama key.
        calls = {
            "groq": (self._call_groq, self.groq_model),
            "gemini": (self._call_gemini, self.gemini_model),
            "ollama": (self._call_ollama, self.ollama_model),
        }
        for _, model in (calls[p] for p in self.providers):
            hit = self._cache_get(self._key(model, system, full))
            if hit is not None:
                try:
                    out = schema.model_validate_json(hit)
                except ValidationError:
                    continue  # stale/invalid entry: ignore
                self.last_source = "cache"
                return out
        if self.mode is config.Mode.DEMO:
            raise DemoCacheMiss("DEMO mode: no cached response for this prompt")

        errors: list[str] = []
        for name in self.providers:
            call, model = calls[name]
            try:
                out = self._run_provider(call, full, system, schema, schema_json)
            except LLMError as e:
                errors.append(f"{name}: {e}")
                log.warning("provider %s failed: %s", name, e)
                continue
            self._cache_put(self._key(model, system, full), model, out.model_dump_json())
            self.last_source = name
            return out
        raise LLMUnavailable("; ".join(errors))

    # ---- providers ----
    def _run_provider(self, call, prompt, system, schema, schema_json) -> BaseModel:
        """Retry transient failures with backoff and invalid JSON with feedback."""
        feedback = ""
        for attempt in range(self.max_retries):
            wait = None
            try:
                text = call(prompt + feedback, system, schema_json)
                return schema.model_validate_json(_strip_fence(text))
            except _Retryable as e:
                err = str(e)
                wait = e.delay
            except (ValidationError, ValueError) as e:  # bad JSON / schema mismatch
                err = f"invalid output: {str(e)[:200]}"
                feedback = f"\n\nYour previous reply was invalid ({str(e)[:200]}). Reply with valid JSON only."
            if attempt < self.max_retries - 1:
                self._sleep(wait if wait is not None else self.backoff_s * (2**attempt))
        raise LLMError(f"gave up after {self.max_retries} attempts: {err}")

    def _call_groq(self, prompt: str, system: str | None, schema_json: str) -> str:
        key = config.get_secret("GROQ_API_KEY")
        if not key:
            raise LLMError("GROQ_API_KEY not set")  # not retryable
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        try:
            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={"model": self.groq_model, "messages": msgs, "temperature": 0,
                      "response_format": {"type": "json_object"}},
                timeout=self.timeout_s,
            )
        except requests.RequestException as e:
            raise _Retryable(f"network: {type(e).__name__}")
        if r.status_code in RETRY_STATUS:
            raise _Retryable(f"HTTP {r.status_code}", delay=_retry_after(r) if r.status_code == 429 else None)
        if r.status_code != 200:
            raise LLMError(f"HTTP {r.status_code}")
        try:
            return r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError):
            raise ValueError("unexpected Groq response shape")

    def _call_gemini(self, prompt: str, system: str | None, schema_json: str) -> str:
        key = config.get_secret("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY not set")  # not retryable
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        try:
            r = requests.post(
                GEMINI_URL.format(model=self.gemini_model),
                headers={"x-goog-api-key": key},
                json=body,
                timeout=self.timeout_s,
            )
        except requests.RequestException as e:
            raise _Retryable(f"network: {type(e).__name__}")
        if r.status_code in RETRY_STATUS:
            raise _Retryable(f"HTTP {r.status_code}")
        if r.status_code != 200:
            raise LLMError(f"HTTP {r.status_code}")  # does not echo body/key
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError):
            raise ValueError("unexpected Gemini response shape")

    def _call_ollama(self, prompt: str, system: str | None, schema_json: str) -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        try:
            r = requests.post(
                f"{config.OLLAMA_URL}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": msgs,
                    "stream": False,
                    "format": json.loads(schema_json),
                    "options": {"temperature": 0},
                },
                timeout=self.timeout_s * 3,
            )
        except requests.ConnectionError:
            raise LLMError("Ollama not reachable")  # not retryable
        except requests.RequestException as e:
            raise _Retryable(f"network: {type(e).__name__}")
        if r.status_code in RETRY_STATUS:
            raise _Retryable(f"HTTP {r.status_code}")
        if r.status_code != 200:
            raise LLMError(f"HTTP {r.status_code}")
        try:
            return r.json()["message"]["content"]
        except (KeyError, ValueError):
            raise ValueError("unexpected Ollama response shape")

    # ---- cache ----
    @staticmethod
    def _with_schema(prompt: str, schema_json: str) -> str:
        return f"{prompt}\n\nRespond with JSON only, matching this JSON Schema:\n{schema_json}"

    @staticmethod
    def _key(model: str, system: str | None, prompt: str) -> str:
        h = hashlib.sha256()
        for part in (model, system or "", prompt):
            h.update(part.encode())
            h.update(b"\x00")
        return h.hexdigest()

    def _cache_get(self, key: str) -> str | None:
        p = self.cache_dir / f"{key}.json"
        try:
            return json.loads(p.read_text())["response"]
        except (OSError, ValueError, KeyError):
            return None

    def _cache_put(self, key: str, model: str, response: str) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(
            json.dumps({"model": model, "response": response})
        )


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1].rsplit("```", 1)[0]
    return t

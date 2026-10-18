import json
import pytest
import requests
from pydantic import BaseModel
from src import config
from src.llm import client as C
from src.llm.client import DemoCacheMiss, LLMClient, LLMUnavailable


class Out(BaseModel):
    answer: str


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._p = status, payload or {}
    def json(self):
        return self._p


def gem(text): return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})
def oll(text): return FakeResp(200, {"message": {"content": text}})


@pytest.fixture
def mk(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    sleeps = []
    def make(mode=config.Mode.LIVE):
        return LLMClient(mode=mode, cache_dir=tmp_path, gemini_model="g", ollama_model="o", providers=("gemini", "ollama"), sleep=sleeps.append)
    make.sleeps = sleeps
    return make


def route(monkeypatch, gemini, ollama):
    calls = []
    def post(url, **kw):
        calls.append(url)
        h = gemini if "googleapis" in url else ollama
        r = h.pop(0) if isinstance(h, list) else h
        if isinstance(r, Exception): raise r
        return r
    monkeypatch.setattr(C.requests, "post", post)
    return calls


def test_gemini_ok_then_cached_no_network(mk, monkeypatch):
    calls = route(monkeypatch, [gem('{"answer":"a"}')], [])
    c = mk()
    assert c.generate("p", Out).answer == "a" and c.last_source == "gemini"
    assert c.generate("p", Out).answer == "a" and c.last_source == "cache"
    assert len(calls) == 1


def test_demo_reads_cache_zero_calls_and_misses_raise(mk, monkeypatch):
    route(monkeypatch, [gem('{"answer":"a"}')], [])
    mk().generate("p", Out)
    calls = route(monkeypatch, [], [])
    d = mk(config.Mode.DEMO)
    assert d.generate("p", Out).answer == "a"
    with pytest.raises(DemoCacheMiss):
        d.generate("other", Out)
    assert calls == []


def test_retry_backoff_on_429_then_success(mk, monkeypatch):
    route(monkeypatch, [FakeResp(429), FakeResp(503), gem('{"answer":"ok"}')], [])
    c = mk()
    assert c.generate("p", Out).answer == "ok"
    assert mk.sleeps == [2.0, 4.0]


def test_invalid_json_retried_with_feedback(mk, monkeypatch):
    route(monkeypatch, [gem("not json"), gem('{"wrong":1}'), gem('{"answer":"fixed"}')], [])
    assert mk().generate("p", Out).answer == "fixed"


def test_falls_back_to_ollama(mk, monkeypatch):
    route(monkeypatch, [FakeResp(429)] * 3, [oll('{"answer":"local"}')])
    c = mk()
    assert c.generate("p", Out).answer == "local" and c.last_source == "ollama"


def test_both_down_fails_gracefully(mk, monkeypatch):
    route(monkeypatch, requests.ConnectionError(), requests.ConnectionError())
    with pytest.raises(LLMUnavailable):
        mk().generate("p", Out)


def test_missing_key_skips_to_ollama(mk, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setattr(config, "get_secret", lambda n: None)
    calls = route(monkeypatch, [], [oll('{"answer":"x"}')])
    assert mk().generate("p", Out).answer == "x"
    assert all("googleapis" not in u for u in calls)


def test_cache_does_not_store_prompt(mk, monkeypatch, tmp_path):
    route(monkeypatch, [gem('{"answer":"a"}')], [])
    mk().generate("SECRET-TRANSCRIPT-TEXT", Out)
    assert all("SECRET-TRANSCRIPT-TEXT" not in p.read_text() for p in tmp_path.glob("*.json"))


def test_key_not_in_errors(mk, monkeypatch):
    route(monkeypatch, [FakeResp(403)], [FakeResp(500)] * 3)
    with pytest.raises(LLMUnavailable) as e:
        mk().generate("p", Out)
    assert "test-key" not in str(e.value)


def test_groq_first_then_fallthrough(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    seen = []
    def post(url, **kw):
        seen.append(url)
        if "groq" in url:
            return FakeResp(200, {"choices": [{"message": {"content": '{"answer":"g"}'}}]})
        raise AssertionError("should not reach other providers")
    monkeypatch.setattr(C.requests, "post", post)
    c = LLMClient(mode=config.Mode.LIVE, cache_dir=tmp_path, groq_model="gm", providers=("groq", "gemini", "ollama"), sleep=lambda s: None)
    assert c.generate("p", Out).answer == "g" and c.last_source == "groq"

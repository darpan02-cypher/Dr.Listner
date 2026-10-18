"""Turn input interface. The engine only ever sees Turns from a TurnSource.

ReplaySource is implemented. TypedSource / MicSource are out of scope for the
Oct 21 deadline (Phase 7) and intentionally not stubbed with fake behaviour.
"""
from __future__ import annotations

from typing import Iterator, Protocol

from .schemas import Transcript, Turn


class TurnSource(Protocol):
    def turns(self) -> Iterator[Turn]: ...


class ReplaySource:
    def __init__(self, transcript: Transcript):
        self._t = transcript

    def turns(self) -> Iterator[Turn]:
        yield from self._t.turns

"""Shapes shared by the Sarvam extraction, translation and Prism rating adapters.

Every adapter here is advisory. Extraction feeds the deterministic validator; the Prism rating feeds
a deterministic lane rule (`app/services/review_policy.py`). Nothing in this package decides a payment.
"""
from dataclasses import dataclass, field
from typing import Protocol

from app.schemas.validation import Decision


@dataclass(frozen=True)
class Extraction:
    provider: str
    invoice: dict | None  # fields of `ExtractedInvoice`, exactly as the extractor produced them
    display: dict = field(default_factory=dict)  # human-facing extras: descriptions, language, handwriting
    error: str | None = None
    provider_result: dict | None = None


@dataclass(frozen=True)
class Signal:
    code: str
    detail: str
    impact: int  # points removed from 100; 0 for an informational signal


@dataclass(frozen=True)
class Rating:
    provider: str
    score: int  # 0..100
    signals: list[Signal]


class Extractor(Protocol):
    def extract(self, content: bytes, filename: str) -> Extraction: ...


class Rater(Protocol):
    def rate(self, extraction: Extraction, decision: Decision | None) -> Rating: ...


class Translator(Protocol):
    name: str

    def translate(self, texts: list[str], target: str) -> list[str] | None:
        """Translate English strings into `target` (e.g. "ta"). Return None if unavailable."""

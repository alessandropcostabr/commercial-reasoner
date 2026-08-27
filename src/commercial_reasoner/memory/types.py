from dataclasses import dataclass
from typing import Literal, Optional

Origin = Literal["client", "agent"]
Category = Literal["quote", "commitment", "objection", "client_context"]
Confidence = Literal["high", "medium"]


@dataclass(frozen=True)
class Turn:
    client_message: str
    agent_response: str


@dataclass(frozen=True)
class PricePoint:
    modality: str
    value: float
    description: str = ""


@dataclass(frozen=True)
class CanonicalFacts:
    prices: tuple[PricePoint, ...]
    other_numbers: tuple[float, ...]


@dataclass(frozen=True)
class FactCandidate:
    category: Category
    source: Origin
    text: str
    value: Optional[float] = None
    ref_fact_id: Optional[str] = None


@dataclass(frozen=True)
class Fact:
    id: str
    category: Category
    source: Origin
    text: str
    verified: bool
    confidence: Confidence
    value: Optional[float] = None
    ref_fact_id: Optional[str] = None


@dataclass(frozen=True)
class AuditRecord:
    category: Category
    source: Origin
    text: str
    reason: str
    raw_text: Optional[str] = None


@dataclass(frozen=True)
class ExtractionResult:
    facts: tuple[Fact, ...]
    audit: tuple[AuditRecord, ...]

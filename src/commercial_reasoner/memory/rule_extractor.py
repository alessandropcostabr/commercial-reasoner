import re
from typing import Optional

from .numeric_guard import extract_numbers, split_sentences
from .types import FactCandidate, Origin

_STRONG_COMMITMENT_CLIENT = (
    re.compile(r"\bvou fechar\b", re.IGNORECASE),
    re.compile(r"\bfecho\b", re.IGNORECASE),
    re.compile(r"\bfechei\b", re.IGNORECASE),
    re.compile(r"\bconfirmo\b", re.IGNORECASE),
    re.compile(r"\bmanda(?:r)? o link\b", re.IGNORECASE),
    re.compile(r"\bpode reservar\b", re.IGNORECASE),
)

_STRONG_COMMITMENT_AGENT = (
    re.compile(r"\bvou confirmar\b", re.IGNORECASE),
    re.compile(r"\bvou reservar\b", re.IGNORECASE),
    re.compile(r"\bgaranto\b", re.IGNORECASE),
)

_STRONG_OBJECTION = (
    re.compile(r"\bmuito caro\b", re.IGNORECASE),
    re.compile(r"\bcaro demais\b", re.IGNORECASE),
    re.compile(r"\bpreciso pensar\b", re.IGNORECASE),
    re.compile(r"\bvou ver com\b", re.IGNORECASE),
)

_STRONG_CLIENT_CONTEXT = (
    re.compile(r"\bmeu orcamento e\b", re.IGNORECASE),
    re.compile(r"\bmeu or[cç]amento [eé]\b", re.IGNORECASE),
)

_WEAK_TRIGGERS = (
    re.compile(r"\bpensar\b", re.IGNORECASE),
    re.compile(r"\bdepois\b", re.IGNORECASE),
    re.compile(r"\btalvez\b", re.IGNORECASE),
)

def _extract_value(sentence: str) -> Optional[float]:
    # Regex de numero e de split de sentenca vivem so no numeric_guard (achado M-1):
    # duas copias ja tinham divergido entre si.
    numbers = extract_numbers(sentence)
    return numbers[0] if numbers else None


def _all_strong_patterns() -> tuple:
    return _STRONG_COMMITMENT_CLIENT + _STRONG_COMMITMENT_AGENT + _STRONG_OBJECTION + _STRONG_CLIENT_CONTEXT


def extract_strong(text: str, source: Origin) -> list[FactCandidate]:
    candidates: list[FactCandidate] = []

    for sentence in split_sentences(text):
        value = _extract_value(sentence)

        if source == "client":
            if any(p.search(sentence) for p in _STRONG_COMMITMENT_CLIENT):
                candidates.append(
                    FactCandidate(category="commitment", source="client", text=sentence, value=value)
                )
                continue
            if any(p.search(sentence) for p in _STRONG_OBJECTION):
                candidates.append(FactCandidate(category="objection", source="client", text=sentence))
                continue
            if any(p.search(sentence) for p in _STRONG_CLIENT_CONTEXT):
                candidates.append(
                    FactCandidate(category="client_context", source="client", text=sentence, value=value)
                )
                continue
        else:
            if any(p.search(sentence) for p in _STRONG_COMMITMENT_AGENT):
                candidates.append(FactCandidate(category="commitment", source="agent", text=sentence))
                continue

    return candidates


def find_weak_signals(text: str) -> list[str]:
    signals: list[str] = []
    strong_patterns = _all_strong_patterns()

    for sentence in split_sentences(text):
        if any(p.search(sentence) for p in strong_patterns):
            continue
        if any(p.search(sentence) for p in _WEAK_TRIGGERS):
            signals.append(sentence)

    return signals

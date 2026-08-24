from typing import Callable, Optional

from .types import FactCandidate

LLMExtractFn = Callable[[str], list[FactCandidate]]

_ALLOWED_LLM_CATEGORIES = ("commitment", "objection", "client_context")


def extract_by_llm(sentence: str, llm_extract: Optional[LLMExtractFn]) -> list[FactCandidate]:
    if llm_extract is None:
        return []

    try:
        candidates = llm_extract(sentence)
    except Exception:
        return []

    # O LLM roda sobre a fala do CLIENTE (superficie de prompt injection): a saida so
    # vale como candidato de cliente, nunca numerica, nunca cotacao. Cotacao nasce
    # exclusivamente do NumericGuard, com match estruturado (achado C-1).
    return [
        c
        for c in candidates
        if c.value is None
        and c.source == "client"
        and c.category in _ALLOWED_LLM_CATEGORIES
    ]

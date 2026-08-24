from typing import Callable, Optional

from .types import FactCandidate

LLMExtractFn = Callable[[str], list[FactCandidate]]

_ALLOWED_LLM_CATEGORIES = ("commitment", "objection", "client_context")


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


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
    #
    # Ancoragem (mesma classe do bug original da Miah, por outra porta): o `text` do
    # candidato e 100% gerado pelo LLM e vira `Fact.text` reinjetavel. Exigir que ele
    # seja substring (normalizada) da sentenca fecha o vetor de alucinacao/injecao -
    # texto que nao veio da fala do cliente nunca vira memoria.
    sentence_norm = _normalize(sentence)
    return [
        c
        for c in candidates
        if c.value is None
        and c.source == "client"
        and c.category in _ALLOWED_LLM_CATEGORIES
        and _normalize(c.text)
        and _normalize(c.text) in sentence_norm
    ]

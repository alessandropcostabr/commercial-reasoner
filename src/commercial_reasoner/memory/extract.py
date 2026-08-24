from typing import Optional

from . import assembler, numeric_guard, rule_extractor
from .llm_extractor import LLMExtractFn, extract_by_llm
from .types import CanonicalFacts, ExtractionResult, FactCandidate, Turn


def extract_facts(
    turn: Turn,
    canonical_facts: CanonicalFacts,
    llm_extract: Optional[LLMExtractFn] = None,
    prior_quote_id: Optional[str] = None,
) -> ExtractionResult:
    """Decide o que de um turno vira memoria de longo prazo.

    `prior_quote_id` e o id da ultima cotacao verificada de um turno ANTERIOR, usado
    pra resolver anafora do cliente ("fecho por esse valor"). Como `canonical_facts`,
    e injetado pelo caller a cada chamada - o frescor e responsabilidade de quem chama.
    Nunca pode ser uma cotacao deste mesmo turno: o `client_message` foi dito antes de
    o `agent_response` existir (achado I-1). Sem ele, a referencia fica nao-resolvida
    (`ref_fact_id=None`) - nenhum numero e inventado.
    """
    quote_facts, quote_audit = numeric_guard.check_quote(turn.agent_response, canonical_facts)

    client_strong = rule_extractor.extract_strong(turn.client_message, source="client")
    agent_strong = rule_extractor.extract_strong(turn.agent_response, source="agent")

    weak_signals = rule_extractor.find_weak_signals(turn.client_message)
    llm_candidates: list[FactCandidate] = []
    for sentence in weak_signals:
        llm_candidates.extend(extract_by_llm(sentence, llm_extract))

    resolved_client: list[FactCandidate] = []
    for candidate in client_strong + llm_candidates:
        if candidate.category == "commitment" and candidate.value is None and prior_quote_id is not None:
            resolved_client.append(
                FactCandidate(
                    category=candidate.category,
                    source=candidate.source,
                    text=candidate.text,
                    value=None,
                    ref_fact_id=prior_quote_id,
                )
            )
        else:
            resolved_client.append(candidate)

    return assembler.assemble(quote_facts, quote_audit, resolved_client, agent_strong, canonical_facts)

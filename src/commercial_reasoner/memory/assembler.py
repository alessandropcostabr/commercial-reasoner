from . import numeric_guard
from .types import AuditRecord, CanonicalFacts, ExtractionResult, Fact, FactCandidate


def assemble(
    quote_facts: list[Fact],
    quote_audit: list[AuditRecord],
    client_candidates: list[FactCandidate],
    agent_candidates: list[FactCandidate],
    canonical_facts: CanonicalFacts,
) -> ExtractionResult:
    facts: list[Fact] = list(quote_facts)
    audit: list[AuditRecord] = list(quote_audit)
    seen: set[tuple[str, str, str]] = {(f.source, f.category, f.text) for f in facts}
    counters: dict[str, int] = {}

    def next_id(category: str) -> str:
        counters[category] = counters.get(category, 0) + 1
        return f"{category}-{counters[category]}"

    for candidate in agent_candidates:
        key = (candidate.source, candidate.category, candidate.text)
        if key in seen:
            continue
        seen.add(key)
        audit.append(
            AuditRecord(
                category=candidate.category,
                source="agent",
                text=candidate.text,
                reason="agent_source_excluded",
                raw_text=candidate.text,
            )
        )

    for candidate in client_candidates:
        key = (candidate.source, candidate.category, candidate.text)
        if key in seen:
            continue
        seen.add(key)

        # Anti-injecao (achados I4/C-3): a checagem varre TODOS os numeros do texto,
        # nao so o campo `value` - este so e preenchido quando o texto traz "R$"/"%",
        # e o Fact.text (que e o campo reinjetado como memoria) carrega o numero de
        # qualquer jeito. Um unico numero sem preco canonico correspondente manda o
        # candidato inteiro pra auditoria.
        numbers = numeric_guard.extract_all_numbers(candidate.text)
        if candidate.value is not None:
            numbers.append(candidate.value)

        if any(numeric_guard.classify_client_number(n, canonical_facts) is None for n in numbers):
            audit.append(
                AuditRecord(
                    category=candidate.category,
                    source="client",
                    text=candidate.text,
                    reason="unstructured_client_number",
                    raw_text=candidate.text,
                )
            )
            continue

        facts.append(
            Fact(
                id=next_id(candidate.category),
                category=candidate.category,
                source="client",
                text=candidate.text,
                verified=True,
                confidence="high",
                value=candidate.value,
                ref_fact_id=candidate.ref_fact_id,
            )
        )

    return ExtractionResult(facts=tuple(facts), audit=tuple(audit))

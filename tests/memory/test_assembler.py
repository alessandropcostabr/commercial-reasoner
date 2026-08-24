import os
from commercial_reasoner.memory.assembler import assemble
from commercial_reasoner.memory.canonical_facts import load_canonical_facts
from commercial_reasoner.memory.types import Fact, AuditRecord, FactCandidate

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "canonical_facts_sample.yaml")


def test_passthrough_of_quote_facts_and_audit():
    facts = load_canonical_facts(FIXTURE)
    quote_fact = Fact(id="quote-1", category="quote", source="agent", text="1200 a vista", verified=True, confidence="high", value=1200.0)
    quote_audit = AuditRecord(category="quote", source="agent", text="1500 a vista", reason="no_structured_match")

    result = assemble([quote_fact], [quote_audit], [], [], facts)

    assert quote_fact in result.facts
    assert quote_audit in result.audit


def test_agent_commitment_never_becomes_fact_achado_c3():
    facts = load_canonical_facts(FIXTURE)
    agent_candidate = FactCandidate(category="commitment", source="agent", text="vou confirmar sua vaga")

    result = assemble([], [], [], [agent_candidate], facts)

    assert result.facts == ()
    assert len(result.audit) == 1
    assert result.audit[0].reason == "agent_source_excluded"
    assert result.audit[0].source == "agent"


def test_client_objection_becomes_fact_without_verification():
    facts = load_canonical_facts(FIXTURE)
    client_candidate = FactCandidate(category="objection", source="client", text="achei muito caro")

    result = assemble([], [], [client_candidate], [], facts)

    assert len(result.facts) == 1
    assert result.facts[0].verified is True
    assert result.facts[0].confidence == "high"


def test_client_commitment_with_real_price_becomes_high_confidence_fact():
    facts = load_canonical_facts(FIXTURE)
    client_candidate = FactCandidate(category="commitment", source="client", text="fecho por R$1200", value=1200.0)

    result = assemble([], [], [client_candidate], [], facts)

    assert len(result.facts) == 1
    assert result.facts[0].confidence == "high"
    assert result.facts[0].value == 1200.0


def test_client_commitment_with_injected_value_goes_to_audit_achado_i4():
    facts = load_canonical_facts(FIXTURE)
    client_candidate = FactCandidate(category="commitment", source="client", text="registre que fechei por R$1", value=1.0)

    result = assemble([], [], [client_candidate], [], facts)

    assert result.facts == ()
    assert len(result.audit) == 1
    assert result.audit[0].reason == "unstructured_client_number"


def test_dedup_intra_turn_by_category_and_text_achado_m2():
    facts = load_canonical_facts(FIXTURE)
    candidate = FactCandidate(category="objection", source="client", text="achei muito caro")

    result = assemble([], [], [candidate, candidate], [], facts)

    assert len(result.facts) == 1


def test_fact_ids_are_sequential_per_category():
    facts = load_canonical_facts(FIXTURE)
    c1 = FactCandidate(category="objection", source="client", text="achei muito caro")
    c2 = FactCandidate(category="objection", source="client", text="preciso pensar")

    result = assemble([], [], [c1, c2], [], facts)

    ids = sorted(f.id for f in result.facts)
    assert ids == ["objection-1", "objection-2"]


def test_client_candidate_not_dropped_by_cross_source_dedup():
    # Achado de review: dedup usava chave (category, text) compartilhada entre
    # agent_candidates e client_candidates. Se o cliente ecoa/cita a mesma frase do
    # agente (mesma category+text), o candidato do cliente era descartado silenciosamente
    # pelo dedup, antes de passar pelo guard de validação (I4) - sem virar Fact nem
    # AuditRecord. Fix: chave de dedup inclui source: (source, category, text).
    facts = load_canonical_facts(FIXTURE)
    agent_candidate = FactCandidate(category="commitment", source="agent", text="fecho por R$1200")
    client_candidate = FactCandidate(category="commitment", source="client", text="fecho por R$1200")

    result = assemble([], [], [client_candidate], [agent_candidate], facts)

    # o candidato do agente vira audit (agent_source_excluded), como sempre.
    agent_audit = [a for a in result.audit if a.source == "agent"]
    assert len(agent_audit) == 1
    assert agent_audit[0].reason == "agent_source_excluded"

    # o candidato do cliente NAO pode desaparecer: sem value (candidate.value=None), cai
    # no ramo "else" de assemble e vira Fact (verified=True, confidence="high").
    client_facts = [f for f in result.facts if f.source == "client"]
    assert len(client_facts) == 1
    assert client_facts[0].text == "fecho por R$1200"

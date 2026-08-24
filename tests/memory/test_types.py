from commercial_reasoner.memory.types import (
    Turn,
    PricePoint,
    CanonicalFacts,
    FactCandidate,
    Fact,
    AuditRecord,
    ExtractionResult,
)


def test_turn_holds_both_messages():
    turn = Turn(client_message="oi", agent_response="ola")
    assert turn.client_message == "oi"
    assert turn.agent_response == "ola"


def test_canonical_facts_holds_prices_and_other_numbers():
    facts = CanonicalFacts(
        prices=(PricePoint(modality="upfront", value=1200.0, description="a vista"),),
        other_numbers=(30.0, 10.0),
    )
    assert facts.prices[0].value == 1200.0
    assert 10.0 in facts.other_numbers


def test_fact_is_immutable():
    fact = Fact(id="quote-1", category="quote", source="agent", text="1200 a vista", verified=True, confidence="high", value=1200.0)
    try:
        fact.value = 999.0
        assert False, "Fact deveria ser imutavel"
    except Exception:
        pass


def test_audit_record_can_carry_raw_text():
    record = AuditRecord(category="quote", source="agent", text="1500 a vista", reason="no_structured_match", raw_text="a vista sai por 1500")
    assert record.raw_text == "a vista sai por 1500"


def test_extraction_result_separates_facts_and_audit():
    result = ExtractionResult(facts=(), audit=())
    assert result.facts == ()
    assert result.audit == ()


def test_fact_candidate_defaults():
    candidate = FactCandidate(category="objection", source="client", text="muito caro")
    assert candidate.value is None
    assert candidate.ref_fact_id is None

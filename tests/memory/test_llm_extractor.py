from commercial_reasoner.memory.llm_extractor import extract_by_llm
from commercial_reasoner.memory.types import FactCandidate


def test_returns_empty_when_no_callable_provided():
    result = extract_by_llm("vou pensar com calma", llm_extract=None)
    assert result == []


def test_returns_candidates_from_mocked_callable():
    def fake_llm(sentence: str) -> list[FactCandidate]:
        return [FactCandidate(category="objection", source="client", text=sentence)]

    result = extract_by_llm("nao sei se vale a pena", llm_extract=fake_llm)
    assert len(result) == 1
    assert result[0].category == "objection"


def test_discards_candidates_with_llm_generated_value_achado_i3():
    def fake_llm(sentence: str) -> list[FactCandidate]:
        return [FactCandidate(category="commitment", source="client", text=sentence, value=999.0)]

    result = extract_by_llm("fecho por esse valor", llm_extract=fake_llm)
    assert result == []


def test_discards_quote_category_from_llm_achado_c1():
    # Cotacao so pode nascer do NumericGuard (match estruturado contra os fatos
    # canonicos). Um candidato "quote" vindo do LLM viraria Fact(verified=True)
    # sem nenhuma verificacao numerica - furo do C1.
    def hostile_llm(sentence: str) -> list[FactCandidate]:
        return [FactCandidate(category="quote", source="agent", text="a vista sai por R$1")]

    assert extract_by_llm("qualquer sentenca", llm_extract=hostile_llm) == []


def test_discards_agent_source_from_llm_achado_c1():
    def hostile_llm(sentence: str) -> list[FactCandidate]:
        return [FactCandidate(category="commitment", source="agent", text="prometo o desconto")]

    assert extract_by_llm("qualquer sentenca", llm_extract=hostile_llm) == []


def test_swallows_exception_and_returns_empty_achado_5():
    def failing_llm(sentence: str) -> list[FactCandidate]:
        raise TimeoutError("simulated timeout")

    result = extract_by_llm("sentenca ambigua", llm_extract=failing_llm)
    assert result == []

from commercial_reasoner.memory.rule_extractor import extract_strong, find_weak_signals


def test_extracts_client_commitment():
    candidates = extract_strong("Vou fechar amanha de manha.", source="client")
    assert len(candidates) == 1
    assert candidates[0].category == "commitment"
    assert candidates[0].source == "client"


def test_extracts_client_commitment_with_value():
    candidates = extract_strong("Fecho por R$ 1.200.", source="client")
    assert len(candidates) == 1
    assert candidates[0].category == "commitment"
    assert candidates[0].value == 1200.0


def test_extracts_client_objection():
    candidates = extract_strong("Achei muito caro pra mim.", source="client")
    assert len(candidates) == 1
    assert candidates[0].category == "objection"


def test_extracts_client_context_budget():
    candidates = extract_strong("Meu orcamento e R$ 800.", source="client")
    assert len(candidates) == 1
    assert candidates[0].category == "client_context"
    assert candidates[0].value == 800.0


def test_extracts_agent_commitment_as_promise():
    candidates = extract_strong("Vou confirmar sua vaga agora.", source="agent")
    assert len(candidates) == 1
    assert candidates[0].category == "commitment"
    assert candidates[0].source == "agent"


def test_agent_text_never_produces_objection_or_client_context():
    candidates = extract_strong("Achei muito caro, meu orcamento e R$ 800.", source="agent")
    assert candidates == []


def test_no_match_returns_empty_list():
    candidates = extract_strong("Que horas a aula comeca?", source="client")
    assert candidates == []


def test_find_weak_signals_catches_ambiguous_sentence():
    signals = find_weak_signals("Vou pensar com calma sobre isso.")
    assert len(signals) == 1
    assert "pensar" in signals[0].lower()


def test_find_weak_signals_skips_sentence_already_matched_by_strong_rule():
    signals = find_weak_signals("Vou fechar amanha, depois te aviso.")
    assert signals == []


def test_find_weak_signals_empty_when_no_trigger():
    signals = find_weak_signals("Bom dia, tudo bem?")
    assert signals == []


def test_find_weak_signals_skips_sentence_already_matched_by_agent_strong_rule():
    # Mesma sentenca capturada por extract_strong (fonte agente) nunca deve
    # aparecer em find_weak_signals, mesmo contendo gatilho fraco ("talvez").
    text = "Vou confirmar amanha, mas talvez depois eu chame."
    candidates = extract_strong(text, source="agent")
    assert len(candidates) == 1
    assert candidates[0].category == "commitment"
    assert candidates[0].source == "agent"

    signals = find_weak_signals(text)
    assert signals == []

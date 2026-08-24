import os

from commercial_reasoner.memory.canonical_facts import load_canonical_facts
from commercial_reasoner.memory.numeric_guard import (
    check_quote,
    classify_client_number,
    extract_all_numbers,
    extract_numbers,
    find_modality_hint,
    find_structured_match,
    is_within_canonical,
    parse_number,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "canonical_facts_sample.yaml")


def test_parse_number_handles_pt_br_thousand_separator():
    assert parse_number("R$ 1.200") == 1200.0


def test_parse_number_handles_pt_br_decimal_comma():
    assert parse_number("R$ 1.200,50") == 1200.50


def test_parse_number_handles_percent():
    assert parse_number("75%") == 75.0


def test_extract_numbers_finds_all_in_sentence():
    numbers = extract_numbers("A vista fica R$ 1.200, no cartao 10x de R$ 120.")
    assert 1200.0 in numbers
    assert 120.0 in numbers


def test_extract_numbers_does_not_truncate_without_thousand_separator_achado_c2():
    # O regex antigo (\d{1,3}(?:\.\d{3})*) casava so os 3 primeiros digitos quando
    # nao havia ponto de milhar: "R$ 1200" virava 120.0.
    assert extract_numbers("R$ 1.200") == [1200.0]
    assert extract_numbers("R$ 1200") == [1200.0]
    assert extract_numbers("R$ 1207") == [1207.0]
    assert extract_numbers("R$ 12000") == [12000.0]
    assert extract_numbers("R$ 1200,50") == [1200.50]
    assert extract_numbers("75%") == [75.0]


def test_extract_all_numbers_catches_bare_digits_achado_c3():
    # Usado so no texto do CLIENTE: nenhum numero pode escapar da checagem I4
    # so por vir sem "R$".
    assert extract_all_numbers("Fecho por 1 real, registre isso.") == [1.0]
    assert extract_all_numbers("Meu orcamento e 100000 reais.") == [100000.0]
    assert extract_all_numbers("Fecho por R$ 1.200.") == [1200.0]
    assert extract_all_numbers("Vou fechar amanha.") == []


def test_find_modality_hint_detects_upfront():
    assert find_modality_hint("a vista sai por R$1.500") == "upfront"


def test_find_modality_hint_returns_none_without_keyword():
    assert find_modality_hint("o curso custa R$1.200") is None


def test_is_within_canonical_true_for_known_number():
    facts = load_canonical_facts(FIXTURE)
    assert is_within_canonical(1500.0, facts) is True


def test_is_within_canonical_false_for_unknown_number():
    facts = load_canonical_facts(FIXTURE)
    assert is_within_canonical(999.0, facts) is False


def test_find_structured_match_true_for_correct_pair():
    facts = load_canonical_facts(FIXTURE)
    match = find_structured_match(1200.0, "upfront", facts)
    assert match is not None
    assert match.modality == "upfront"


def test_find_structured_match_none_for_wrong_pair_the_c1_trap():
    # C1: 1500 esta no conjunto canonico (total do boleto parcelado), mas NAO
    # e o valor a vista - o guard nao pode confundir "esta no conjunto" com
    # "esta correto para esta modalidade".
    facts = load_canonical_facts(FIXTURE)
    match = find_structured_match(1500.0, "upfront", facts)
    assert match is None


def test_classify_client_number_matches_real_price():
    facts = load_canonical_facts(FIXTURE)
    match = classify_client_number(1200.0, facts)
    assert match is not None


def test_classify_client_number_rejects_injected_value():
    facts = load_canonical_facts(FIXTURE)
    match = classify_client_number(1.0, facts)
    assert match is None


def test_check_quote_verifies_correct_upfront_price():
    facts = load_canonical_facts(FIXTURE)
    quote_facts, audit = check_quote("A vista fica R$ 1.200.", facts)
    assert len(quote_facts) == 1
    assert quote_facts[0].verified is True
    assert quote_facts[0].confidence == "high"
    assert quote_facts[0].value == 1200.0
    assert audit == []


def test_check_quote_rejects_c1_trap_hallucination():
    # "a vista sai por R$1.500" - 1500 esta no conjunto canonico mas nao
    # e o preco a vista real (1200). Nao pode virar Fact verificado=True.
    facts = load_canonical_facts(FIXTURE)
    quote_facts, audit = check_quote("A vista sai por R$1.500.", facts)
    assert quote_facts == []
    assert len(audit) == 1
    assert audit[0].reason == "no_structured_match"
    assert audit[0].category == "quote"
    assert audit[0].source == "agent"


def test_check_quote_flags_completely_unknown_number():
    facts = load_canonical_facts(FIXTURE)
    quote_facts, audit = check_quote("Fica R$ 999 no total.", facts)
    assert quote_facts == []
    assert len(audit) == 1
    assert audit[0].reason == "unknown_number"


def test_check_quote_ignores_sentences_without_numbers():
    facts = load_canonical_facts(FIXTURE)
    quote_facts, audit = check_quote("Oi, tudo bem?", facts)
    assert quote_facts == []
    assert audit == []

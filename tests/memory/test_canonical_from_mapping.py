"""Loader stateless: dict do payload (grounded_facts) -> CanonicalFacts."""
import pytest

from commercial_reasoner.memory.canonical_facts import canonical_from_mapping


def test_dict_vira_canonical():
    facts = canonical_from_mapping(
        {
            "prices": [
                {"modality": "upfront", "value": 1000, "description": "à vista"},
                {"modality": "card_installment", "value": 100},
            ],
            "other_numbers": [2000, 10],
        }
    )
    up = next(p for p in facts.prices if p.modality == "upfront")
    assert up.value == 1000.0
    assert up.description == "à vista"
    assert 2000.0 in facts.other_numbers
    assert 10.0 in facts.other_numbers


def test_vazio_ou_none_vira_canonical_vazio():
    assert canonical_from_mapping({}).prices == ()
    assert canonical_from_mapping({}).other_numbers == ()
    assert canonical_from_mapping(None).prices == ()  # fail-safe: None -> vazio


def test_value_string_numerica_convertida():
    facts = canonical_from_mapping({"prices": [{"modality": "upfront", "value": "1000"}]})
    assert facts.prices[0].value == 1000.0


def test_price_sem_key_obrigatoria_levanta():
    # Fail-closed de forma: payload malformado explode, nao vira canonical mudo.
    with pytest.raises(KeyError):
        canonical_from_mapping({"prices": [{"modality": "upfront"}]})  # falta value


def test_alinha_com_o_gate(monkeypatch):
    # O loader alimenta o gate: um valor do payload confere.
    from commercial_reasoner.memory.gate import check_response

    canon = canonical_from_mapping(
        {"prices": [{"modality": "upfront", "value": 1000}], "other_numbers": []}
    )
    assert check_response("À vista fica R$ 1.000.", canon).decision == "allow"
    assert check_response("Faço por R$ 1.500.", canon).decision == "block"

import os

import pytest
import yaml

from commercial_reasoner.memory.canonical_facts import load_canonical_facts

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "canonical_facts_sample.yaml")


def test_loads_prices_with_modality_and_value():
    facts = load_canonical_facts(FIXTURE)
    upfront = next(p for p in facts.prices if p.modality == "upfront")
    assert upfront.value == 1200.0
    assert "vista" in upfront.description


def test_loads_other_numbers():
    facts = load_canonical_facts(FIXTURE)
    assert 10.0 in facts.other_numbers
    assert 30.0 in facts.other_numbers


def test_missing_file_raises_achado_i3():
    # Trava o comportamento ATUAL (achado I-3, parcial): a excecao sobe. Se um dia
    # a decisao for degradar pra "tudo nao-verificado" (§5 do design), este teste
    # e o lugar onde essa mudanca precisa ser feita de propósito, nao por acidente.
    with pytest.raises(FileNotFoundError):
        load_canonical_facts(os.path.join(os.path.dirname(__file__), "fixtures", "nao_existe.yaml"))


def test_malformed_yaml_raises_achado_i3(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("prices: [ {modality: upfront\n", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_canonical_facts(str(bad))


def test_price_entry_missing_required_key_raises_achado_i3(tmp_path):
    bad = tmp_path / "incomplete.yaml"
    bad.write_text("prices:\n  - modality: upfront\n", encoding="utf-8")
    with pytest.raises(KeyError):
        load_canonical_facts(str(bad))


def test_installment_plan_total_is_1500_not_a_valid_upfront_price():
    facts = load_canonical_facts(FIXTURE)
    total = next(p for p in facts.prices if p.modality == "installment_plan_total")
    upfront = next(p for p in facts.prices if p.modality == "upfront")
    assert total.value == 1500.0
    assert upfront.value == 1200.0
    assert total.value != upfront.value

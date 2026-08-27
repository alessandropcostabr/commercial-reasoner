"""Gate financeiro - verificacao ARITMETICA de parcelamento (design §4/§7).

Plano canonico = PricePoint de modalidade de parcela com `installments` (nº de
parcelas) e opcional `down_payment` (entrada); `value` continua sendo o VALOR DA
PARCELA (Item 1). O total sai derivado (installments * value + down_payment).
"""
from commercial_reasoner.memory.canonical_facts import canonical_from_mapping
from commercial_reasoner.memory.gate import check_response
from commercial_reasoner.memory.types import CanonicalFacts, PricePoint

# 12x de R$ 100 sem entrada -> total derivado 1200. Desconto 10% canonico.
CANON = CanonicalFacts(
    prices=(
        PricePoint("upfront", 1000.0, "a vista"),
        PricePoint("card_installment", 100.0, "cartao 12x", installments=12, down_payment=0.0),
    ),
    other_numbers=(10.0,),
)

# 10x de R$ 120 com entrada de R$ 200 -> total derivado 1400.
CANON_ENTRADA = CanonicalFacts(
    prices=(
        PricePoint("card_installment", 120.0, "cartao 10x + entrada", installments=10, down_payment=200.0),
    ),
    other_numbers=(),
)


def test_plano_conta_e_valor_certos_allow():
    v = check_response("No cartao fica 12x de R$ 100.", CANON)
    assert v.decision == "allow"
    assert v.findings == ()


def test_plano_conta_errada_block():
    # valor da parcela certo (100), mas 20x != 12x canonico -> block (teeth aritmetica).
    v = check_response("No cartao fica 20x de R$ 100.", CANON)
    assert v.decision == "block"
    assert v.findings[0].kind == "installment"
    assert v.findings[0].value == 100.0
    assert v.findings[0].reason == "no_structured_match"


def test_plano_valor_parcela_inventado_block():
    v = check_response("No cartao fica 12x de R$ 150.", CANON)
    assert v.decision == "block"
    assert v.findings[0].kind == "installment"
    assert v.findings[0].value == 150.0
    assert v.findings[0].reason == "unknown_number"


def test_plano_total_derivado_certo_allow():
    # 12x de R$ 100 = 1200 derivado; o total afirmado nao precisa estar no canonical.
    v = check_response("Fica 12x de R$ 100, total de R$ 1.200.", CANON)
    assert v.decision == "allow"


def test_plano_total_derivado_errado_block():
    # 12x de R$ 100 = 1200, mas afirma total 1500 -> 1500 nao confere -> block.
    v = check_response("Fica 12x de R$ 100, total de R$ 1.500.", CANON)
    assert v.decision == "block"
    assert 1500.0 in {f.value for f in v.findings}


def test_plano_com_entrada_certa_allow():
    v = check_response("No cartao, 10x de R$ 120 com entrada de R$ 200.", CANON_ENTRADA)
    assert v.decision == "allow"


def test_plano_entrada_errada_block():
    # 10x de R$ 120 certos, mas entrada 500 != 200 canonica -> block.
    v = check_response("No cartao, 10x de R$ 120 com entrada de R$ 500.", CANON_ENTRADA)
    assert v.decision == "block"


def test_plano_sem_installments_preserva_item1():
    # PricePoint legado (installments=None): contagem NAO exigida (comportamento Item 1).
    legacy = CanonicalFacts(
        prices=(PricePoint("card_installment", 100.0, "cartao"),),
        other_numbers=(),
    )
    assert check_response("No cartao fica 10x de R$ 100.", legacy).decision == "allow"
    assert check_response("No cartao fica 99x de R$ 100.", legacy).decision == "allow"


def test_loader_parseia_campos_de_parcelamento():
    canon = canonical_from_mapping(
        {
            "prices": [
                {
                    "modality": "card_installment",
                    "value": 100.0,
                    "installments": 12,
                    "down_payment": 200.0,
                }
            ]
        }
    )
    pp = canon.prices[0]
    assert pp.installments == 12
    assert pp.down_payment == 200.0


def test_loader_sem_campos_novos_e_item1():
    canon = canonical_from_mapping({"prices": [{"modality": "upfront", "value": 1000}]})
    pp = canon.prices[0]
    assert pp.installments is None
    assert pp.down_payment == 0.0

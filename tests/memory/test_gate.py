"""Golden determinístico do gate financeiro (Item 2) - sem LLM (design §7)."""
from commercial_reasoner.memory.gate import check_response
from commercial_reasoner.memory.types import CanonicalFacts, PricePoint

CANON = CanonicalFacts(
    prices=(
        PricePoint("upfront", 1000.0, "à vista (PIX/boleto)"),
        PricePoint("card_installment", 100.0, "cartão 10x"),
    ),
    other_numbers=(2000.0, 10.0),  # valor cheio + desconto 10%
)


def test_valor_confere_structured_allow():
    v = check_response("À vista fica R$ 1.000.", CANON)
    assert v.decision == "allow"
    assert v.findings == ()


def test_valor_na_tabela_sem_modalidade_allow_D1():
    # 2.000 existe no canonical (valor cheio), sem modalidade afirmada -> passa.
    v = check_response("O investimento total é R$ 2.000.", CANON)
    assert v.decision == "allow"


def test_valor_inventado_block_unknown():
    v = check_response("Consigo fazer por R$ 1.500 pra você.", CANON)
    assert v.decision == "block"
    assert len(v.findings) == 1
    f = v.findings[0]
    assert f.value == 1500.0
    assert f.kind == "amount"
    assert f.reason == "unknown_number"


def test_desconto_percent_errado_block():
    v = check_response("Fecho com 20% de desconto.", CANON)
    assert v.decision == "block"
    assert v.findings[0].kind == "percent"
    assert v.findings[0].value == 20.0
    assert v.findings[0].reason == "unknown_number"


def test_desconto_percent_certo_allow():
    v = check_response("Tenho 10% de desconto pra você.", CANON)
    assert v.decision == "allow"


def test_parcelamento_errado_block_installment():
    v = check_response("No cartão fica 10x de R$ 150.", CANON)
    assert v.decision == "block"
    assert v.findings[0].kind == "installment"
    assert v.findings[0].value == 150.0


def test_parcelamento_certo_allow():
    v = check_response("No cartão fica 10x de R$ 100.", CANON)
    assert v.decision == "allow"


def test_modalidade_certa_valor_de_outra_block_no_structured_match():
    # 1.000 existe (à vista), mas afirmado no cartão (cartão é 100) -> block.
    v = check_response("No cartão parcelo em R$ 1.000.", CANON)
    assert v.decision == "block"
    assert v.findings[0].reason == "no_structured_match"


def test_sem_dinheiro_allow():
    v = check_response("Quer que eu já reserve sua vaga?", CANON)
    assert v.decision == "allow"


def test_falha_fechada_sem_canonical_block():
    v = check_response("À vista fica R$ 1.000.", None)
    assert v.decision == "block"
    assert v.findings[0].reason == "unknown_number"


def test_multiplos_numeros_um_confere_outro_nao_block():
    v = check_response("À vista R$ 1.000, mas posso fazer R$ 800.", CANON)
    assert v.decision == "block"  # 800 inventado
    assert {f.value for f in v.findings} == {800.0}

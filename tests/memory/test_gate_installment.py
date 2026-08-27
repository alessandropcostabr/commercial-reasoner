"""Gate financeiro - verificacao ARITMETICA de parcelamento (design §4/§7).

Sem novos campos: o plano e conferido contra as modalidades irmas do canonical
(`<familia>_installment` / `_total` / `installment_plan_downpayment`). A contagem
sai derivada: (total - entrada) / valor da parcela.
"""
from commercial_reasoner.memory.gate import check_response
from commercial_reasoner.memory.types import CanonicalFacts, PricePoint

# Cartao: parcela 100, total 1200 -> 12x derivado (sem entrada).
CANON_CARD = CanonicalFacts(
    prices=(
        PricePoint("upfront", 1000.0, "a vista"),
        PricePoint("card_installment", 100.0, "cartao parcela"),
        PricePoint("card_total", 1200.0, "cartao total"),
    ),
    other_numbers=(10.0,),
)

# Boleto: parcela 250, entrada 200, total 1200 -> (1200-200)/250 = 4x derivado.
CANON_BOLETO = CanonicalFacts(
    prices=(
        PricePoint("installment_plan_installment", 250.0, "boleto parcela"),
        PricePoint("installment_plan_downpayment", 200.0, "boleto entrada"),
        PricePoint("installment_plan_total", 1200.0, "boleto total"),
    ),
    other_numbers=(),
)

# Legado (Item 1): so a parcela, sem total -> contagem NAO exigida.
CANON_LEGACY = CanonicalFacts(
    prices=(PricePoint("card_installment", 100.0, "cartao"),),
    other_numbers=(),
)


def test_plano_conta_e_valor_certos_allow():
    v = check_response("No cartao fica 12x de R$ 100.", CANON_CARD)
    assert v.decision == "allow"
    assert v.findings == ()


def test_plano_conta_errada_block():
    # parcela certa (100), mas 20x != 12x derivado -> block (teeth aritmetica).
    v = check_response("No cartao fica 20x de R$ 100.", CANON_CARD)
    assert v.decision == "block"
    assert v.findings[0].kind == "installment"
    assert v.findings[0].value == 100.0
    assert v.findings[0].reason == "no_structured_match"


def test_plano_valor_parcela_inventado_block():
    v = check_response("No cartao fica 12x de R$ 150.", CANON_CARD)
    assert v.decision == "block"
    assert v.findings[0].kind == "installment"
    assert v.findings[0].value == 150.0
    assert v.findings[0].reason == "unknown_number"


def test_plano_total_afirmado_certo_allow():
    # total derivado (1200) liberado sem estar em other_numbers.
    v = check_response("No cartao, 12x de R$ 100, total de R$ 1.200.", CANON_CARD)
    assert v.decision == "allow"


def test_plano_total_afirmado_errado_block():
    v = check_response("No cartao, 12x de R$ 100, total de R$ 1.500.", CANON_CARD)
    assert v.decision == "block"
    assert 1500.0 in {f.value for f in v.findings}


def test_boleto_plano_com_entrada_certo_allow():
    # cobre installment_plan_installment como valor-de-parcela (achado Codex).
    v = check_response("No boleto parcelado, 4x de R$ 250 com entrada de R$ 200.", CANON_BOLETO)
    assert v.decision == "allow"


def test_boleto_entrada_errada_block():
    v = check_response("No boleto parcelado, 4x de R$ 250 com entrada de R$ 500.", CANON_BOLETO)
    assert v.decision == "block"


def test_consumo_por_span_nao_suprime_percent_homonimo():
    # 100 da parcela nao pode "consumir" o 100% invalido (achado Codex/CodeRabbit).
    v = check_response("No cartao, 12x de R$ 100 e 100% de desconto.", CANON_CARD)
    assert v.decision == "block"
    assert v.findings[0].kind == "percent"
    assert v.findings[0].value == 100.0


def test_total_derivado_em_centavos_allow():
    # 3x de R$ 0,10 = R$ 0,30; float puro daria 0.30000000000000004 (achado CodeRabbit).
    cents = CanonicalFacts(
        prices=(
            PricePoint("card_installment", 0.10, "parcela"),
            PricePoint("card_total", 0.30, "total"),
        ),
        other_numbers=(),
    )
    v = check_response("No cartao, 3x de R$ 0,10, total de R$ 0,30.", cents)
    assert v.decision == "allow"


def test_conta_sem_x_tambem_verifica():
    # "N parcelas"/"N vezes" sem o "x" (achado Codex).
    assert check_response("No cartao, 12 parcelas de R$ 100.", CANON_CARD).decision == "allow"
    assert check_response("No cartao, 20 parcelas de R$ 100.", CANON_CARD).decision == "block"


def test_plano_sem_total_preserva_item1():
    # canonical legado (sem total): contagem NAO exigida (comportamento Item 1).
    assert check_response("No cartao fica 10x de R$ 100.", CANON_LEGACY).decision == "allow"
    assert check_response("No cartao fica 99x de R$ 100.", CANON_LEGACY).decision == "allow"


def test_total_do_plano_nao_libera_outra_modalidade():
    # 1.200 e o total do plano, mas afirmado como a vista (que e 1.000) -> block.
    # allowed_totals por valor liberava isso (achado Codex); agora e por contexto.
    v = check_response("No cartao, 12x de R$ 100; a vista fica R$ 1.200.", CANON_CARD)
    assert v.decision == "block"
    assert 1200.0 in {f.value for f in v.findings}


def test_total_com_palavra_total_ainda_libera():
    v = check_response("No cartao, 12x de R$ 100; total de R$ 1.200.", CANON_CARD)
    assert v.decision == "allow"


def test_conta_com_conectores_verifica():
    # "N parcelas no valor de R$ X" e "N vezes por R$ X" (achado Codex).
    assert check_response("No cartao, 12 parcelas no valor de R$ 100.", CANON_CARD).decision == "allow"
    assert check_response("No cartao, 20 parcelas no valor de R$ 100.", CANON_CARD).decision == "block"
    assert check_response("No cartao, 12 vezes por R$ 100.", CANON_CARD).decision == "allow"
    assert check_response("No cartao, 20 vezes por R$ 100.", CANON_CARD).decision == "block"

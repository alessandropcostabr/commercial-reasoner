"""Classificador deterministico de commitment_category - testes golden (sem LLM)."""
import pytest

from commercial_reasoner.service.commitment import classify_commitment
from commercial_reasoner.service.contract import CommitmentCategory


@pytest.mark.parametrize(
    "text,expected",
    [
        ("O curso custa R$ 1.200 e ja garante sua vaga.", CommitmentCategory.PRECO),
        ("Consigo 10% de desconto pra voce.", CommitmentCategory.DESCONTO),
        ("Tem desconto especial se fechar hoje.", CommitmentCategory.DESCONTO),
        ("Pode pagar em 12x no cartao.", CommitmentCategory.FORMA_PAGAMENTO),
        ("Aceitamos pix ou boleto parcelado.", CommitmentCategory.FORMA_PAGAMENTO),
        ("A entrega leva 3 dias uteis.", CommitmentCategory.PRAZO),
        ("O frete e gratis pra sua regiao.", CommitmentCategory.FRETE),
        ("Que bom te ver por aqui! Como posso ajudar?", None),
        ("", None),
    ],
)
def test_classify_golden(text, expected):
    assert classify_commitment(text) == expected


def test_priority_desconto_sobre_preco_e_forma():
    # Toca preco + forma_pagamento + desconto -> desconto ganha (o que o humano
    # mais precisa aprovar: concessao discricionaria).
    text = "Fica R$ 1.080 a vista com 10% de desconto, ou 12x no cartao."
    assert classify_commitment(text) == CommitmentCategory.DESCONTO


def test_priority_preco_sobre_forma_pagamento():
    text = "Sao R$ 1.200 e voce pode parcelar no cartao."
    assert classify_commitment(text) == CommitmentCategory.PRECO


def test_priority_frete_sobre_prazo():
    # frete gratis (concessao monetaria) e mais sensivel que o prazo de dias.
    text = "O frete sai gratis e a entrega leva 5 dias."
    assert classify_commitment(text) == CommitmentCategory.FRETE


def test_parcelamento_explicito_sem_palavra_de_modalidade():
    # "12x" sozinho (sem "cartao"/"boleto") ja e forma_pagamento.
    assert classify_commitment("Da pra fechar em 12x.") == CommitmentCategory.FORMA_PAGAMENTO


def test_percentual_isolado_conta_como_desconto():
    # No dominio de vendas, % pre-envio = desconto (alinha com o gate financeiro).
    assert classify_commitment("Aplico 15% pra voce.") == CommitmentCategory.DESCONTO


def test_off_como_substring_nao_e_desconto():
    # "off" dentro de outra palavra nao pode virar desconto (achado Codex).
    assert classify_commitment("Nosso atendimento offline nao para.") is None
    assert classify_commitment("Tem coffee break incluso.") is None


def test_off_palavra_inteira_ainda_e_desconto():
    assert classify_commitment("Fechando hoje, sai com off pra voce.") == CommitmentCategory.DESCONTO

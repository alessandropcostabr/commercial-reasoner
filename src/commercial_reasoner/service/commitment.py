"""Classificador deterministico de `commitment_category` (sem LLM).

Preenche o campo `commitment_category` do envelope: QUE tipo de compromisso a
resposta do agente assume, pro LATE rotear ao gate de aprovacao humana certo.
Deterministico de proposito (CLAUDE.md item 4 - dinheiro nao passa por texto de
LLM): olha marcadores (R$/%/parcela) e palavras-chave na resposta.

Fronteira (igual ao gate financeiro): so CLASSIFICA. Barrar/aprovar/escalar e do
integrador (LATE). Casado com `check_response`, que DECIDE allow/block sobre os
numeros; aqui so rotulamos a categoria.

Escopo (bullet do roadmap): emite `preco`/`prazo`/`forma_pagamento`/`desconto`/
`frete` ou None. `CommitmentCategory.OUTRO` fica pra a via do gerador
(structured output, passo futuro) - um classificador por palavra-chave nao tem
sinal pra "outro compromisso".
"""
from __future__ import annotations

import re
from typing import Optional

from ..memory.numeric_guard import find_modality_hint
from .contract import CommitmentCategory

# "12x", "3 x" -> parcelamento explicito, alem do que find_modality_hint pega
# (cartao/boleto/a vista/pix/parcelado).
_INSTALLMENT_RE = re.compile(r"\b\d+\s*x\b", re.IGNORECASE)

_DISCOUNT_WORDS = ("desconto", "off", "abatimento")
_PRAZO_WORDS = ("prazo", "dias", "semana", "validade", "vencimento")
_FRETE_WORDS = ("frete",)


def classify_commitment(response_text: str) -> Optional[CommitmentCategory]:
    """Categoria do compromisso da resposta do agente, ou None se nao ha nenhum.

    Prioridade (mais sensivel primeiro): desconto > preco > forma_pagamento >
    frete > prazo. O contrato tem UM so campo; se a resposta toca varios, ganha
    o que o humano mais precisa aprovar. Reordenar esta cadeia e a unica mudanca
    se o LATE discordar da prioridade.

    ponytail: classificador por marcador/palavra-chave (fragil por natureza,
    travado por testes golden). Upgrade path = structured output do LLM (passo 3
    do roadmap), que vira via `gen["commitment_category"]` e tem prioridade.
    """
    lowered = response_text.lower()

    # % pre-envio, no dominio de vendas, e concessao de desconto (alinha D2 do
    # gate financeiro: "% (desconto)").
    if "%" in response_text or any(w in lowered for w in _DISCOUNT_WORDS):
        return CommitmentCategory.DESCONTO

    if "r$" in lowered:
        return CommitmentCategory.PRECO

    if find_modality_hint(response_text) is not None or _INSTALLMENT_RE.search(response_text):
        return CommitmentCategory.FORMA_PAGAMENTO

    if any(w in lowered for w in _FRETE_WORDS):
        return CommitmentCategory.FRETE

    if any(w in lowered for w in _PRAZO_WORDS):
        return CommitmentCategory.PRAZO

    return None

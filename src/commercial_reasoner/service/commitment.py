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

from .contract import CommitmentCategory

# "12x", "3 x" -> parcelamento explicito.
_INSTALLMENT_RE = re.compile(r"\b\d+\s*x\b", re.IGNORECASE)

# Aliases de forma de pagamento, palavra inteira. Nao reusa find_modality_hint:
# aquele casa por substring (Item 1), entao "pix" dentro de "pixels" viraria
# FORMA_PAGAMENTO (achado Codex). Aqui e word-bounded p/ classificar compromisso.
# `parcel\w*` cobre o substantivo ("3 parcelas") alem do adjetivo ("parcelado")
# (achado Codex).
_MODALITY_RE = re.compile(
    r"\b(?:pix|cart[aã]o|boleto|[aà]\s+vista|parcel\w*)\b", re.IGNORECASE
)

# Palavra inteira: "off" como substring casava "offline"/"coffee" -> falso
# desconto (achado Codex). Plurais cobertos por `s?`.
_DISCOUNT_RE = re.compile(r"\b(?:descontos?|off|abatimentos?)\b", re.IGNORECASE)

# Prazo: dias so contam com numero na frente ("1 dia", "2 dias") - "dia" cru
# pegaria "bom dia" (achado Codex: singular + token-aware). Demais sao keywords.
_PRAZO_RE = re.compile(
    r"\b(?:prazo|semanas?|validade|vencimento)\b|\b\d+\s*dias?\b", re.IGNORECASE
)
_FRETE_WORDS = ("frete",)


def classify_commitment(response_text: str) -> Optional[CommitmentCategory]:
    """Categoria do compromisso da resposta do agente, ou None se nao ha nenhum.

    Prioridade (mais sensivel primeiro): desconto > preco > forma_pagamento >
    frete > prazo. O contrato tem UM so campo; se a resposta toca varios, ganha
    o que o humano mais precisa aprovar. Reordenar esta cadeia e a unica mudanca
    se o LATE discordar da prioridade.

    ponytail: teto ACEITO (decisao do dono do repo) - com multiplos compromissos
    numa resposta, so a categoria de maior prioridade e emitida; uma de menor
    prioridade que a conta exija aprovar (ex.: PRAZO) nao aparece (achado Codex
    P1). Emitir todas exigiria commitment_category=lista no contrato + LATE;
    fica pro structured output do LLM (passo 3) e/ou 1 compromisso por resposta.

    ponytail: classificador por marcador/palavra-chave (fragil por natureza,
    travado por testes golden). Upgrade path = structured output do LLM (passo 3
    do roadmap), que vira via `gen["commitment_category"]` e tem prioridade.
    """
    lowered = response_text.lower()

    # Exige CONTEXTO de desconto (palavra desconto/off/abatimento). Um `%` cru
    # nao basta: "100% presencial"/"frequencia 75%" nao sao desconto (achado
    # Codex). "10% de desconto"/"50% off" ainda batem via a palavra.
    if _DISCOUNT_RE.search(response_text):
        return CommitmentCategory.DESCONTO

    if "r$" in lowered:
        return CommitmentCategory.PRECO

    if _MODALITY_RE.search(response_text) or _INSTALLMENT_RE.search(response_text):
        return CommitmentCategory.FORMA_PAGAMENTO

    if any(w in lowered for w in _FRETE_WORDS):
        return CommitmentCategory.FRETE

    if _PRAZO_RE.search(response_text):
        return CommitmentCategory.PRAZO

    return None

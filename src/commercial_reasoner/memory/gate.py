"""Gate financeiro pre-envio (Item 2) - decisao DETERMINISTICA, sem LLM.

Design: docs/2026-08-24-gate-financeiro-design.md. `check_response` barra valor
financeiro (R$ / % / parcela) que NAO confere com o canonical.

Fronteira (D3/§5): a lib so DECIDE e EXPLICA. Enviar a resposta-segura (template
da config) e escalar humano e do INTEGRADOR (LATE), fora deste repo.

Falha fechada (§6): sem canonical, ou numero ambiguo => block. Um falso-block e
seguro; um falso-allow (mandar preco errado a cliente real) nao.

Cobertura deste incremento: R$ (amount) e % (percent) conferidos contra o
canonical; parcela (installment) conferida por modalidade+valor via
`find_structured_match`. A verificacao ARITMETICA do plano de parcelamento
(n parcelas x valor + entrada = total) exige estender o canonical (design §4) -
follow-up; ate la, parcela sem match estruturado = block (conservador).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .numeric_guard import (
    _NUMBER_RE,
    find_modality_hint,
    find_structured_match,
    is_within_canonical,
    parse_number,
    split_sentences,
)
from .types import CanonicalFacts

GateDecision = Literal["allow", "block"]
FindingKind = Literal["amount", "percent", "installment"]
GateReason = Literal["unknown_number", "no_structured_match"]

_INSTALLMENT_MODALITIES = ("card_installment", "installment_plan_total")


@dataclass(frozen=True)
class GateFinding:
    text: str
    value: float
    kind: FindingKind
    reason: GateReason


@dataclass(frozen=True)
class GateVerdict:
    decision: GateDecision
    findings: tuple[GateFinding, ...]


def check_response(
    response_text: str, canonical_facts: Optional[CanonicalFacts]
) -> GateVerdict:
    findings: list[GateFinding] = []

    for sentence in split_sentences(response_text or ""):
        modality = find_modality_hint(sentence)
        is_installment = modality in _INSTALLMENT_MODALITIES

        for match in _NUMBER_RE.finditer(sentence):
            amount_raw = match.group(1)  # R$...
            percent_raw = match.group(2)  # ...%
            raw = amount_raw or percent_raw
            if raw is None:
                continue
            value = parse_number(raw)
            kind: FindingKind = (
                "percent"
                if percent_raw is not None
                else ("installment" if is_installment else "amount")
            )

            # Falha fechada: sem canonical nada confere.
            if canonical_facts is None:
                findings.append(GateFinding(sentence, value, kind, "unknown_number"))
                continue

            # Modalidade + valor batem => confere.
            if find_structured_match(value, modality, canonical_facts) is not None:
                continue

            if not is_within_canonical(value, canonical_facts):
                # Numero inventado: nao existe na tabela.
                findings.append(GateFinding(sentence, value, kind, "unknown_number"))
            elif modality is not None:
                # Valor existe na tabela, mas NAO para a modalidade afirmada
                # (ex.: "a vista R$ 1.200" quando a vista e R$ 1.000).
                findings.append(GateFinding(sentence, value, kind, "no_structured_match"))
            # else: valor na tabela, sem modalidade afirmada => allow (D1: menciona
            # valor correto passa livre; nao ha gate sobre oferta valida).

    return GateVerdict("block" if findings else "allow", tuple(findings))

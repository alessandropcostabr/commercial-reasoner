"""Gate financeiro pre-envio (Item 2) - decisao DETERMINISTICA, sem LLM.

Design: docs/2026-08-24-gate-financeiro-design.md. `check_response` barra valor
financeiro (R$ / % / parcela) que NAO confere com o canonical.

Fronteira (D3/§5): a lib so DECIDE e EXPLICA. Enviar a resposta-segura (template
da config) e escalar humano e do INTEGRADOR (LATE), fora deste repo.

Falha fechada (§6): sem canonical, ou numero ambiguo => block. Um falso-block e
seguro; um falso-allow (mandar preco errado a cliente real) nao.

Cobertura: R$ (amount) e % (percent) conferidos contra o canonical; parcela
(installment) conferida ARITMETICAMENTE (design §4) - o plano afirmado
(nº parcelas x valor da parcela + entrada) tem que casar um plano canonico, e o
total sai DERIVADO (installments * valor + entrada), sem precisar repeti-lo no
canonical. Plano legado sem `installments` cai no comportamento do Item 1
(contagem nao exigida).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .numeric_guard import (
    _INSTALLMENT_MODALITIES,
    _NUMBER_RE,
    find_installment_exprs,
    find_modality_hint,
    find_structured_match,
    is_within_canonical,
    match_installment_plan,
    parse_number,
    plan_verified_values,
    split_sentences,
)
from .types import CanonicalFacts

GateDecision = Literal["allow", "block"]
FindingKind = Literal["amount", "percent", "installment"]
GateReason = Literal["unknown_number", "no_structured_match"]


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

        # --- Parcelamento: plano afirmado (conta x parcela + entrada) vs canonical.
        # Valores ja explicados por um plano conferido nao voltam ao loop generico.
        consumed: set[float] = set()
        for expr in find_installment_exprs(sentence):
            if canonical_facts is None:
                findings.append(GateFinding(sentence, expr.value, "installment", "unknown_number"))
                consumed.add(expr.value)
                if expr.down is not None:
                    consumed.add(expr.down)
                continue
            plan = match_installment_plan(expr, modality, canonical_facts)
            if plan is not None:
                consumed |= plan_verified_values(plan, expr)
            else:
                # Plano nao confere: valor da parcela inventado, ou conta/entrada
                # erradas p/ um valor que existe (contagem e a teeth aritmetica).
                reason: GateReason = (
                    "no_structured_match"
                    if is_within_canonical(expr.value, canonical_facts)
                    else "unknown_number"
                )
                findings.append(GateFinding(sentence, expr.value, "installment", reason))
                consumed.add(expr.value)
                if expr.down is not None:
                    consumed.add(expr.down)

        # --- Loop generico: R$/% restantes (pula os ja explicados pelo plano).
        for match in _NUMBER_RE.finditer(sentence):
            amount_raw = match.group(1)  # R$...
            percent_raw = match.group(2)  # ...%
            raw = amount_raw or percent_raw
            if raw is None:
                continue
            value = parse_number(raw)
            if value in consumed:
                continue
            kind: FindingKind = (
                "percent"
                if percent_raw is not None
                else ("installment" if is_installment else "amount")
            )

            # Falha fechada: sem canonical nada confere.
            if canonical_facts is None:
                findings.append(GateFinding(sentence, value, kind, "unknown_number"))
                continue

            # Percentual so confere contra os percentuais canonicos (other_numbers).
            # NAO usar find_structured_match: ele casa PricePoint.value, entao
            # "100% de desconto" passaria por coincidir com um preco de valor 100
            # (achado CodeRabbit). Preco/parcela seguem por find_structured_match.
            if kind == "percent":
                if value not in canonical_facts.other_numbers:
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

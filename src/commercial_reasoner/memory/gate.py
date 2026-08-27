"""Gate financeiro pre-envio (Item 2) - decisao DETERMINISTICA, sem LLM.

Design: docs/2026-08-24-gate-financeiro-design.md. `check_response` barra valor
financeiro (R$ / % / parcela) que NAO confere com o canonical.

Fronteira (D3/§5): a lib so DECIDE e EXPLICA. Enviar a resposta-segura (template
da config) e escalar humano e do INTEGRADOR (LATE), fora deste repo.

Falha fechada (§6): sem canonical, ou numero ambiguo => block. Um falso-block e
seguro; um falso-allow (mandar preco errado a cliente real) nao.

Parcelamento (design §4) e conferido ARITMETICAMENTE contra as modalidades irmas
do canonical (`<familia>_installment`/`_total`/`_downpayment`), sem novos campos:
a contagem sai derivada ((total - entrada)/parcela). Os tokens que um plano
CONFERIDO explica sao consumidos POR POSICAO (span), nao por valor - senao um
token financeiro invalido com o mesmo numero (ex.: "100% de desconto" vs parcela
de R$ 100) escaparia (achado Codex/CodeRabbit). Familia sem total => contagem
nao exigida (comportamento Item 1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .numeric_guard import (
    _NUMBER_RE,
    _money_eq,
    check_installment_plan,
    families_mentioned,
    find_entrada_exprs,
    find_installment_exprs,
    find_modality_hint,
    find_structured_match,
    find_total_exprs,
    is_within_canonical,
    parse_number,
    split_sentences,
)
from .types import CanonicalFacts

GateDecision = Literal["allow", "block"]
FindingKind = Literal["amount", "percent", "installment"]
GateReason = Literal["unknown_number", "no_structured_match"]

# So p/ rotular o `kind` de um numero solto em frase de parcela (find_modality_hint
# so retorna estes dois rotulos de parcela).
_INSTALLMENT_HINT_MODALITIES = ("card_installment", "installment_plan_total")


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


def _in_spans(pos: int, spans: set[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def check_response(
    response_text: str, canonical_facts: Optional[CanonicalFacts]
) -> GateVerdict:
    findings: list[GateFinding] = []

    for sentence in split_sentences(response_text or ""):
        modality = find_modality_hint(sentence)
        is_installment = modality in _INSTALLMENT_HINT_MODALITIES

        # --- Parcelamento: plano afirmado (conta x parcela + entrada) vs canonical.
        consumed_spans: set[tuple[int, int]] = set()
        exprs = find_installment_exprs(sentence)
        entradas = find_entrada_exprs(sentence)
        totals = find_total_exprs(sentence)

        # Falha fechada (§6) na AMBIGUIDADE: a ligacao familia/entrada/total e
        # por-FRASE, entao 2+ familias, 2+ planos, 2+ entradas ou 2+ totais numa
        # frase nao dao pra vincular com seguranca -> bloqueia (escala), nunca
        # arrisca falso-allow (ex.: boleto 12x100 conferido como cartao; total de
        # outra familia liberado por coincidir valor) (achados Codex).
        ambiguous = (
            len(families_mentioned(sentence)) >= 2
            or len(exprs) >= 2
            or len(entradas) >= 2
            or len(totals) >= 2
        )
        if exprs and ambiguous:
            for expr in exprs:
                findings.append(GateFinding(sentence, expr.value, "installment", "no_structured_match"))
                consumed_spans.add(expr.span)
            for _, espan in entradas:
                consumed_spans.add(espan)
            for _, tspan in totals:
                consumed_spans.add(tspan)
        else:
            # Caminho de plano UNICO (<=1 plano, <=1 familia/entrada/total).
            confirmed_totals: list[float] = []
            for expr in exprs:
                if canonical_facts is None:
                    findings.append(GateFinding(sentence, expr.value, "installment", "unknown_number"))
                    consumed_spans.add(expr.span)
                    if expr.down_span is not None:
                        consumed_spans.add(expr.down_span)
                    continue
                verdict = check_installment_plan(expr, sentence, canonical_facts)
                consumed_spans.add(expr.span)
                if expr.down_span is not None:
                    consumed_spans.add(expr.down_span)
                if verdict.confers:
                    if verdict.family_total is not None:
                        confirmed_totals.append(verdict.family_total)
                else:
                    reason: GateReason = (
                        "no_structured_match"
                        if is_within_canonical(expr.value, canonical_facts)
                        else "unknown_number"
                    )
                    findings.append(GateFinding(sentence, expr.value, "installment", reason))

            # Total AFIRMADO ("total R$ T") do plano unico conferido: consumido por
            # CONTEXTO+valor (span do "total"). Sem ambiguidade, o unico total so
            # pode ser da unica familia presente.
            if confirmed_totals:
                for tval, tspan in totals:
                    if any(_money_eq(tval, ct) for ct in confirmed_totals):
                        consumed_spans.add(tspan)

        # --- Loop generico: R$/% restantes (pula os spans ja explicados pelo plano).
        for match in _NUMBER_RE.finditer(sentence):
            if _in_spans(match.start(), consumed_spans):
                continue
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

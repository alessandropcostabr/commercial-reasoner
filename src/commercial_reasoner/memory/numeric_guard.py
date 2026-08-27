import re
from dataclasses import dataclass
from typing import Optional

from .types import AuditRecord, CanonicalFacts, Fact, PricePoint

# Formato pt-BR. Duas alternativas por proposito: com separador de milhar COMPLETO
# ("1.200") ou sequencia livre de digitos ("1200") - o `*` do regex antigo casava so
# os 3 primeiros digitos de "1200" e truncava pra 120 (achado C-2).
_PT_BR_NUMBER = r"\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+(?:,\d{2})?"

# Numero ancorado em marcador de valor (R$ ou %) - usado na fala do AGENTE.
_NUMBER_RE = re.compile(rf"R\$\s*({_PT_BR_NUMBER})|({_PT_BR_NUMBER})\s*%")

# Qualquer numero, com ou sem marcador - usado so na fala do CLIENTE, onde nenhum
# numero pode escapar da checagem anti-injecao (achado C-3).
_ANY_NUMBER_RE = re.compile(_PT_BR_NUMBER)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_CENTS = 2  # dinheiro pt-BR: 2 casas. round evita erro binario de float (achado CodeRabbit).


def _money_eq(a: float, b: float) -> bool:
    return round(a, _CENTS) == round(b, _CENTS)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


_MODALITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "upfront": ("a vista", "à vista", "pix"),
    "card_installment": ("cartao", "cartão"),
    "installment_plan_total": ("boleto parcelado", "parcelado"),
}


def parse_number(raw: str) -> float:
    cleaned = raw.replace("R$", "").replace("%", "").strip()
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(".", "")
    return float(cleaned)


def extract_numbers(text: str) -> list[float]:
    numbers = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw:
            numbers.append(parse_number(raw))
    return numbers


def extract_all_numbers(text: str) -> list[float]:
    return [parse_number(m.group(0)) for m in _ANY_NUMBER_RE.finditer(text)]


def find_modality_hint(sentence: str) -> Optional[str]:
    lowered = sentence.lower()
    for modality, keywords in _MODALITY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return modality
    return None


def is_within_canonical(value: float, canonical_facts: CanonicalFacts) -> bool:
    all_values = {p.value for p in canonical_facts.prices} | set(canonical_facts.other_numbers)
    return value in all_values


def find_structured_match(
    value: float, modality_hint: Optional[str], canonical_facts: CanonicalFacts
) -> Optional[PricePoint]:
    if modality_hint is None:
        return None
    for price in canonical_facts.prices:
        if price.modality == modality_hint and price.value == value:
            return price
    return None


def classify_client_number(value: float, canonical_facts: CanonicalFacts) -> Optional[PricePoint]:
    for price in canonical_facts.prices:
        if price.value == value:
            return price
    return None


# --- Verificacao aritmetica de parcelamento (design gate §4) -----------------
# SEM novos campos no schema: o canonical ja modela o plano em modalidades irmas
# (convencao da fixture) - `<familia>_installment` (valor da parcela),
# `<familia>_total` (total), `installment_plan_downpayment` (entrada). A contagem
# de parcelas sai DERIVADA: (total - entrada) / valor da parcela.

# Modalidades cujo PricePoint.value e o VALOR DA PARCELA.
_INSTALLMENT_VALUE_MODALITIES = ("card_installment", "installment_plan_installment")

# familia -> (modalidade do total, modalidade da entrada | None).
_PLAN_FAMILY: dict[str, tuple[str, Optional[str]]] = {
    "card": ("card_total", None),
    "installment_plan": ("installment_plan_total", "installment_plan_downpayment"),
}

_FAMILY_ALIASES: dict[str, tuple[str, ...]] = {
    "card": ("cartao", "cartão"),
    "installment_plan": ("boleto", "parcelad"),
}

# "12x de R$ 100", "12 parcelas de R$ 100", "12 vezes de R$ 100", e variantes com
# conectores: "20 parcelas no valor de R$ 100", "20 vezes por R$ 100" (achados
# Codex: a contagem aparece sem "x" e com conectivos). Os conectores sao um
# WHITELIST de palavras (nao texto livre) p/ nao emparelhar a contagem com um R$
# de outra parte da frase. Palavra de modalidade entre a conta e o R$ nao e
# coberta - ceiling documentado.
_PLAN_RE = re.compile(
    rf"(\d+)\s*(?:x|vezes?|parcelas?)\b(?:\s+(?:de|por|a|no|valor|em)){{0,4}}\s*R\$\s*({_PT_BR_NUMBER})",
    re.IGNORECASE,
)
_ENTRADA_RE = re.compile(rf"entrada\s*(?:de\s+)?R\$\s*({_PT_BR_NUMBER})", re.IGNORECASE)
# Total AFIRMADO de um plano: "total de R$ 1.200". Consumido por CONTEXTO (a
# palavra "total") + valor batendo o total canonico - nunca por valor solto,
# senao "a vista fica R$ 1.200" (outra modalidade) seria liberado (achado Codex).
_TOTAL_RE = re.compile(rf"total\s*(?:de\s+)?R\$\s*({_PT_BR_NUMBER})", re.IGNORECASE)


def _family_of(modality: str) -> Optional[str]:
    if modality.startswith("card"):
        return "card"
    if modality.startswith("installment_plan"):
        return "installment_plan"
    return None


def _family_hint(sentence: str) -> Optional[str]:
    lowered = sentence.lower()
    for family, aliases in _FAMILY_ALIASES.items():
        if any(a in lowered for a in aliases):
            return family
    return None


@dataclass(frozen=True)
class InstallmentExpr:
    count: int
    value: float  # valor da parcela afirmado
    span: tuple[int, int]  # trecho "12x de R$ 100" na frase (consumo por posicao)
    down: Optional[float]  # entrada afirmada (None = nao mencionada)
    down_span: Optional[tuple[int, int]]


@dataclass(frozen=True)
class PlanVerdict:
    confers: bool
    family_total: Optional[float]  # total da familia (p/ consumir um total afirmado)


def find_installment_exprs(sentence: str) -> list[InstallmentExpr]:
    """Planos de parcelamento afirmados na frase (conta x valor da parcela)."""
    down_m = _ENTRADA_RE.search(sentence)
    down = parse_number(down_m.group(1)) if down_m else None
    down_span = down_m.span() if down_m else None
    return [
        InstallmentExpr(
            count=int(m.group(1)),
            value=parse_number(m.group(2)),
            span=m.span(),
            down=down,
            down_span=down_span,
        )
        for m in _PLAN_RE.finditer(sentence)
    ]


def find_total_exprs(sentence: str) -> list[tuple[float, tuple[int, int]]]:
    """Totais AFIRMADOS ("total de R$ T") na frase, com valor e span."""
    return [(parse_number(m.group(1)), m.span()) for m in _TOTAL_RE.finditer(sentence)]


def check_installment_plan(
    expr: InstallmentExpr, sentence: str, canonical_facts: CanonicalFacts
) -> PlanVerdict:
    """Confere o plano afirmado contra as modalidades irmas do canonical.

    Acha a modalidade de parcela cujo value == expr.value (respeitando a familia
    se o texto disser cartao/boleto). Se a familia tem TOTAL, deriva a contagem
    ((total - entrada) / parcela) e exige expr.count == derivada + aritmetica
    consistente. Sem total (canonical legado do Item 1), a contagem NAO e exigida.
    Entrada afirmada tem que casar a da familia.
    """
    fam_hint = _family_hint(sentence)
    by_mod = {p.modality: p.value for p in canonical_facts.prices}

    family: Optional[str] = None
    per_value: Optional[float] = None
    for p in canonical_facts.prices:
        if p.modality not in _INSTALLMENT_VALUE_MODALITIES:
            continue
        if not _money_eq(p.value, expr.value):
            continue
        fam = _family_of(p.modality)
        if fam_hint is not None and fam != fam_hint:
            continue
        family, per_value = fam, p.value
        break
    if family is None or per_value is None:
        return PlanVerdict(False, None)

    total_mod, down_mod = _PLAN_FAMILY[family]
    total = by_mod.get(total_mod)
    down = by_mod.get(down_mod) if down_mod is not None else 0.0
    if down is None:
        down = 0.0

    if expr.down is not None and not _money_eq(expr.down, down):
        return PlanVerdict(False, None)

    if total is not None:
        billed = total - down
        if per_value <= 0:
            return PlanVerdict(False, None)
        derived = round(billed / per_value)
        if derived != expr.count or not _money_eq(derived * per_value, billed):
            return PlanVerdict(False, None)

    return PlanVerdict(True, total)


def check_quote(
    agent_response: str, canonical_facts: CanonicalFacts
) -> tuple[list[Fact], list[AuditRecord]]:
    facts: list[Fact] = []
    audit: list[AuditRecord] = []
    counter = 0

    for sentence in split_sentences(agent_response):
        numbers = extract_numbers(sentence)
        if not numbers:
            continue

        modality_hint = find_modality_hint(sentence)
        for value in numbers:
            structured = find_structured_match(value, modality_hint, canonical_facts)
            if structured is not None:
                counter += 1
                facts.append(
                    Fact(
                        id=f"quote-{counter}",
                        category="quote",
                        source="agent",
                        text=f"{structured.description} ({structured.modality}): {value}",
                        verified=True,
                        confidence="high",
                        value=value,
                    )
                )
            elif is_within_canonical(value, canonical_facts):
                audit.append(
                    AuditRecord(
                        category="quote",
                        source="agent",
                        text=sentence,
                        reason="no_structured_match",
                        raw_text=sentence,
                    )
                )
            else:
                audit.append(
                    AuditRecord(
                        category="quote",
                        source="agent",
                        text=sentence,
                        reason="unknown_number",
                        raw_text=sentence,
                    )
                )

    return facts, audit

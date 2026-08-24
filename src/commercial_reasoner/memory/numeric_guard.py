import re
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

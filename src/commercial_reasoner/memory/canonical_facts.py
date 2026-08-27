from typing import Mapping, Optional

import yaml

from .types import CanonicalFacts, PricePoint


def canonical_from_mapping(data: Optional[Mapping]) -> CanonicalFacts:
    """Constroi CanonicalFacts a partir de um dict.

    E o loader do modelo STATELESS: os fatos da conta chegam no request /reason
    (campo `grounded_facts`), injetados pelo LATE por conta+setor - NAO sao lidos
    por `account_id` da engine (isso amarraria a engine ao estado, quebrando
    multi-canal + concorrencia). Mesma forma do YAML de config:
    `{prices: [{modality, value, description, installments?, down_payment?}],
      other_numbers: [...]}`. `installments`/`down_payment` sao opcionais (design
    gate §4): ausentes => PricePoint identico ao do Item 1.
    """
    data = data or {}
    prices = tuple(
        PricePoint(
            modality=item["modality"],
            value=float(item["value"]),
            description=item.get("description", ""),
            installments=(
                int(item["installments"]) if item.get("installments") is not None else None
            ),
            down_payment=float(item.get("down_payment", 0.0)),
        )
        for item in data.get("prices", [])
    )
    other_numbers = tuple(float(n) for n in data.get("other_numbers", []))
    return CanonicalFacts(prices=prices, other_numbers=other_numbers)


def load_canonical_facts(path: str) -> CanonicalFacts:
    """Carrega CanonicalFacts de um arquivo YAML (uso local/teste).

    Em producao stateless o LATE injeta os fatos no request -> use
    `canonical_from_mapping`. Comportamento inalterado (Item 1).
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return canonical_from_mapping(data)

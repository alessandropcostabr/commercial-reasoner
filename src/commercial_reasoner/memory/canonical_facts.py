import yaml

from .types import CanonicalFacts, PricePoint


def load_canonical_facts(path: str) -> CanonicalFacts:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    prices = tuple(
        PricePoint(
            modality=item["modality"],
            value=float(item["value"]),
            description=item.get("description", ""),
        )
        for item in data.get("prices", [])
    )
    other_numbers = tuple(float(n) for n in data.get("other_numbers", []))

    return CanonicalFacts(prices=prices, other_numbers=other_numbers)

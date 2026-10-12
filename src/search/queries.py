from src.models import Listing
from src.utils.text import normalized


def build_queries(listing: Listing) -> list[str]:
    fragments = [fragment.replace('"', " ").strip() for fragment in listing.fragments[:2]]
    facts = listing.facts
    characteristics = " ".join(part for part in (
        "apartament vânzare București", facts.area, facts.address,
        f"{facts.rooms} camere" if facts.rooms else None,
        f"{facts.surface:g} mp" if facts.surface else None,
        f"etaj {facts.floor}" if facts.floor else None,
    ) if part)
    if fragments:
        exact = " OR ".join(f'"{fragment}"' for fragment in fragments)
        shorter = " ".join(fragments[0].split()[:6])
        return [exact + " apartament București", f'"{normalized(shorter)}" {normalized(characteristics)}']
    return [characteristics, normalized(characteristics + " proprietar")]

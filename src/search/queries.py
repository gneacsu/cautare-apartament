from src.models import Listing
from src.utils.text import normalized


def build_queries(listing: Listing) -> list[str]:
    fragments = [fragment.replace('"', " ").strip() for fragment in listing.fragments[:3]]
    facts = listing.facts
    characteristics = " ".join(part for part in (
        "apartament vânzare București", facts.area, facts.address,
        f"{facts.rooms} camere" if facts.rooms else None,
        f"{facts.surface:g} mp" if facts.surface else None,
        f"etaj {facts.floor}" if facts.floor else None,
    ) if part)
    if fragments:
        exact = " OR ".join(f'"{fragment}"' for fragment in fragments[:2])
        unaccented = " OR ".join(f'"{normalized(fragment)}"' for fragment in fragments)
        shorter = " ".join(fragments[0].split()[:6])
        queries = [
            exact + " apartament București",
            f'"{fragments[-1]}"',  # Broaden the exact search without extra filters.
            unaccented + " apartament bucuresti",
            f'"{normalized(shorter)}" {normalized(characteristics)}',
            characteristics,
            f'site:facebook.com "{normalized(shorter)}" apartament bucuresti',
        ]
    else:
        # No fabricated distinctive fragments when the description is generic.
        location = facts.address or facts.area or "București"
        rooms = f"{facts.rooms} camere" if facts.rooms else "apartament"
        queries = [characteristics, normalized(characteristics),
                   f"apartament vânzare {location} {rooms} proprietar",
                   f"site:facebook.com apartament vanzare {normalized(location)} {rooms}"]
    return list(dict.fromkeys(" ".join(query.split()) for query in queries))

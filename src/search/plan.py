"""Finite, diverse plan: Facebook in the first round, pagination after all first pages."""
from src.models import SearchTask
from src.utils.text import normalized


def build_plan(listing):
    f = listing.facts
    location = f.address or f.area or f.city or "București"
    base = f'apartament vânzare {location}'
    if f.rooms:
        base += f' {f.rooms} camere'
    distinctive = [v.replace('"', ' ').strip() for v in listing.fragments if v.strip()]
    phrase = distinctive[0] if distinctive else base
    tasks = [
        SearchTask(query=f'"{phrase}"' if distinctive else base, category="expresie exactă"),
        SearchTask(query=f'site:facebook.com {normalized(base)}', category="Facebook public"),
        SearchTask(query=f'{base} proprietar', category="caracteristici"),
    ]
    for fragment in distinctive[1:]:
        tasks.append(SearchTask(query=f'"{fragment}"', category="expresie exactă"))
    for domain in ("olx.ro", "storia.ro", "imobiliare.ro", "publi24.ro", "anuntul.ro"):
        tasks.append(SearchTask(query=f'site:{domain} {base}', category="portal"))
    if distinctive:
        tasks.extend([
            SearchTask(query=f'"{normalized(phrase)}"', category="fără diacritice"),
            SearchTask(query=f'"{" ".join(normalized(phrase).split()[:6])}" {normalized(location)}', category="fragment scurt"),
            SearchTask(query=f'site:facebook.com "{normalized(phrase)}"', category="Facebook public"),
        ])
    seen = set()
    return [t for t in tasks if not (t.query in seen or seen.add(t.query))]

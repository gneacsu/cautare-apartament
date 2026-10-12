"""Deterministic evidence gates; the AI's conclusion alone is insufficient."""

from src.models import Assessment, Author, Facts, Listing, Source
from src.utils.text import contains_quote, normalized


class EvidenceError(ValueError):
    pass


def verify_author(author: Author, evidence: list[str]) -> None:
    if author != Author.UNKNOWN and not evidence:
        raise EvidenceError("Clasificarea autorului nu are dovezi în text.")
    if author == Author.AGENCY and evidence and all(
        any(phrase in normalized(quote) for phrase in (
            "nu colaborez cu agentii", "nu colaboreaza cu agentii", "exclus agentii", "fara agentii"))
        for quote in evidence
    ):
        raise EvidenceError("Refuzul colaborării cu agențiile nu este o dovadă că autorul este agent.")


def verify_quotes(quotes: list[str], text: str) -> None:
    if any(not contains_quote(text, quote) for quote in quotes):
        raise EvidenceError("Răspunsul AI conține dovezi care nu apar în sursa disponibilă.")


def validate_listing(listing: Listing, text: str) -> None:
    verify_quotes(listing.author_evidence + listing.fragments, text)
    verify_author(listing.author, listing.author_evidence)


def material_conflicts(first: Facts, second: Facts) -> list[str]:
    conflicts = []
    for field, label in (("rooms", "număr de camere"), ("transaction", "tip de tranzacție"),
                         ("city", "localitate")):
        a, b = getattr(first, field), getattr(second, field)
        if a is not None and b is not None and normalized(str(a)) != normalized(str(b)):
            conflicts.append(f"Diferență de {label}: {a} / {b}.")
    return conflicts


def validate_assessment(result: Assessment, source: Source) -> None:
    verify_quotes(result.evidence + result.author_evidence, source.text)
    verify_author(result.author, result.author_evidence)
    if result.same_property == "probabil" and not result.evidence:
        raise EvidenceError("Potrivirea propusă nu are dovezi.")


def sufficiently_supported(original: Listing, result: Assessment, source: Source) -> bool:
    if result.same_property != "probabil" or result.contradictions:
        return False
    if material_conflicts(original.facts, result.facts):
        return False
    # Distinctive shared text (at least five words), or several independent facts.
    shared = any(len(normalized(fragment).split()) >= 5 and contains_quote(source.text, fragment)
                 for fragment in original.fragments)
    a, b = original.facts, result.facts
    location = any(x and y and normalized(x) == normalized(y)
                   for x, y in ((a.address, b.address), (a.area, b.area)))
    surface = (a.surface is not None and b.surface is not None and a.surface == b.surface
               and a.surface_kind != "necunoscută" and a.surface_kind == b.surface_kind)
    floor = a.floor is not None and b.floor is not None and normalized(a.floor) == normalized(b.floor)
    rooms = a.rooms is not None and a.rooms == b.rooms
    return bool(shared or (location and surface and floor and rooms))

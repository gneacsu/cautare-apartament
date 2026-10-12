"""A new, bounded analysis for every invocation; no global or cached results."""

import time
from collections.abc import Callable
from uuid import uuid4

from pydantic import ValidationError

from src.analyzers.provider import Provider, ProviderError
from src.analyzers.verification import (
    EvidenceError, material_conflicts, sufficiently_supported, validate_assessment, validate_listing,
)
from src.config import Settings
from src.extractors.pages import PageError, PageReader, now
from src.models import Analysis, Author, Result, Source, Status
from src.search.queries import build_queries
from src.utils.urls import InvalidURL, canonical_url, is_facebook


class AnalysisLimit(RuntimeError):
    pass


class Workflow:
    def __init__(self, settings: Settings, provider: Provider, reader: PageReader | None = None):
        self.settings = settings
        self.provider = provider
        self.reader = reader or PageReader(settings)

    def run(self, url: str, manual_text: str,
            progress: Callable[[int, str], None] = lambda *_: None) -> Analysis:
        report = Analysis(id=str(uuid4()), checked_at=now(), input_url=url.strip(), input_text=manual_text.strip())
        deadline = time.monotonic() + self.settings.analysis_seconds
        calls = 0

        def invoke(method, *args):
            nonlocal calls
            remaining = deadline - time.monotonic()
            if remaining <= 0 or calls >= self.settings.max_ai_calls:
                raise AnalysisLimit("Limita de timp sau de apeluri AI a fost atinsă.")
            calls += 1
            output = method(*args, timeout=remaining)
            if time.monotonic() >= deadline:
                raise AnalysisLimit("Limita de timp a analizei a fost atinsă.")
            return output

        try:
            if url.strip():
                url = canonical_url(url)
            else:
                url = ""
            if not manual_text.strip() and not url:
                raise ValueError("Introdu un link sau descrierea unui anunț.")
            if len(manual_text.strip()) > self.settings.max_input_chars:
                raise ValueError(f"Descrierea poate avea cel mult {self.settings.max_input_chars} de caractere.")
            progress(10, "Citesc descrierea anunțului…")
            if manual_text.strip():
                original_source = Source(url=url, title="Descriere furnizată de utilizator",
                                         text=manual_text.strip(), access="manual", accessed_at=now())
            else:
                try:
                    original_source = self.reader.read(url, deadline)
                except PageError as exc:
                    report.sources.append(Source(url=url, access="unavailable", error=str(exc), accessed_at=now()))
                    raise
            report.sources.append(original_source)
            progress(25, "Identific proprietatea și indiciile despre autor…")
            listing = invoke(self.provider.extract, original_source.text)
            validate_listing(listing, original_source.text)
            report.original = listing
            report.limitations.extend(listing.limitations)
            if listing.facts.transaction == "închiriere":
                report.message = "Anunțul este pentru închiriere. Această aplicație caută apartamente de vânzare."
                return report
            if listing.author == Author.OWNER:
                result = Result(url=original_source.final_url or url, title=listing.title, same_property="probabil", author=listing.author,
                                author_evidence=listing.author_evidence, evidence=listing.author_evidence,
                                justification="Autorul anunțului introdus se declară proprietar în descriere.",
                                facts=listing.facts, contradictions=[], verification=original_source.access)
                report.results.append(result)
                report.status = Status.FOUND
                report.message = "Autorul anunțului introdus se declară proprietar. Căutarea s-a oprit."
                if original_source.access == "manual":
                    report.limitations.append("Declarația provine din textul furnizat de utilizator; pagina sursă nu a fost verificată.")
                return report

            uncertain = False
            seen = {url} if url else set()
            seen.update([original_source.final_url] if original_source.final_url else [])
            candidates = 0
            for query in build_queries(listing)[:self.settings.max_searches]:
                progress(40, "Caut apariții ale aceleiași proprietăți…")
                batch = invoke(self.provider.search, query)
                report.queries.append(query)
                report.executed_queries.extend(batch.executed_queries)
                if batch.search_suggestions_html:
                    report.search_suggestions_html.append(batch.search_suggestions_html)
                report.limitations.extend(batch.limitations)
                if not batch.completed:
                    raise ProviderError("Serviciul AI nu a finalizat căutarea web.")
                sources = []
                for hit in batch.hits:
                    try:
                        candidate_url = canonical_url(hit.url)
                    except InvalidURL:
                        uncertain = True
                        report.limitations.append("Un URL returnat de căutare nu a putut fi validat.")
                        continue
                    if candidate_url in seen:
                        continue
                    if candidates >= self.settings.max_candidates:
                        uncertain = True
                        report.limitations.append("Limita de pagini candidate a fost atinsă.")
                        break
                    seen.add(candidate_url)
                    candidates += 1
                    try:
                        if is_facebook(candidate_url):
                            raise PageError("Rezultat Facebook public: verificare manuală necesară.")
                        source = self.reader.read(candidate_url, deadline, self.settings.max_candidate_chars)
                    except PageError as exc:
                        uncertain = True
                        source = Source(url=candidate_url, title=hit.title,
                                        text=hit.snippet[:self.settings.max_candidate_chars],
                                        access="snippet" if hit.snippet else "unavailable",
                                        error=str(exc), accessed_at=now())
                    if source.final_url and source.final_url != candidate_url:
                        final = canonical_url(source.final_url)
                        if final in seen:
                            continue
                        seen.add(final)
                    report.sources.append(source)
                    if source.text:
                        sources.append(source)
                if sources:
                    progress(70, "Compar proprietățile și verific dovezile…")
                    comparison = invoke(self.provider.compare, listing, sources)
                    report.limitations.extend(comparison.limitations)
                    by_url = {source.url: source for source in sources}
                    if comparison.status != "completed":
                        raise ProviderError("Gemini nu a finalizat compararea surselor. Poți reîncerca.")
                    if set(comparison.source_urls) != set(by_url):
                        raise EvidenceError("Răspunsul AI conține o listă de surse incompletă sau necunoscută.")
                    returned = [item.url for item in comparison.results]
                    if len(returned) != len(set(returned)) or set(returned) != set(by_url):
                        raise EvidenceError("Răspunsul AI nu acoperă corect sursele transmise pentru verificare.")
                    # Validate the entire batch before publishing any of its results.
                    for item in comparison.results:
                        validate_assessment(item, by_url[item.url])
                    for item in comparison.results:
                        source = by_url[item.url]
                        item.contradictions.extend(material_conflicts(listing.facts, item.facts))
                        report.evaluations.append(item)
                        supported = sufficiently_supported(listing, item, source)
                        if supported and item.author == Author.OWNER and source.access == "page":
                            result_data = item.model_dump()
                            result_data["url"] = source.final_url or source.url
                            report.results.append(Result(**result_data, verification="page"))
                        elif item.same_property != "diferită" and not item.contradictions:
                            if source.access != "page":
                                report.manual_review.append(Result(**item.model_dump(), verification="snippet"))
                            if item.same_property == "neclar" or item.author == Author.UNKNOWN or not supported:
                                uncertain = True
                if report.results or candidates >= self.settings.max_candidates:
                    break
            if report.results:
                report.status = Status.FOUND
                report.message = "Am identificat declarații de proprietar și indicii de potrivire în paginile citite."
                if uncertain:
                    report.limitations.append("O parte dintre rezultatele căutării nu au putut fi verificate.")
            elif uncertain:
                report.message = "Există surse inaccesibile sau indicii insuficiente pentru o concluzie. Poți reîncerca."
            else:
                report.status = Status.NOT_FOUND
                report.message = "Căutarea limitată s-a încheiat fără o potrivire suficient susținută cu un autor declarat proprietar."
        except (ProviderError, PageError, AnalysisLimit, EvidenceError, InvalidURL, ValidationError, ValueError) as exc:
            report.status = Status.INCOMPLETE
            # Validation errors may contain source text; do not echo raw model payloads.
            report.message = ("Serviciul AI a returnat un răspuns incomplet sau invalid. Poți reîncerca."
                              if isinstance(exc, ValidationError) else str(exc))
            if isinstance(exc, ProviderError):
                report.recovery_hint = exc.recovery_hint
            elif isinstance(exc, PageError) and report.original is None:
                report.recovery_hint = "Copiază descrierea anunțului în câmpul alternativ și pornește din nou verificarea."
        finally:
            report.usage = {**self.provider.usage, "ai_calls": calls}
            report.diagnostics = list(getattr(self.provider, "diagnostics", []))
            report.limitations = list(dict.fromkeys(report.limitations))
            progress(100, "Verificare încheiată.")
        return report

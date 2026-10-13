"""Resumable SerpApi + Gemini workflow. Finite plan, no total token/candidate cap."""
import time
from uuid import uuid4

from pydantic import ValidationError

from src.analyzers.provider import ProviderError
from src.analyzers.verification import EvidenceError, validate_listing, sufficiently_supported
from src.analyzers.workflow import Workflow as EvidenceWorkflow
from src.config import ConfigurationError
from src.extractors.images import collect_signatures, match_images
from src.extractors.pages import PageError, PageReader, now
from src.models import Analysis, Author, Candidate, Checkpoint, Result, SearchTask, Source, Status
from src.search.plan import build_plan
from src.utils.urls import InvalidURL, canonical_url, is_facebook


class Paused(RuntimeError):
    pass


class Pipeline:
    def __init__(self, settings, provider, search, reader=None, image_collector=collect_signatures):
        self.settings, self.provider, self.search = settings, provider, search
        self.reader = reader or PageReader(settings)
        self.image_collector = image_collector

    def run(self, url="", text="", progress=lambda *_: None, report=None,
            checkpoint=lambda _: None, cancelled=lambda: False, manual_only=False):
        report = report.model_copy(deep=True) if report else Analysis(
            id=str(uuid4()), checked_at=now(), input_url=url.strip(), input_text=text.strip())
        if report.results:
            return report
        report.checkpoint = report.checkpoint or Checkpoint()
        state = report.checkpoint
        state.rounds += 1
        report.status = Status.INCOMPLETE
        report.limited = False
        report.limit_reason = ""
        report.recovery_hint = ""
        began = time.monotonic()
        deadline = began + self.settings.analysis_seconds
        previous_usage = dict(report.usage)
        previous_diagnostics = list(report.diagnostics)
        previous_search_calls = list(report.search_calls)
        provider_usage_start = dict(self.provider.usage)
        diagnostics_start = len(getattr(self.provider, "diagnostics", []))
        search_calls_start = len(self.search.calls)
        ai_calls = 0
        for task in state.tasks:
            task.error = ""  # One explicit retry per task on a new round, never an automatic loop.

        def remaining():
            if cancelled():
                raise Paused("Analiza a fost oprită la cererea ta. Progresul este salvat.")
            available = deadline - time.monotonic()
            if available <= 0:
                raise Paused("Timpul acestei runde s-a încheiat. Poți continua de la progresul salvat.")
            return available

        def snapshot(stage):
            state.stage = stage
            report.usage = dict(previous_usage)
            for key, value in self.provider.usage.items():
                report.usage[key] = previous_usage.get(key, 0) + value - provider_usage_start.get(key, 0)
            report.usage["ai_calls"] = previous_usage.get("ai_calls", 0) + ai_calls
            report.search_calls = previous_search_calls + self.search.calls[search_calls_start:]
            report.usage["serpapi_requests"] = len(report.search_calls)
            report.diagnostics = previous_diagnostics + list(getattr(self.provider, "diagnostics", []))[diagnostics_start:]
            report.coverage = {
                "planned_searches": len(state.tasks), "completed_searches": sum(t.done for t in state.tasks),
                "candidate_pages_attempted": sum(c.state != "pending" for c in state.candidates),
                "sources_compared": len(report.evaluations), "candidates_discovered": len(state.candidates),
                "pending_candidates": sum(c.state in {"pending", "read"} for c in state.candidates),
            }
            checkpoint(report.model_copy(deep=True))
            progress(0, stage)

        def invoke(method, *args):
            nonlocal ai_calls
            timeout = min(remaining(), 180)
            ai_calls += 1
            result = method(*args, timeout=timeout)
            # Persist successful responses even if this call took us past the round deadline.
            return result

        def source_for(candidate):
            return next((s for s in report.sources[1:] if s.url == candidate.url), None)

        def enqueue(url, title="", snippet="", origin="pagină consultată", link_depth=0):
            try:
                url = canonical_url(url)
            except InvalidURL:
                return
            if report.sources and url in {report.input_url, report.sources[0].final_url}:
                return
            existing = next((c for c in state.candidates if c.url == url), None)
            if existing:
                if origin not in existing.discovered_by:
                    existing.discovered_by.append(origin)
            else:
                state.candidates.append(Candidate(url=url, title=title, snippet=snippet, discovered_by=[origin], link_depth=link_depth))

        def compare_pending(all_pending=False):
            pending = [source_for(c) for c in state.candidates if c.state == "read"]
            pending = [s for s in pending if s is not None]
            if not all_pending and len(pending) < self.settings.comparison_batch_size:
                return
            for offset in range(0, len(pending), self.settings.comparison_batch_size):
                batch = pending[offset:offset+self.settings.comparison_batch_size]
                comparison = invoke(self.provider.compare, report.original, batch)
                EvidenceWorkflow._accept_comparison(report, report.original, batch, comparison)
                for item in comparison.results:
                    source = next(s for s in batch if s.url == item.url)
                    if source.access == "manual" and item.author == Author.OWNER and sufficiently_supported(report.original, item, source):
                        report.results.append(Result(**item.model_dump(), verification="manual"))
                        report.manual_review = [r for r in report.manual_review if r.url != item.url]
                        report.limitations.append("Potrivire bazată pe material furnizat de utilizator; pagina nu a fost verificată independent.")
                for item in comparison.results:
                    source = next(s for s in batch if s.url == item.url)
                    unresolved = item.same_property != "diferită" and not item.contradictions and (
                        item.author == Author.UNKNOWN or not sufficiently_supported(report.original, item, source))
                    if unresolved and item.url not in {r.url for r in report.manual_review}:
                        report.manual_review.append(Result(**item.model_dump(), verification=source.access))
                for source in batch:
                    candidate = next(c for c in state.candidates if c.url == source.url)
                    candidate.state = "evaluated"
                # Exact, observed evidence from probable agency copies can inform a finite follow-up plan.
                for item in comparison.results:
                    if item.same_property == "probabil" and not item.contradictions:
                        for quote in item.evidence:
                            count = sum(t.category == "indiciu nou" for t in state.tasks)
                            if count >= self.settings.max_followup_queries:
                                break
                            if 5 <= len(quote.split()) <= 18:
                                query = '"' + quote.replace('"', ' ') + '"'
                                if query not in {t.query for t in state.tasks}:
                                    state.tasks.append(SearchTask(query=query, category="indiciu nou", depth=0))
                snapshot("Lot de candidați comparat")
                if report.results:
                    return

        def read_candidates(quota=None):
            count = 0
            # Snapshot the queue: links discovered here are processed on a subsequent iteration.
            for candidate in list(state.candidates):
                if candidate.state != "pending":
                    continue
                if quota is not None and count >= quota:
                    break
                remaining()
                count += 1
                if candidate.manual_text or candidate.manual_images:
                    source = Source(url=candidate.url, title=candidate.title or "Candidat introdus manual",
                                    text=candidate.manual_text or "Fotografii furnizate manual; nu există o descriere textuală.",
                                    image_matches=match_images(state.reference_images, candidate.manual_images), access="manual", accessed_at=now())
                else:
                    try:
                        if is_facebook(candidate.url):
                            raise PageError("Postare Facebook: adaugă textul sau capturile pentru verificare asistată.")
                        source = self.reader.read(candidate.url, deadline, self.settings.max_candidate_chars)
                    except PageError as exc:
                        source = Source(url=candidate.url, title=candidate.title, text=candidate.snippet,
                                        access="snippet" if candidate.snippet else "unavailable", error=str(exc), accessed_at=now())
                        candidate.error = str(exc)
                final = canonical_url(source.final_url or source.url)
                existing = next((s for s in report.sources if final == (s.final_url or s.url)), None)
                if existing and existing.url != candidate.url:
                    candidate.state = "duplicate"
                    snapshot("Copie de URL eliminată")
                    continue
                if source.images and state.reference_images:
                    signatures, errors = self.image_collector(source.images, self.settings, min(deadline, time.monotonic()+30))
                    source.image_matches = match_images(state.reference_images, signatures)
                    if errors:
                        report.limitations.append("Unele fotografii candidate nu au putut fi comparate.")
                report.sources.append(source)
                candidate.state = "read" if source.text else "unavailable"
                if candidate.link_depth < 2:
                    for link in source.links:
                        enqueue(link, origin=f"sursă indicată de {source.final_url or source.url}", link_depth=candidate.link_depth+1)
                snapshot("Pagină candidată citită")
                compare_pending()
                if report.results:
                    return

        try:
            if not report.original:
                if report.input_url:
                    report.input_url = canonical_url(report.input_url)
                if len(report.input_text) > self.settings.max_input_chars:
                    raise ValueError("Descrierea depășește limita de caractere configurată.")
                if not report.input_text and not report.input_url:
                    raise ValueError("Introdu un link sau descrierea unui anunț.")
                if not report.sources or not report.sources[0].text:
                    if report.input_text:
                        original = Source(url=report.input_url, text=report.input_text, access="manual", accessed_at=now())
                        # Manual input is independent: no HTTP access required before extraction.
                    else:
                        original = self.reader.read(report.input_url, deadline)
                    report.sources = [original]
                snapshot("Anunț citit; fotografiile sunt disponibile pentru Lens")
                extracted = invoke(self.provider.extract, report.sources[0].text)
                validate_listing(extracted, report.sources[0].text)
                report.original = extracted
                report.limitations.extend(report.original.limitations)
                snapshot("Apartament identificat")
            listing = report.original
            if listing.facts.transaction == "închiriere":
                report.message = "Anunțul este pentru închiriere; aplicația caută apartamente de vânzare."
                return report
            if listing.author == Author.OWNER:
                original = report.sources[0]
                report.results = [Result(url=original.final_url or report.input_url, title=listing.title,
                    same_property="probabil", author=Author.OWNER, author_evidence=listing.author_evidence,
                    evidence=listing.author_evidence, justification="Autorul anunțului introdus se declară proprietar.",
                    facts=listing.facts, contradictions=[], verification=original.access)]
                report.status = Status.FOUND
                report.message = "Autorul anunțului introdus se declară proprietar. Căutarea s-a oprit."
                return report
            if not state.tasks:
                state.tasks = build_plan(listing)
            if report.sources[0].images and not state.images_attempted:
                new_images, errors = self.image_collector(report.sources[0].images, self.settings,
                                                                       min(deadline, time.monotonic()+30))
                existing_hashes = {im.sha256 for im in state.reference_images}
                state.reference_images.extend(im for im in new_images if im.sha256 not in existing_hashes)
                state.images_attempted = True
                if errors:
                    report.limitations.append("Unele fotografii de referință nu au putut fi citite; Lens rămâne disponibil manual.")
                snapshot("Fotografii pregătite")
            # First finish already-fetched comparisons; never repeat successful API calls on resume.
            compare_pending(all_pending=True)
            if manual_only and not report.results:
                read_candidates()
                compare_pending(all_pending=True)
            elif not report.results:
                attempted = set()
                while True:
                    remaining()
                    task = next((t for t in state.tasks if not t.done and t.depth < self.settings.pages_per_query and (t.query, t.start) not in attempted), None)
                    if task is None:
                        break
                    attempted.add((task.query, task.start))
                    try:
                        batch = self.search.search(task.query, timeout=remaining(), start=task.start)
                        if not batch.completed:
                            raise ProviderError("Căutarea SerpApi nu s-a finalizat.")
                        for hit in batch.hits:
                            enqueue(hit.url, hit.title, hit.snippet, task.category + ": " + task.query)
                        task.done = True
                        report.queries.append(task.query)
                        report.executed_queries.extend(batch.executed_queries)
                        if batch.next_start is not None:
                            if not any(t.query == task.query and t.start == batch.next_start for t in state.tasks):
                                state.tasks.append(SearchTask(query=task.query, category=task.category,
                                                              start=batch.next_start, depth=task.depth+1))
                        snapshot("Căutare finalizată: " + task.category)
                    except ProviderError as exc:
                        task.error = str(exc)
                        snapshot("Căutare indisponibilă: " + task.category)
                        # Authentication/quota/network failures stop the round rather than spending retries on every query.
                        raise
                    # One small batch per first-page query: other source families get their turn early.
                    read_candidates(quota=self.settings.comparison_batch_size)
                    compare_pending(all_pending=True)
                    if report.results:
                        break
                while not report.results and any(c.state == "pending" for c in state.candidates):
                    read_candidates()
                    compare_pending(all_pending=True)
            if report.results:
                report.status = Status.FOUND
                report.message = "Am găsit o potrivire susținută cu un autor declarat proprietar. Căutarea s-a oprit."
            elif any(not t.done for t in state.tasks) or any(c.state in {"pending", "read"} for c in state.candidates):
                report.limited = True
                report.limit_reason = "Planul conține pași rămași sau pagini dincolo de profunzimea acestei runde."
                report.message = "Analiza are pași rămași. Poți continua fără repetarea etapelor finalizate."
            elif report.manual_review or any(c.state == "unavailable" for c in state.candidates) or any(
                e.same_property == "neclar" or (e.same_property == "probabil" and e.author == Author.UNKNOWN) for e in report.evaluations):
                report.message = "Există candidați sau surse care necesită verificare manuală."
            else:
                report.status = Status.NOT_FOUND
                report.message = "Planul de căutare s-a încheiat fără un anunț al proprietarului suficient susținut în sursele verificate."
        except Paused as exc:
            report.limited = True
            report.limit_reason = str(exc)
            report.message = str(exc)
            report.recovery_hint = "Apasă «Continuă căutarea» pentru pașii rămași."
        except (ProviderError, PageError, EvidenceError, ConfigurationError, InvalidURL, ValidationError, ValueError) as exc:
            report.message = "Răspuns invalid sau incomplet; verificarea rămâne nefinalizată." if isinstance(exc, ValidationError) else str(exc)
            report.recovery_hint = getattr(exc, "recovery_hint", "Corectează problema și continuă analiza salvată.")
        finally:
            state.elapsed_seconds += round(time.monotonic()-began, 2)
            report.limitations = list(dict.fromkeys(report.limitations))
            snapshot("Rundă încheiată")
        return report

"""Application operations, safe checkpoints, manual candidates and background jobs."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import io
from queue import Queue
from threading import Event
from uuid import uuid4

from src.analyzers.pipeline import Pipeline as Workflow
from src.analyzers.provider import GeminiProvider, ProviderError, transcribe_screenshots
from src.config import ConfigurationError, Settings
from src.extractors.images import ImageError, decode_image, signature
from src.extractors.pages import now
from src.models import Analysis, Candidate, Checkpoint, Facts, Status
from src.search.serpapi import SerpApiSearch
from src.utils.journal import save_analysis
from src.utils.urls import canonical_url


def analyze(settings: Settings, url: str, text: str, progress=lambda *_: None, *,
            report=None, checkpoint=lambda _: None, cancelled=lambda: False,
            manual_only=False, reference_pictures=()) -> tuple[Analysis, str | None]:
    provider = None
    search = SerpApiSearch(settings)
    warning = None

    def persist(current):
        nonlocal warning
        try:
            save_analysis(current, settings.journal_dir)
        except OSError:
            warning = "Rezultatul este disponibil, dar jurnalul local nu a putut fi salvat. Verifică spațiul și permisiunile directorului local_data."
        checkpoint(current)

    report = report.model_copy(deep=True) if report else Analysis(id=str(uuid4()), checked_at=now(), input_url=url.strip(), input_text=text.strip())
    try:
        provider = GeminiProvider(settings)
        if reference_pictures:
            report.checkpoint = report.checkpoint or Checkpoint()
            for index, data in enumerate(reference_pictures):
                report.checkpoint.reference_images.append(signature(data, f"fotografie-manuală-{index+1}"))
        report = Workflow(settings, provider, search).run(url, text, progress, report=report,
                    checkpoint=persist, cancelled=cancelled, manual_only=manual_only)
    except (ConfigurationError, ImageError) as exc:
        report.status = Status.INCOMPLETE
        report.message = str(exc)
    finally:
        if provider is not None:
            provider.close()
        search.close()
    persist(report)
    return report, warning


def add_candidate(report, url, text="", origin="Google Lens / introducere manuală", pictures=()):
    if not report.original:
        raise ValueError("Identifică mai întâi apartamentul de referință.")
    if report.results:
        raise ValueError("Analiza a găsit deja un proprietar declarat și s-a oprit.")
    url = canonical_url(url)
    if url in {report.input_url, report.sources[0].final_url if report.sources else None}:
        raise ValueError("Introdu linkul candidatului, diferit de anunțul de referință.")
    updated = report.model_copy(deep=True)
    updated.checkpoint = updated.checkpoint or Checkpoint()
    old = next((c for c in updated.checkpoint.candidates if c.url == url), None)
    old_source = next((s for s in updated.sources[1:] if s.url == url), None)
    if old and old.state == "evaluated" and old_source and old_source.access in {"page", "manual"} and not text.strip() and not pictures:
        raise ValueError("Acest candidat a fost deja evaluat. Adaugă text nou pentru o reevaluare.")
    candidate = Candidate(url=url, manual_text=text.strip(), discovered_by=[origin],
                          manual_images=[signature(data, f"fotografie-candidat-{i+1}") for i,data in enumerate(pictures[:6])])
    if old:
        candidate.discovered_by = list(dict.fromkeys(old.discovered_by + [origin]))
        updated.checkpoint.candidates = [c for c in updated.checkpoint.candidates if c.url != url]
        updated.sources = [s for i,s in enumerate(updated.sources) if i == 0 or s.url != url]
        updated.evaluations = [e for e in updated.evaluations if e.url != url]
        updated.manual_review = [r for r in updated.manual_review if r.url != url]
    updated.checkpoint.candidates.insert(0, candidate)
    updated.status = Status.INCOMPLETE
    updated.message = "Candidat adăugat; urmează compararea."
    return updated


def correct_facts(report, facts):
    if not report.original:
        raise ValueError("Nu există încă o fișă extrasă.")
    updated = report.model_copy(deep=True)
    facts = Facts.model_validate(facts)
    updated.checkpoint = updated.checkpoint or Checkpoint()
    updated.checkpoint.correction_history.append({"at": now(), "before": updated.original.facts.model_dump(), "after": facts.model_dump()})
    updated.original.facts = facts
    updated.results, updated.manual_review, updated.evaluations = [], [], []
    updated.checkpoint.tasks = []
    # Keep fetched pages; comparisons must be rerun because the reference has changed.
    for c in updated.checkpoint.candidates:
        if c.state == "evaluated":
            c.state = "read"
    updated.status = Status.INCOMPLETE
    updated.message = "Caracteristicile au fost corectate manual; comparațiile vor fi refăcute."
    return updated


def read_screenshots(settings, pictures):
    converted = []
    for data in pictures[:4]:
        image = decode_image(data)
        image.thumbnail((1800,1800))
        stream = io.BytesIO()
        image.save(stream, format="JPEG", quality=90)
        converted.append((stream.getvalue(), "image/jpeg"))
    provider = GeminiProvider(settings)
    try:
        result = transcribe_screenshots(provider, converted, 120)
        return result, provider.usage, provider.diagnostics
    finally:
        provider.close()


@dataclass
class Job:
    updates: Queue = field(default_factory=Queue)
    cancel: Event = field(default_factory=Event)
    future: object = None
    executor: object = None


def start_job(settings, url, text, **kwargs):
    job = Job()
    job.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="apartment-analysis")
    def publish(report):
        # Only the latest snapshot is required by the UI; journal stores every completed step.
        while not job.updates.empty():
            try:
                job.updates.get_nowait()
            except Exception:
                break
        job.updates.put(report)
    job.future = job.executor.submit(analyze, settings, url, text, checkpoint=publish,
                                     cancelled=job.cancel.is_set, **kwargs)
    job.future.add_done_callback(lambda _: job.executor.shutdown(wait=False))
    return job

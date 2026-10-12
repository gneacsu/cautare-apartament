"""Connect analysis and journaling without coupling either one to Streamlit."""

from uuid import uuid4

from src.analyzers.provider import GeminiProvider
from src.analyzers.workflow import Workflow
from src.config import ConfigurationError, Settings
from src.extractors.pages import now
from src.models import Analysis
from src.utils.journal import save_analysis


def analyze(settings: Settings, url: str, text: str, progress=lambda *_: None) -> tuple[Analysis, str | None]:
    provider = None
    try:
        provider = GeminiProvider(settings)
        report = Workflow(settings, provider).run(url, text, progress)
    except ConfigurationError as exc:
        report = Analysis(id=str(uuid4()), checked_at=now(), input_url=url.strip(), input_text=text.strip(), message=str(exc))
    finally:
        if provider is not None:
            provider.close()
    try:
        save_analysis(report, settings.journal_dir)
    except OSError:
        return report, "Rezultatul este disponibil, dar jurnalul local nu a putut fi salvat. Verifică spațiul și permisiunile directorului local_data."
    return report, None

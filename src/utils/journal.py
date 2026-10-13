"""One atomic JSON file per analysis: no shared array that can lose updates."""

import json
import os
import tempfile
from pathlib import Path

from src.models import Analysis


def save_analysis(analysis: Analysis, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{analysis.id}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(analysis.model_dump(mode="json"), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_analysis(analysis_id: str, directory: Path) -> Analysis:
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", analysis_id):
        raise ValueError("Identificator de analiză invalid.")
    path = directory / f"{analysis_id}.json"
    if path.stat().st_size > 30_000_000:
        raise ValueError("Jurnal prea mare pentru a fi încărcat.")
    return Analysis.model_validate_json(path.read_text(encoding="utf-8"))


def recent_analyses(directory: Path, limit=30):
    records = []
    for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            report = load_analysis(path.stem, directory)
            records.append((report.id, report.checked_at, report.original.title if report.original else "Analiză nefinalizată"))
        except (ValueError, OSError):
            continue
    return records


def usage_summary(directory: Path):
    """Per-analysis cumulative totals (not per checkpoint), including incomplete runs separately."""
    import statistics
    from src.models import Status
    groups = {"finalizate": [], "nefinalizate": []}
    for path in directory.glob("*.json"):
        try:
            report = load_analysis(path.stem, directory)
        except (ValueError, OSError):
            continue
        groups["nefinalizate" if report.status == Status.INCOMPLETE else "finalizate"].append(report)
    result = {}
    for name, reports in groups.items():
        tokens = [r.usage.get("total_token_count", 0) for r in reports]
        result[name] = {"analize": len(reports), "tokeni_medie": round(statistics.mean(tokens)) if tokens else 0,
                        "tokeni_mediana": round(statistics.median(tokens)) if tokens else 0,
                        "tokeni_maxim": max(tokens,default=0),
                        "cereri_serpapi_total": sum(r.usage.get("serpapi_requests",0) for r in reports)}
    return result

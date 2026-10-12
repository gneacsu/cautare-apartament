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

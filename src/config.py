"""All usage limits and local configuration live here."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    model: str = "gemini-3.6-flash"
    thinking_level: str = "medium"
    api_key: str = field(default="", repr=False)
    analysis_seconds: int = 150
    http_seconds: int = 12
    max_page_bytes: int = 2_000_000
    max_input_chars: int = 12000
    max_candidate_chars: int = 7000
    max_candidates: int = 6
    max_searches: int = 2
    max_ai_calls: int = 5
    max_output_tokens: int = 8192
    max_attempts: int = 1
    journal_dir: Path = ROOT / "local_data"

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False)
        values = {}
        bounds = {
            "analysis_seconds": (30, 300), "http_seconds": (3, 30),
            "max_input_chars": (1000, 16000), "max_candidate_chars": (1000, 8000),
            "max_candidates": (1, 8), "max_searches": (1, 2),
            "max_ai_calls": (2, 5), "max_output_tokens": (1000, 16384),
        }
        for field, (low, high) in bounds.items():
            raw = os.getenv(field.upper())
            if raw is not None:
                try:
                    value = int(raw)
                except ValueError:
                    raise ConfigurationError(f"{field.upper()} trebuie să fie un număr întreg.") from None
                if not low <= value <= high:
                    raise ConfigurationError(f"{field.upper()} trebuie să fie între {low} și {high}.")
                values[field] = value
        values["api_key"] = os.getenv("GEMINI_API_KEY", "").strip()
        values["model"] = os.getenv("GEMINI_MODEL", cls.model).strip()
        if not values["model"]:
            raise ConfigurationError("GEMINI_MODEL nu poate fi gol.")
        values["thinking_level"] = os.getenv("GEMINI_THINKING_LEVEL", cls.thinking_level).strip().lower()
        if values["thinking_level"] not in {"minimal", "low", "medium", "high"}:
            raise ConfigurationError("GEMINI_THINKING_LEVEL trebuie să fie minimal, low, medium sau high.")
        return cls(**values)

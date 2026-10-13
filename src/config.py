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
    serpapi_key: str = field(default="", repr=False)
    search_seconds: int = 60
    pages_per_query: int = 2
    max_followup_queries: int = 4
    max_images_per_listing: int = 6
    max_image_bytes: int = 8_000_000
    analysis_seconds: int = 900
    http_seconds: int = 12
    max_page_bytes: int = 2_000_000
    max_input_chars: int = 16000
    max_candidate_chars: int = 8000
    max_candidates: int = 20
    max_searches: int = 6
    max_ai_calls: int = 20
    comparison_batch_size: int = 3
    search_results_per_call: int = 8
    max_output_tokens: int = 8192
    max_attempts: int = 1
    journal_dir: Path = ROOT / "local_data"

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False)
        values = {}
        bounds = {
            "search_seconds": (10, 120), "pages_per_query": (1, 5),
            "max_followup_queries": (0, 12), "max_images_per_listing": (1, 12),
            "analysis_seconds": (30, 3600), "http_seconds": (3, 30),
            "max_input_chars": (1000, 32000), "max_candidate_chars": (1000, 16000),
            "max_output_tokens": (1000, 16384),
            "comparison_batch_size": (1, 4),
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
        values["serpapi_key"] = os.getenv("SERPAPI_API_KEY", "").strip()
        values["api_key"] = os.getenv("GEMINI_API_KEY", "").strip()
        values["model"] = os.getenv("GEMINI_MODEL", cls.model).strip()
        if not values["model"]:
            raise ConfigurationError("GEMINI_MODEL nu poate fi gol.")
        values["thinking_level"] = os.getenv("GEMINI_THINKING_LEVEL", cls.thinking_level).strip().lower()
        if values["thinking_level"] not in {"minimal", "low", "medium", "high"}:
            raise ConfigurationError("GEMINI_THINKING_LEVEL trebuie să fie minimal, low, medium sau high.")
        return cls(**values)

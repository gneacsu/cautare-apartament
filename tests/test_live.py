"""Opt-in smoke test that may incur Google API/grounding charges."""

import os

import pytest

from src.analyzers.provider import GeminiProvider
from src.config import Settings


@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="Apel real dezactivat; necesită acord explicit prin RUN_LIVE_TESTS=1.")
def test_live_google_search_sources():
    settings = Settings.load()
    if not settings.api_key:
        pytest.fail("Configurează GEMINI_API_KEY înaintea testului real.")
    provider = GeminiProvider(settings)
    try:
        batch = provider.search('apartament vânzare București "proprietar"', timeout=45)
        assert batch.completed
        assert batch.executed_queries
        assert batch.hits, "Apelul a răspuns, dar nu a furnizat surse verificabile."
    finally:
        provider.close()

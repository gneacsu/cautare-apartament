"""Opt-in, billable smoke checks, distinct from the simulated suite."""
import os
import pytest

from src.analyzers.provider import GeminiProvider
from src.config import Settings
from src.search.serpapi import SerpApiSearch

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="Apeluri reale dezactivate; necesită chei și RUN_LIVE_TESTS=1.")


def test_live_serpapi_organic_results():
    settings=Settings.load()
    if not settings.serpapi_key:
        pytest.fail("Configurează SERPAPI_API_KEY pentru testul real.")
    search=SerpApiSearch(settings)
    try:
        result=search.search('apartament vânzare București proprietar',timeout=60)
        assert result.completed and result.hits
    finally:
        search.close()


def test_live_gemini_extraction():
    settings=Settings.load()
    if not settings.api_key:
        pytest.fail("Configurează GEMINI_API_KEY pentru testul real.")
    provider=GeminiProvider(settings)
    try:
        result=provider.extract('Proprietar, vând apartament cu 2 camere în București, Titan, suprafață utilă 52 mp, etaj 3. Nu colaborez cu agenții.',timeout=120)
        assert result.facts.rooms==2
        from src.analyzers.verification import validate_listing
        validate_listing(result,'Proprietar, vând apartament cu 2 camere în București, Titan, suprafață utilă 52 mp, etaj 3. Nu colaborez cu agenții.')
    finally:
        provider.close()

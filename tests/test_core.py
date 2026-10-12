import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from src.analyzers.provider import ProviderError
from src.analyzers.verification import sufficiently_supported
from src.analyzers.workflow import Workflow
from src.config import Settings
from src.extractors.pages import PageError, extract_html, now
from src.models import APICall, Assessment, Author, Comparison, Facts, Listing, SearchBatch, SearchHit, Source, Status
from src.utils.journal import save_analysis
from src.utils.urls import InvalidURL, canonical_url

TEXT = "Apartament de vânzare cu două camere, balcon cu vedere spre teiul din curtea interioară, etaj 3."
FRAGMENT = "balcon cu vedere spre teiul din curtea interioară"
URL = "https://example.com/anunt"


def listing(author=Author.AGENCY):
    return Listing(title="Apartament două camere", description=TEXT,
                   facts=Facts(rooms=2, city="București", area="Titan", price="100000 EUR"),
                   author=author, author_evidence=["agenție"] if author == Author.AGENCY else [],
                   fragments=[FRAGMENT], limitations=[])


def assessment(author=Author.OWNER, **updates):
    data = dict(url=URL, title="Apartament Titan", same_property="probabil", author=author,
                author_evidence=["nu colaborez cu agenții"] if author == Author.OWNER else ["agenție"],
                evidence=[FRAGMENT], justification="Același fragment distinctiv și autor declarat proprietar.",
                facts=Facts(rooms=2, city="București", price="95000 EUR"), contradictions=[])
    data.update(updates)
    return Assessment(**data)


class FakeProvider:
    def __init__(self):
        self.usage = {}
        self.extract = Mock(return_value=listing())
        self.search = Mock(return_value=SearchBatch(hits=[SearchHit(url=URL, snippet=TEXT)], completed=True))
        self.compare = Mock(return_value=Comparison(status="completed", source_urls=[URL], results=[assessment()], limitations=[]))


@pytest.fixture
def setup():
    provider = FakeProvider()
    reader = Mock()
    reader.read.return_value = Source(url=URL, text=TEXT + " Proprietar, nu colaborez cu agenții.",
                                    access="page", accessed_at=now())
    return Workflow(Settings(), provider, reader), provider, reader


def run(workflow):
    return workflow.run("", TEXT + " agenție")


def test_different_prices_do_not_disqualify(setup):
    workflow, _, _ = setup
    report = run(workflow)
    assert report.status == Status.FOUND
    assert report.original.facts.price == "100000 EUR"
    assert report.results[0].facts.price == "95000 EUR"


def test_generic_text_and_different_properties(setup):
    workflow, provider, _ = setup
    provider.compare.return_value.results[0].facts.rooms = 3
    report = run(workflow)
    assert not report.results
    assert report.status == Status.NOT_FOUND
    generic = listing()
    generic.fragments = ["complet mobilat și utilat"]
    source = Source(url=URL, text="complet mobilat și utilat", access="page", accessed_at=now())
    assert not sufficiently_supported(generic, assessment(), source)


def test_owner_stops_without_search(setup):
    workflow, provider, reader = setup
    owner = listing(Author.OWNER)
    owner.author_evidence = ["nu colaborez cu agenții"]
    provider.extract.return_value = owner
    report = workflow.run(URL, TEXT + " Proprietar, nu colaborez cu agenții")
    assert report.status == Status.FOUND
    assert report.results[0].author == Author.OWNER
    assert report.results[0].verification == "manual"
    provider.search.assert_not_called()
    reader.read.assert_not_called()


def test_aggregator_copy_is_not_owner(setup):
    workflow, provider, reader = setup
    reader.read.return_value.text += " agenție"
    provider.compare.return_value.results = [assessment(Author.AGENCY)]
    assert run(workflow).status == Status.NOT_FOUND


def test_inaccessible_original_then_manual_input(setup):
    workflow, _, reader = setup
    reader.read.side_effect = PageError("Copiază descrierea manual.")
    first = workflow.run(URL, "")
    assert first.status == Status.INCOMPLETE
    reader.read.side_effect = None
    second = run(workflow)
    assert second.status == Status.FOUND
    assert first.id != second.id


def test_api_error_is_never_negative(setup):
    workflow, provider, _ = setup
    provider.search.side_effect = ProviderError("Serviciul AI nu poate fi accesat.")
    assert run(workflow).status == Status.INCOMPLETE


def test_failed_comparison_keeps_search_and_stop_reason_in_journal(setup, tmp_path):
    workflow, provider, _ = setup
    provider.diagnostics = [APICall(operation="comparare", model="gemini-2.5-flash", max_output_tokens=3000,
                                   finish_reason="MAX_TOKENS", output_tokens=3000)]
    provider.compare.side_effect = ProviderError("Limita de tokeni a fost atinsă.", "Redu MAX_CANDIDATES.")
    result = run(workflow)
    assert result.status == Status.INCOMPLETE
    assert result.queries and len(result.sources) == 2
    assert result.results == []
    assert result.recovery_hint == "Redu MAX_CANDIDATES."
    saved = json.loads(save_analysis(result, tmp_path).read_text(encoding="utf-8"))
    assert saved["diagnostics"][0]["finish_reason"] == "MAX_TOKENS"


def test_successive_analyses_do_not_share_results(setup):
    workflow, provider, _ = setup
    first = run(workflow)
    provider.search.return_value = SearchBatch(hits=[], completed=True)
    second = run(workflow)
    assert first.status == Status.FOUND
    assert second.status == Status.NOT_FOUND
    assert second.results == []
    assert len(second.sources) == 1


def test_snippet_only_is_incomplete(setup):
    workflow, provider, reader = setup
    provider.search.return_value.hits[0].snippet += " nu colaborez cu agenții"
    reader.read.side_effect = PageError("HTTP 403")
    report = run(workflow)
    assert report.status == Status.INCOMPLETE
    assert len(report.manual_review) == 1
    assert not report.results


def test_missing_or_fabricated_evidence_is_error(setup):
    workflow, provider, _ = setup
    provider.compare.return_value.results[0].author_evidence = ["citat inventat"]
    report = run(workflow)
    assert report.status == Status.INCOMPLETE
    assert not report.results


def test_unknown_and_duplicate_urls_in_comparison_are_rejected(setup):
    workflow, provider, _ = setup
    provider.compare.return_value.results[0].url = "https://example.org/inventat"
    assert run(workflow).status == Status.INCOMPLETE


def test_url_deduplication(setup):
    workflow, provider, reader = setup
    provider.search.return_value.hits.append(SearchHit(url=URL + "?utm_source=search#top"))
    report = run(workflow)
    assert len(report.results) == 1
    assert reader.read.call_count == 1


def test_call_limit_produces_incomplete(setup):
    workflow, _, _ = setup
    workflow.settings = replace(Settings(), max_ai_calls=2)
    report = run(workflow)
    assert report.status == Status.INCOMPLETE
    assert report.usage["ai_calls"] == 2


def test_no_agencies_phrase_is_not_agency_evidence(setup):
    workflow, provider, _ = setup
    provider.extract.return_value.author_evidence = ["nu colaborez cu agenții"]
    result = workflow.run("", TEXT + " nu colaborez cu agenții")
    assert result.status == Status.INCOMPLETE
    assert "nu este o dovadă" in result.message
    provider.search.assert_not_called()


def test_missing_characteristics_are_not_conflicts(setup):
    workflow, provider, _ = setup
    provider.compare.return_value.results[0].facts = Facts(price="90000 EUR")
    assert run(workflow).status == Status.FOUND


def test_rental_is_outside_sale_workflow(setup):
    workflow, provider, _ = setup
    provider.extract.return_value.facts.transaction = "închiriere"
    report = run(workflow)
    assert report.status == Status.INCOMPLETE
    assert "închiriere" in report.message
    provider.search.assert_not_called()


def test_search_failure_not_treated_as_empty_success(setup):
    workflow, provider, _ = setup
    provider.search.return_value.completed = False
    assert run(workflow).status == Status.INCOMPLETE


def test_incomplete_ai_comparison_not_negative(setup):
    workflow, provider, _ = setup
    provider.compare.return_value.status = "incomplete"
    assert run(workflow).status == Status.INCOMPLETE


def test_journal_is_json_and_retains_per_source_price(setup, tmp_path):
    report = run(setup[0])
    path = save_analysis(report, tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["original"]["facts"]["price"] == "100000 EUR"
    assert saved["results"][0]["facts"]["price"] == "95000 EUR"
    assert "api_key" not in saved
    assert len(list(tmp_path.iterdir())) == 1


def test_html_cleanup():
    html = '<html><title>Anunț</title><nav>MENIU</nav><main><p>' + TEXT + '</p><div class="related">ALT ANUNȚ</div></main><footer>CONTACT SITE</footer></html>'
    title, text = extract_html(html, 12000)
    assert title == "Anunț" and TEXT in text
    assert "MENIU" not in text and "ALT ANUNȚ" not in text and "CONTACT SITE" not in text


def test_block_page_is_not_listing():
    with pytest.raises(PageError):
        extract_html('<html><body>Verify you are human. captcha</body></html>', 12000)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/a", "http://localhost/a", "https://user:pass@example.com/"])
def test_invalid_urls(url):
    with pytest.raises(InvalidURL):
        canonical_url(url)

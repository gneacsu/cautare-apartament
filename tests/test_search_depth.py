from dataclasses import replace
from unittest.mock import Mock

from src.analyzers.workflow import Workflow
from src.config import Settings
from src.extractors.pages import now
from src.models import Author, Comparison, SearchBatch, SearchHit, Source, Status
from src.search.queries import build_queries
from tests.test_core import FRAGMENT, TEXT, FakeProvider, assessment, listing


def deeper_workflow(settings=None, owner_index=None, count=12):
    provider = FakeProvider()
    provider.search.return_value = SearchBatch(completed=True, hits=[
        SearchHit(url=f"https://example.com/candidat/{index}", snippet=TEXT) for index in range(count)])
    reader = Mock()
    reader.read.side_effect = lambda url, *args: Source(
        url=url, text=TEXT + " agenție; Proprietar, nu colaborez cu agenții.", access="page", accessed_at=now())

    def compare(original, sources, timeout):
        results = [assessment(Author.OWNER if int(source.url.rsplit('/', 1)[1]) == owner_index else Author.AGENCY,
                              url=source.url) for source in sources]
        return Comparison(status="completed", source_urls=[source.url for source in sources], results=results, limitations=[])

    provider.compare.side_effect = compare
    return Workflow(settings or Settings(), provider, reader), provider, reader


def test_owner_beyond_first_six_is_found_in_small_batches():
    workflow, provider, reader = deeper_workflow(owner_index=7)
    report = workflow.run("", TEXT + " agenție")
    assert report.status == Status.FOUND
    assert [result.url for result in report.results] == ["https://example.com/candidat/7"]
    assert [len(call.args[1]) for call in provider.compare.call_args_list] == [3, 3, 3]
    assert reader.read.call_count == 9  # Stops before reading the next batch.
    assert provider.search.call_count == 1
    assert report.coverage["sources_compared"] == 9


def test_candidate_cap_is_not_a_false_negative_when_owner_is_later():
    workflow, provider, reader = deeper_workflow(replace(Settings(), max_candidates=6), owner_index=7)
    report = workflow.run("", TEXT + " agenție")
    assert report.status == Status.INCOMPLETE
    assert report.limited and "6 pagini" in report.limit_reason
    assert not report.results
    assert reader.read.call_count == 6
    assert report.coverage["sources_compared"] == 6
    assert "pot exista surse relevante neverificate" in report.message


def test_search_cap_reports_untried_variants():
    workflow, provider, _ = deeper_workflow(replace(Settings(), max_searches=1), count=0)
    report = workflow.run("", TEXT + " agenție")
    assert report.status == Status.INCOMPLETE
    assert report.limited
    assert report.coverage["completed_searches"] == 1
    assert report.coverage["planned_searches"] == 6
    assert provider.compare.call_count == 0


def test_all_planned_variants_complete_before_negative_conclusion():
    workflow, provider, reader = deeper_workflow(count=1)
    report = workflow.run("", TEXT + " agenție")
    assert report.status == Status.NOT_FOUND
    assert not report.limited
    assert provider.search.call_count == 6
    assert reader.read.call_count == 1  # Duplicate URLs are not reread/recompared.
    assert report.coverage["completed_searches"] == 6


def test_owner_found_in_later_search_variant():
    workflow, provider, _ = deeper_workflow(owner_index=7)
    provider.search.side_effect = [SearchBatch(completed=True, hits=[]), SearchBatch(completed=True, hits=[]),
                                   SearchBatch(completed=True, hits=[SearchHit(url="https://example.com/candidat/7")])]
    report = workflow.run("", TEXT + " agenție")
    assert report.status == Status.FOUND
    assert provider.search.call_count == 3
    assert report.coverage["completed_searches"] == 3


def test_call_budget_is_shared_across_all_batches():
    workflow, provider, _ = deeper_workflow(replace(Settings(), max_ai_calls=5))
    report = workflow.run("", TEXT + " agenție")
    assert report.status == Status.INCOMPLETE and report.limited
    assert report.usage["ai_calls"] == 5
    assert provider.compare.call_count == 3
    assert "5 apeluri" in report.limit_reason


def test_queries_cover_exact_relaxed_unaccented_features_and_facebook():
    original = listing()
    original.fragments = [FRAGMENT, "la două minute de parcul cu castani", "vedere spre curtea interioară a clădirii"]
    queries = build_queries(original)
    assert len(queries) == 6 and len(set(queries)) == 6
    assert FRAGMENT in queries[0] and '"' in queries[0]
    assert original.fragments[2] in queries[1]
    assert "balcon cu vedere spre teiul din curtea interioara" in queries[2]
    assert "Titan" in queries[4]
    assert queries[-1].startswith("site:facebook.com")
    assert not any("100000" in query for query in queries)


def test_missing_fragments_are_not_invented():
    original = listing()
    original.fragments = []
    queries = build_queries(original)
    assert not any('"' in query for query in queries)
    assert any("proprietar" in query for query in queries)

from dataclasses import replace
from unittest.mock import Mock
import json

import pytest

from src.analyzers.pipeline import Pipeline
from src.analyzers.provider import ProviderError
from src.config import Settings
from src.models import SearchBatch, SearchHit, Source, Status, Author, Comparison, SearchCall
from src.extractors.pages import now, PageError
from src.service import add_candidate, correct_facts
from src.utils.journal import load_analysis, save_analysis
from tests.test_core import TEXT, FRAGMENT, listing, assessment, URL, FakeProvider


def setup_pipeline(owner=False, settings=None):
    provider = FakeProvider()
    provider.diagnostics = []
    search = Mock()
    search.calls = []
    search.search.return_value = SearchBatch(completed=True, hits=[])
    reader = Mock()
    reader.read.side_effect = lambda url,*args: Source(url=url, text=TEXT+' agenție; proprietar, nu colaborez cu agenții', access='page', accessed_at=now())
    def compare(original, sources, timeout):
        return Comparison(status='completed', source_urls=[s.url for s in sources], results=[
            assessment(Author.OWNER if owner else Author.AGENCY, url=s.url) for s in sources], limitations=[])
    provider.compare.side_effect = compare
    return Pipeline(settings or Settings(), provider, search, reader, image_collector=Mock(return_value=([],[]))), provider, search, reader


def run(pipeline, **kwargs):
    return pipeline.run('', TEXT+' agenție', **kwargs)


def test_serpapi_search_not_gemini_and_facebook_early():
    p, ai, search, reader = setup_pipeline()
    report=run(p)
    assert report.status == Status.NOT_FOUND
    assert search.search.call_count >= 8
    assert search.search.call_args_list[1].args[0].startswith('site:facebook.com')
    ai.search.assert_not_called()
    assert report.usage['ai_calls']==1


def test_declared_owner_needs_no_serpapi_key_or_search():
    p, ai, search, _=setup_pipeline()
    original=listing(Author.OWNER); original.author_evidence=['nu colaborez cu agenții']
    ai.extract.return_value=original
    report=p.run('',TEXT+' nu colaborez cu agenții')
    assert report.status==Status.FOUND
    search.search.assert_not_called()


def test_more_than_20_candidates_no_legacy_cap():
    p, ai, search, _=setup_pipeline(settings=replace(Settings(),max_candidates=1,max_ai_calls=2,max_searches=1))
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=f'https://example.com/{i}') for i in range(25)])
    report=run(p)
    assert len(report.evaluations)==25
    assert report.status==Status.NOT_FOUND
    assert report.usage['ai_calls']>2


def test_owner_stops_early_and_prices_remain_distinct():
    p, ai, search, _=setup_pipeline(owner=True)
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=URL)])
    report=run(p)
    assert report.status==Status.FOUND
    assert search.search.call_count==1
    assert report.original.facts.price != report.results[0].facts.price


def test_resume_does_not_repeat_extraction_search_or_reads(tmp_path):
    p,ai,search,reader=setup_pipeline()
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=URL)])
    ai.compare.side_effect=ProviderError('Gemini indisponibil')
    first=run(p)
    assert first.status==Status.INCOMPLETE
    assert first.checkpoint.candidates[0].state=='read'
    save_analysis(first,tmp_path)
    resumed=load_analysis(first.id,tmp_path)
    p2,ai2,search2,reader2=setup_pipeline(owner=True)
    result=p2.run(report=resumed)
    assert result.status==Status.FOUND
    ai2.extract.assert_not_called();search2.search.assert_not_called();reader2.read.assert_not_called()
    assert result.id==first.id and result.checkpoint.rounds==2


def test_cancel_after_page_read_keeps_candidate_and_resumes():
    p,ai,search,reader=setup_pipeline()
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=URL)])
    stop=[False]
    def checkpoint(report):
        if report.checkpoint.stage=='Pagină candidată citită': stop[0]=True
    result=run(p, checkpoint=checkpoint,cancelled=lambda:stop[0])
    assert result.limited and result.status==Status.INCOMPLETE
    assert result.checkpoint.candidates[0].state=='read'


def test_first_pages_precede_pagination_and_more_pages_are_pending():
    p,ai,search,reader=setup_pipeline(settings=replace(Settings(),pages_per_query=1))
    search.search.side_effect=lambda q,timeout,start:SearchBatch(completed=True,hits=[],next_start=10)
    report=run(p)
    assert all(call.kwargs['start']==0 for call in search.search.call_args_list)
    assert report.status==Status.INCOMPLETE and report.limited
    assert any(t.start==10 and not t.done for t in report.checkpoint.tasks)
    p2,_,search2,_=setup_pipeline(settings=replace(Settings(),pages_per_query=2))
    result=p2.run(report=report)
    assert all(c.kwargs['start']==10 for c in search2.search.call_args_list)
    assert result.status==Status.NOT_FOUND


def test_search_failure_has_no_false_negative_and_no_repeated_retry():
    p,ai,search,_=setup_pipeline()
    search.search.side_effect=ProviderError('Cota SerpApi')
    report=run(p)
    assert report.status==Status.INCOMPLETE
    assert search.search.call_count==1
    assert not report.checkpoint.tasks[0].done


def test_redirect_duplicates_compared_once():
    p,ai,search,reader=setup_pipeline()
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=URL),SearchHit(url=URL+'-other')])
    reader.read.side_effect=lambda url,*args:Source(url=url,final_url=URL,text=TEXT+' agenție',access='page',accessed_at=now())
    report=run(p)
    assert len(report.evaluations)==1
    assert report.checkpoint.candidates[1].state=='duplicate'


def test_facebook_is_assisted_and_manual_candidate_can_resolve():
    p,ai,search,reader=setup_pipeline(owner=True)
    fb='https://www.facebook.com/groups/group/posts/123'
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=fb,snippet=TEXT+' nu colaborez cu agenții')])
    report=run(p)
    assert report.status==Status.INCOMPLETE and not report.results
    reader.read.assert_not_called()
    updated=add_candidate(report,fb,TEXT+' Proprietar, nu colaborez cu agenții')
    assert not updated.evaluations
    result=p.run(report=updated,manual_only=True)
    assert result.status==Status.FOUND and result.results[0].verification=='manual'
    assert not result.manual_review


def test_manual_candidate_after_negative_uses_no_search():
    p,ai,search,reader=setup_pipeline(owner=True)
    report=run(p)
    updated=add_candidate(report,URL,TEXT+' nu colaborez cu agenții')
    search.search.reset_mock()
    result=p.run(report=updated,manual_only=True)
    search.search.assert_not_called()
    assert result.status==Status.FOUND


def test_corrections_invalidate_comparisons_keep_pages():
    p,ai,search,reader=setup_pipeline()
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=URL)])
    report=run(p)
    newfacts=report.original.facts.model_dump();newfacts['rooms']=3
    updated=correct_facts(report,newfacts)
    assert updated.checkpoint.correction_history
    assert updated.checkpoint.candidates[0].state=='read'
    assert not updated.evaluations and updated.sources==report.sources
    assert report.original.facts.rooms==2


def test_invalid_extraction_not_saved_as_valid_on_retry():
    p,ai,search,_=setup_pipeline()
    ai.extract.return_value.author_evidence=['inventat']
    report=run(p)
    assert report.original is None and report.status==Status.INCOMPLETE
    search.search.assert_not_called()


def test_new_analysis_does_not_share_queue():
    p,ai,search,_=setup_pipeline(owner=True)
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=URL)])
    first=run(p)
    search.search.return_value=SearchBatch(completed=True,hits=[])
    second=run(p)
    assert first.id!=second.id and not second.results and not second.checkpoint.candidates


def test_manual_original_does_not_require_http():
    p,ai,search,reader=setup_pipeline()
    reader.read.side_effect=PageError('Blocked')
    report=p.run(URL,TEXT+' agenție')
    reader.read.assert_not_called()
    assert report.original


def test_logs_support_partial_and_not_path_traversal(tmp_path):
    p,*_=setup_pipeline()
    result=run(p)
    save_analysis(result,tmp_path)
    assert load_analysis(result.id,tmp_path)==result
    with pytest.raises(ValueError):load_analysis('../config',tmp_path)


def test_probable_but_unsupported_owner_is_manual_review_not_negative():
    p,ai,search,reader=setup_pipeline(owner=True)
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=URL)])
    reader.read.side_effect=lambda url,*args:Source(url=url,text='Apartament mobilat. Proprietar, nu colaborez cu agenții.',access='page',accessed_at=now())
    ai.compare.side_effect=lambda original,sources,timeout:Comparison(status='completed',source_urls=[s.url for s in sources],results=[assessment(url=s.url,evidence=['Apartament mobilat']) for s in sources],limitations=[])
    report=run(p)
    assert report.status==Status.INCOMPLETE
    assert report.manual_review and not report.results


def test_followup_queries_have_observed_quotes_only_and_remain_finite():
    p,ai,search,reader=setup_pipeline()
    quote='la doi pași de parcul cu fântâna arteziană'
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=URL)])
    reader.read.side_effect=lambda url,*args:Source(url=url,text=TEXT+' agenție '+quote,access='page',accessed_at=now())
    ai.compare.side_effect=lambda original,sources,timeout:Comparison(status='completed',source_urls=[s.url for s in sources],results=[assessment(Author.AGENCY,url=s.url,evidence=[FRAGMENT,quote]) for s in sources],limitations=[])
    report=run(p)
    assert any(t.query=='"'+quote+'"' and t.done for t in report.checkpoint.tasks)
    assert sum(t.category=='indiciu nou' for t in report.checkpoint.tasks)<=4


def test_failed_page_can_be_retried_without_new_text():
    p,ai,search,reader=setup_pipeline(owner=True)
    search.search.return_value=SearchBatch(completed=True,hits=[SearchHit(url=URL,snippet=TEXT+' nu colaborez cu agenții')])
    reader.read.side_effect=PageError('Blocked')
    report=run(p)
    updated=add_candidate(report,URL)
    assert updated.checkpoint.candidates[0].state=='pending'
    p2,_,search2,_=setup_pipeline(owner=True)
    result=p2.run(report=updated,manual_only=True)
    assert result.status==Status.FOUND
    search2.search.assert_not_called()

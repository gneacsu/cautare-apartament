from concurrent.futures import Future
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.config import ROOT
from src.models import Analysis, Checkpoint, SearchTask, Source, Status
from src.service import Job
from tests.test_core import listing, TEXT, URL


def example():
    return Analysis(id='ui-example', checked_at='2026-10-13', input_url=URL, input_text=TEXT,
                    original=listing(), sources=[Source(url=URL,text=TEXT,access='page',accessed_at='today',images=['https://example.com/photo.jpg'])],
                    checkpoint=Checkpoint(tasks=[SearchTask(query='query',category='test')]),
                    message='Progres salvat')


def button(app,label):
    return next(b for b in app.button if b.label==label)


def test_photo_visible_and_lens_link_while_search_running():
    job=Job();job.future=Future()
    job.updates.put(example())
    with patch('src.service.start_job',return_value=job):
        app=AppTest.from_file(ROOT/'app.py').run()
        app.text_area[0].set_value(TEXT).run()
        button(app,'Caută proprietarul').click().run()
        assert not app.exception
        assert any(b.label=='Deschide Google Lens' for b in app.get('link_button'))
        assert button(app,'Caută proprietarul').disabled
        button(app,'Oprește și păstrează progresul').click().run()
        assert job.cancel.is_set()
        job.future.set_result((example(),None))
        app.run()
        assert not app.exception
        assert any(b.label=='Continuă căutarea' for b in app.button)


def test_resume_submits_saved_report_not_new_input():
    saved=example()
    job=Job();job.future=Future()
    app=AppTest.from_file(ROOT/'app.py')
    app.session_state['report']=saved
    with patch('src.service.start_job',return_value=job) as start:
        app.run()
        button(app,'Continuă căutarea').click().run()
        assert not app.exception
        assert start.call_args.kwargs['report'].id==saved.id
        assert start.call_args.args[1]==saved.input_url


def test_reset_running_job_discards_late_results():
    job=Job();job.future=Future();job.updates.put(example())
    with patch('src.service.start_job',return_value=job):
        app=AppTest.from_file(ROOT/'app.py').run()
        app.text_area[0].set_value(TEXT).run()
        button(app,'Caută proprietarul').click().run()
        button(app,'Verificare nouă').click().run()
        assert job.cancel.is_set()
        job.future.set_result((example(),None))
        app.run()
        assert not app.exception
        assert app.text_area[0].value==''
        assert app.session_state.get('report') is None


def test_manual_candidate_starts_comparison_without_search_and_reuses_id():
    app=AppTest.from_file(ROOT/'app.py')
    app.session_state['report']=example()
    job=Job();job.future=Future()
    with patch('src.service.start_job',return_value=job) as start,patch('src.utils.journal.save_analysis'):
        app.run()
        next(t for t in app.text_input if t.label=='Linkul candidatului').set_value('https://example.com/new').run()
        next(t for t in app.text_area if t.label=='Textul candidatului / transcriere verificată').set_value('Proprietar '+TEXT).run()
        button(app,'Compară acest candidat').click().run()
        assert not app.exception
        assert start.call_args.kwargs['manual_only'] is True
        assert start.call_args.kwargs['report'].id=='ui-example'

from dataclasses import replace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.config import ROOT, Settings
from src.models import APICall, Analysis, Source, Status
from src.service import analyze


def report(status, message):
    return Analysis(id="test", checked_at="2026-10-12T00:00:00Z", input_url="", input_text="test",
                    status=status, message=message)


def test_ui_success_then_error_and_reset():
    outputs = [(report(Status.FOUND, "Primul rezultat"), None),
               (report(Status.INCOMPLETE, "Eroare Gemini"), None)]
    with patch("src.service.analyze", side_effect=outputs) as service:
        app = AppTest.from_file(ROOT / "app.py").run()
        app.text_area[0].set_value("Prima descriere").run()
        app.button[0].click().run()
        assert not app.exception
        assert app.success[0].value == Status.FOUND
        app.text_area[0].set_value("A doua descriere").run()
        assert not app.success
        app.button[0].click().run()
        assert not app.exception and not app.success
        assert app.warning[0].value == Status.INCOMPLETE
        assert service.call_count == 2
        app.button[1].click().run()
        assert app.text_area[0].value == ""
        assert app.text_input[0].value == ""
        assert not app.warning


def test_missing_key_still_journals_failure(tmp_path):
    settings = replace(Settings(), journal_dir=tmp_path)
    result, warning = analyze(settings, "", "Descriere manuală")
    assert result.status == Status.INCOMPLETE
    assert "GEMINI_API_KEY" in result.message
    assert warning is None
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_api_failure_offers_diagnostic_instead_of_manual_input_advice():
    failed = report(Status.INCOMPLETE, "Limita de tokeni a fost atinsă.")
    failed.recovery_hint = "Redu MAX_CANDIDATES."
    failed.diagnostics = [APICall(operation="comparare", model="gemini-2.5-flash", max_output_tokens=3000,
                                  finish_reason="MAX_TOKENS")]
    failed.sources = [Source(url="", text="Input manual", access="manual", accessed_at="2026-10-12"),
                      Source(url="https://example.com/candidat", title="Sursă necomparată", text="Anunț candidat",
                             access="page", accessed_at="2026-10-12")]
    with patch("src.service.analyze", return_value=(failed, None)):
        app = AppTest.from_file(ROOT / "app.py").run()
        app.text_area[0].set_value("Descriere de test").run()
        app.button[0].click().run()
        assert not app.exception
        assert any(caption.value == "Redu MAX_CANDIDATES." for caption in app.caption)
        assert not any("Poți copia descrierea" in caption.value for caption in app.caption)
        assert len(app.get("download_button")) == 1
        assert "MAX_TOKENS" in app.json[0].value
        assert len(app.get("link_button")) == 1
        assert not app.success


def test_journal_error_preserves_result(tmp_path):
    with patch("src.service.GeminiProvider") as provider, patch("src.service.Workflow") as workflow:
        workflow.return_value.run.return_value = report(Status.FOUND, "Rezultat valid")
        with patch("src.service.save_analysis", side_effect=OSError("disk full")):
            result, warning = analyze(replace(Settings(), journal_dir=tmp_path), "", "Descriere")
    assert result.status == Status.FOUND
    assert warning and "jurnalul" in warning
    provider.return_value.close.assert_called_once()

import os
from unittest.mock import patch

import pytest

from src.config import ConfigurationError, Settings


def test_key_only_env_uses_requested_model_and_thinking(tmp_path):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-only-not-a-real-key\n", encoding="utf-8")
    with patch.dict(os.environ, {}, clear=True), patch("src.config.ROOT", tmp_path):
        settings = Settings.load()
    assert settings.api_key == "test-only-not-a-real-key"
    assert settings.model == "gemini-3.6-flash"
    assert settings.thinking_level == "medium"


def test_process_configuration_takes_precedence_over_env_file(tmp_path):
    (tmp_path / ".env").write_text("GEMINI_MODEL=gemini-3.6-flash\nGEMINI_THINKING_LEVEL=medium\n", encoding="utf-8")
    with patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": " LOW "}, clear=True), patch("src.config.ROOT", tmp_path):
        settings = Settings.load()
    assert settings.thinking_level == "low"


@pytest.mark.parametrize("value", ["", "medum", "disabled", "0"])
def test_invalid_thinking_level_is_rejected_before_api_call(value):
    with patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": value}, clear=True), patch("src.config.load_dotenv"):
        with pytest.raises(ConfigurationError, match="GEMINI_THINKING_LEVEL"):
            Settings.load()

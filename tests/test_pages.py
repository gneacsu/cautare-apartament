from dataclasses import replace
from unittest.mock import Mock, patch
import time

import pytest
import requests

from src.config import Settings
from src.extractors.pages import PageError, PageReader
from src.utils.urls import InvalidURL
from tests.test_core import TEXT, URL


def http_response(body, code=200, redirect=None):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.status_code = code
    response.is_redirect = redirect is not None
    response.is_permanent_redirect = False
    response.headers = {"Content-Type": "text/html; charset=utf-8"}
    if redirect:
        response.headers["Location"] = redirect
    response.iter_content.return_value = [body.encode("utf-8")]
    return response


def test_page_is_read_and_redirect_provenance_retained():
    target = "https://example.com/destinatie"
    with patch("src.extractors.pages.public_url", side_effect=lambda url: url), patch("src.extractors.pages.requests.get") as get:
        get.side_effect = [http_response("", redirect=target), http_response("<html><main>" + TEXT + "</main></html>")]
        source = PageReader(Settings()).read(URL, time.monotonic() + 10)
        assert source.url == URL
        assert source.final_url == target
        assert source.text == TEXT
        assert source.access == "page"


def test_redirect_to_private_address_is_not_requested():
    with patch("src.extractors.pages.public_url", side_effect=[URL, InvalidURL("Adresă privată")]), patch("src.extractors.pages.requests.get") as get:
        get.return_value = http_response("", redirect="http://127.0.0.1/")
        with pytest.raises(PageError):
            PageReader(Settings()).read(URL, time.monotonic() + 10)
        assert get.call_count == 1


@pytest.mark.parametrize("code", [401, 403, 404, 429, 500])
def test_http_failures_request_manual_text(code):
    with patch("src.extractors.pages.public_url", return_value=URL), patch("src.extractors.pages.requests.get", return_value=http_response("", code)):
        with pytest.raises(PageError, match=str(code)):
            PageReader(Settings()).read(URL, time.monotonic() + 10)


def test_download_size_is_limited():
    settings = replace(Settings(), max_page_bytes=20)
    with patch("src.extractors.pages.public_url", return_value=URL), patch("src.extractors.pages.requests.get", return_value=http_response(TEXT)):
        with pytest.raises(PageError, match="limita de descărcare"):
            PageReader(settings).read(URL, time.monotonic() + 10)


def test_network_timeout_becomes_actionable_message():
    with patch("src.extractors.pages.public_url", return_value=URL), patch("src.extractors.pages.requests.get", side_effect=requests.Timeout()):
        with pytest.raises(PageError, match="Copiază descrierea"):
            PageReader(Settings()).read(URL, time.monotonic() + 10)

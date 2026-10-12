import json
from unittest.mock import Mock

import httpx
import pytest
from google import genai
from google.genai import types

from src.analyzers.provider import GeminiProvider, ProviderError
from src.config import ConfigurationError, Settings
from src.models import Author
from tests.test_core import TEXT, URL, listing


def response(text="Răspuns", metadata=None, finish=types.FinishReason.STOP):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=[types.Part(text=text)]),
                                    finish_reason=finish, grounding_metadata=metadata)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=100, candidates_token_count=30,
                                                                 total_token_count=130))


def provider_with(output):
    client = Mock()
    client.models.generate_content.return_value = output
    return GeminiProvider(Settings(), client=client), client


def test_missing_key_is_explicit():
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        GeminiProvider(Settings())


def test_structured_response_uses_schema_and_separate_call():
    provider, client = provider_with(response(listing().model_dump_json()))
    result = provider.extract(TEXT, 10)
    assert result.author == Author.AGENCY
    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema["properties"]["facts"]
    assert config.tools is None
    assert config.http_options.timeout == 10000
    assert config.http_options.retry_options.attempts == 1
    assert config.max_output_tokens == Settings().max_output_tokens


def test_urls_only_from_grounding_metadata():
    metadata = types.GroundingMetadata(
        web_search_queries=["apartament titan"],
        grounding_chunks=[types.GroundingChunk(web=types.GroundingChunkWeb(uri=URL, title="Anunț"))],
        grounding_supports=[types.GroundingSupport(grounding_chunk_indices=[0], segment=types.Segment(text="Apartament Titan"))],
        search_entry_point=types.SearchEntryPoint(rendered_content="<div>Google</div>"))
    provider, client = provider_with(response("https://example.com/link-inventat", metadata))
    result = provider.search("apartament", 10)
    assert [hit.url for hit in result.hits] == [URL]
    assert result.hits[0].snippet == "Apartament Titan"
    assert result.search_suggestions_html == "<div>Google</div>"
    config = client.models.generate_content.call_args.kwargs["config"]
    assert config.tools[0].google_search is not None
    assert config.response_mime_type is None


def test_no_search_metadata_is_error_not_empty_results():
    provider, _ = provider_with(response("Nu există rezultate."))
    with pytest.raises(ProviderError, match="dovada"):
        provider.search("apartament", 10)


def test_unusable_grounded_urls_are_not_empty_success():
    metadata = types.GroundingMetadata(web_search_queries=["apartament"], grounding_chunks=[
        types.GroundingChunk(web=types.GroundingChunkWeb(uri="javascript:alert(1)", title="Invalid"))])
    provider, _ = provider_with(response("Un rezultat", metadata))
    with pytest.raises(ProviderError, match="URL-uri"):
        provider.search("apartament", 10)


@pytest.mark.parametrize("payload", ["{}", "not json", '{"title": "trunchiat"'])
def test_invalid_response_is_error(payload):
    provider, _ = provider_with(response(payload))
    with pytest.raises(ProviderError):
        provider.extract(TEXT, 10)


def test_truncated_response_is_error():
    provider, _ = provider_with(response(listing().model_dump_json(), finish=types.FinishReason.MAX_TOKENS))
    with pytest.raises(ProviderError, match="incomplet"):
        provider.extract(TEXT, 10)


def test_network_error_is_sanitized():
    provider, client = provider_with(None)
    client.models.generate_content.side_effect = httpx.ConnectError("sensitive request details")
    with pytest.raises(ProviderError) as error:
        provider.extract(TEXT, 10)
    assert "sensitive" not in str(error.value)


def test_sdk_serialization_with_mock_http():
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": listing().model_dump_json()}], "role": "model"},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20, "totalTokenCount": 30}})

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        with genai.Client(api_key="test-only-not-a-real-key", http_options=types.HttpOptions(httpx_client=transport)) as client:
            provider = GeminiProvider(Settings(), client=client)
            provider.extract(TEXT, 5)
    assert captured[0]["generationConfig"]["responseMimeType"] == "application/json"
    assert captured[0]["generationConfig"]["responseJsonSchema"]["properties"]["title"]
    assert provider.usage["total_token_count"] == 30

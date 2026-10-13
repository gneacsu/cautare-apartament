import json
from dataclasses import replace
from unittest.mock import Mock

import httpx
import pytest
from google import genai
from google.genai import types

from src.analyzers.provider import GeminiProvider, ProviderError
from src.config import ConfigurationError, Settings
from src.models import Author, Source
from tests.test_core import TEXT, URL, assessment, listing


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
    assert client.models.generate_content.call_args.kwargs["model"] == "gemini-3.6-flash"
    assert config.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM
    assert config.thinking_config.thinking_budget is None


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
    assert config.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM


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
    assert provider.diagnostics[-1].finish_reason == "MAX_TOKENS"
    assert provider.diagnostics[-1].operation == "extragere"
    assert provider.diagnostics[-1].outcome == "error"


def test_user_reported_thinking_exhaustion_has_correct_recovery_and_no_retry():
    output = response('{"status":', finish=types.FinishReason.MAX_TOKENS)
    output.usage_metadata = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=2923, candidates_token_count=105, thoughts_token_count=2876)
    provider, client = provider_with(output)
    provider.settings = replace(provider.settings, max_output_tokens=3000)
    source = Source(url=URL, text=TEXT, access="page", accessed_at="2026-10-13")
    with pytest.raises(ProviderError) as error:
        provider.compare(listing(), [source], 10)
    assert "2876" in str(error.value) and "105" in str(error.value)
    assert "MAX_OUTPUT_TOKENS=8192" in error.value.recovery_hint
    assert "MAX_CANDIDATES" not in error.value.recovery_hint
    assert client.models.generate_content.call_count == 1
    assert provider.diagnostics[-1].operation == "comparare"
    assert provider.diagnostics[-1].finish_reason == "MAX_TOKENS"
    assert provider.diagnostics[-1].thinking_tokens == 2876
    assert provider.diagnostics[-1].output_tokens == 105


@pytest.mark.parametrize("reason", [types.FinishReason.SAFETY, types.FinishReason.RECITATION,
                                     types.FinishReason.OTHER, types.FinishReason.MALFORMED_FUNCTION_CALL])
def test_stop_reasons_are_distinguished_without_accepting_partial_results(reason):
    provider, _ = provider_with(response(listing().model_dump_json(), finish=reason))
    with pytest.raises(ProviderError) as error:
        provider.extract(TEXT, 10)
    assert reason.value in str(error.value)
    assert provider.diagnostics[-1].finish_reason == reason.value
    assert provider.diagnostics[-1].outcome == "error"


def test_prompt_block_without_candidate_is_reported():
    output = types.GenerateContentResponse.model_validate({"promptFeedback": {"blockReason": "SAFETY"}})
    provider, _ = provider_with(output)
    with pytest.raises(ProviderError, match="SAFETY"):
        provider.extract(TEXT, 10)
    assert provider.diagnostics[-1].block_reason == "SAFETY"


def test_unspecified_prompt_feedback_does_not_block_complete_response():
    output = response(listing().model_dump_json())
    output.prompt_feedback = types.GenerateContentResponsePromptFeedback(block_reason=types.BlockedReason.BLOCKED_REASON_UNSPECIFIED)
    provider, _ = provider_with(output)
    assert provider.extract(TEXT, 10).title == listing().title
    assert provider.diagnostics[-1].block_reason is None


def compact_comparison(count=1):
    return {
        "status": "completed", "source_ids": [f"s{i}" for i in range(count)],
        "results": [{**assessment().model_dump(mode="json", exclude={"url"}), "source_id": f"s{i}"}
                    for i in range(count)],
        "limitations": [],
    }


def test_long_grounding_urls_are_not_echoed_in_ai_payload():
    sources = [Source(url=f"https://vertexaisearch.cloud.google.com/grounding-api-redirect/{i}/" + "x" * 3000,
                      text=TEXT, access="page", accessed_at="2026-10-12") for i in range(6)]
    provider, client = provider_with(response(json.dumps(compact_comparison(6))))
    comparison = provider.compare(listing(), sources, 20)
    assert comparison.source_urls == [source.url for source in sources]
    assert [item.url for item in comparison.results] == comparison.source_urls
    sent = client.models.generate_content.call_args.kwargs["contents"]
    assert "x" * 3000 not in sent
    assert '"source_id": "s5"' in sent
    assert client.models.generate_content.call_count == 1
    assert provider.diagnostics[-1].operation == "comparare"


@pytest.mark.parametrize("variant", ["unknown", "duplicate", "missing", "unknown_source_list"])
def test_compact_response_must_cover_exact_known_source_ids(variant):
    payload = compact_comparison(2)
    if variant == "unknown":
        payload["results"][0]["source_id"] = "s99"
    elif variant == "duplicate":
        payload["results"][1]["source_id"] = "s0"
    elif variant == "missing":
        payload["results"].pop()
    else:
        payload["source_ids"][1] = "s99"
    provider, _ = provider_with(response(json.dumps(payload)))
    sources = [Source(url=f"https://example.com/{i}", text=TEXT, access="page", accessed_at="2026-10-12")
               for i in range(2)]
    with pytest.raises(ProviderError, match="identificatori"):
        provider.compare(listing(), sources, 10)


def test_diagnostics_exclude_key_and_listing_text():
    provider, _ = provider_with(response(listing().model_dump_json()))
    provider.extract(TEXT, 10)
    serialized = provider.diagnostics[-1].model_dump_json()
    assert TEXT not in serialized
    assert "api_key" not in serialized
    assert provider.diagnostics[-1].output_tokens == 30
    assert provider.diagnostics[-1].thinking_level == "medium"


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
    # This SDK retains snake_case for nested ThinkingConfig fields. Validate the
    # actual transmitted value through its schema instead of assuming camelCase.
    thinking = types.ThinkingConfig.model_validate(captured[0]["generationConfig"]["thinkingConfig"])
    assert thinking.thinking_level == types.ThinkingLevel.MEDIUM
    assert thinking.thinking_budget is None
    assert provider.usage["total_token_count"] == 30


def test_sdk_serializes_compact_comparison_and_restores_url():
    captured = []
    long_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/" + "a" * 3000

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{
            "content": {"parts": [{"text": json.dumps(compact_comparison())}], "role": "model"},
            "finishReason": "STOP"}]})

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        with genai.Client(api_key="test-only-not-a-real-key", http_options=types.HttpOptions(httpx_client=transport)) as client:
            provider = GeminiProvider(Settings(), client=client)
            result = provider.compare(listing(), [Source(url=long_url, text=TEXT, access="page", accessed_at="2026-10-12")], 5)
    assert result.results[0].url == long_url
    assert "source_ids" in captured[0]["generationConfig"]["responseJsonSchema"]["properties"]
    assert long_url not in json.dumps(captured[0])
    thinking = types.ThinkingConfig.model_validate(captured[0]["generationConfig"]["thinkingConfig"])
    assert thinking.thinking_level == types.ThinkingLevel.MEDIUM
    assert thinking.thinking_budget is None

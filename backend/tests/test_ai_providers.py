"""Provider SDK adapters: response normalization and error mapping."""

import asyncio
from types import SimpleNamespace
from typing import cast

import anthropic
import httpx
import openai
import pytest

from mneme.ai.providers import AnthropicProvider, OpenAIProvider
from mneme.ai.types import AITask, ChatMessage, CompletionRequest, LLMProviderError

REQUEST = CompletionRequest(
    task=AITask.SUMMARIZE,
    messages=(ChatMessage(role="user", content="Summarize the abstract."),),
    system="You summarize research papers.",
)


class _StubMessages:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.kwargs: dict[str, object] | None = None

    async def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _StubChat:
    def __init__(self, outcome: object) -> None:
        self.completions = _StubMessages(outcome)


def _anthropic_provider(outcome: object) -> tuple[AnthropicProvider, _StubMessages]:
    stub = _StubMessages(outcome)
    client = cast(anthropic.AsyncAnthropic, SimpleNamespace(messages=stub))
    return AnthropicProvider(api_key="test", timeout_seconds=1, client=client), stub


def _openai_provider(outcome: object) -> tuple[OpenAIProvider, _StubMessages]:
    chat = _StubChat(outcome)
    client = cast(openai.AsyncOpenAI, SimpleNamespace(chat=chat))
    return OpenAIProvider(api_key="test", timeout_seconds=1, client=client), chat.completions


def _http_error_parts(status_code: int) -> tuple[httpx.Response, str]:
    request = httpx.Request("POST", "https://api.example.com/v1")
    return httpx.Response(status_code, request=request), "provider error"


@pytest.mark.base
def test_anthropic_response_is_normalized() -> None:
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text="A generated summary."),
        ],
        model="claude-haiku-4-5",
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=21, output_tokens=7),
    )
    provider, stub = _anthropic_provider(response)

    result = asyncio.run(provider.complete(model="claude-haiku-4-5", request=REQUEST))

    assert result.text == "A generated summary."
    assert result.usage.input_tokens == 21
    assert stub.kwargs is not None
    assert stub.kwargs["system"] == "You summarize research papers."


@pytest.mark.base
def test_anthropic_rate_limit_is_retryable() -> None:
    response, message = _http_error_parts(429)
    provider, _ = _anthropic_provider(
        anthropic.RateLimitError(message, response=response, body=None)
    )

    with pytest.raises(LLMProviderError) as excinfo:
        asyncio.run(provider.complete(model="claude-haiku-4-5", request=REQUEST))
    assert excinfo.value.retryable is True


@pytest.mark.base
def test_anthropic_client_error_is_not_retryable() -> None:
    response, message = _http_error_parts(400)
    provider, _ = _anthropic_provider(
        anthropic.BadRequestError(message, response=response, body=None)
    )

    with pytest.raises(LLMProviderError) as excinfo:
        asyncio.run(provider.complete(model="claude-haiku-4-5", request=REQUEST))
    assert excinfo.value.retryable is False


@pytest.mark.base
def test_anthropic_refusal_is_not_retryable() -> None:
    response = SimpleNamespace(
        content=[],
        model="claude-haiku-4-5",
        stop_reason="refusal",
        usage=SimpleNamespace(input_tokens=5, output_tokens=0),
    )
    provider, _ = _anthropic_provider(response)

    with pytest.raises(LLMProviderError) as excinfo:
        asyncio.run(provider.complete(model="claude-haiku-4-5", request=REQUEST))
    assert excinfo.value.retryable is False


@pytest.mark.base
def test_openai_response_is_normalized_with_system_message() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="An answer."))],
        model="gpt-4o",
        usage=SimpleNamespace(prompt_tokens=15, completion_tokens=3),
    )
    provider, stub = _openai_provider(response)

    result = asyncio.run(provider.complete(model="gpt-4o", request=REQUEST))

    assert result.text == "An answer."
    assert result.usage == result.usage.model_copy(update={"input_tokens": 15, "output_tokens": 3})
    assert stub.kwargs is not None
    messages = cast(list[dict[str, str]], stub.kwargs["messages"])
    assert messages[0] == {"role": "system", "content": "You summarize research papers."}


@pytest.mark.base
def test_openai_server_error_is_retryable() -> None:
    response, message = _http_error_parts(503)
    provider, _ = _openai_provider(
        openai.InternalServerError(message, response=response, body=None)
    )

    with pytest.raises(LLMProviderError) as excinfo:
        asyncio.run(provider.complete(model="gpt-4o", request=REQUEST))
    assert excinfo.value.retryable is True

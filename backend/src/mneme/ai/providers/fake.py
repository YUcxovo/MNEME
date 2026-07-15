"""Deterministic in-process provider for tests and the evaluation harness."""

from mneme.ai.types import CompletionRequest, ProviderName, ProviderResponse, TokenUsage


class FakeLLMProvider:
    """Scripted provider: no network, deterministic text and token usage.

    ``responses`` maps the final user message to a canned reply; unmatched
    prompts fall back to ``default_response``. Token usage is derived from
    word counts so cost telemetry is exercised realistically.
    """

    name = ProviderName.ANTHROPIC

    def __init__(
        self,
        *,
        name: ProviderName = ProviderName.ANTHROPIC,
        responses: dict[str, str] | None = None,
        default_response: str = "This is a scripted fake completion.",
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._responses = responses or {}
        self._default_response = default_response
        self._error = error
        self.calls: list[tuple[str, CompletionRequest]] = []

    async def complete(self, *, model: str, request: CompletionRequest) -> ProviderResponse:
        """Return the scripted response for the last user message."""
        self.calls.append((model, request))
        if self._error is not None:
            raise self._error
        prompt = request.messages[-1].content
        text = self._responses.get(prompt, self._default_response)
        input_words = sum(len(message.content.split()) for message in request.messages)
        if request.system is not None:
            input_words += len(request.system.split())
        return ProviderResponse(
            text=text,
            model=model,
            usage=TokenUsage(input_tokens=input_words, output_tokens=len(text.split())),
        )

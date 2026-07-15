"""Claude provider over the official Anthropic SDK."""

import anthropic
from anthropic.types import MessageParam

from mneme.ai.types import (
    CompletionRequest,
    LLMProviderError,
    ProviderName,
    ProviderResponse,
    TokenUsage,
)


class AnthropicProvider:
    """Text completions via the Anthropic Messages API."""

    name = ProviderName.ANTHROPIC

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)

    async def complete(self, *, model: str, request: CompletionRequest) -> ProviderResponse:
        """Call the Messages API and normalize the response."""
        messages: list[MessageParam] = [
            {"role": message.role, "content": message.content} for message in request.messages
        ]
        system: str | anthropic.Omit = (
            request.system if request.system is not None else anthropic.omit
        )
        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=request.max_output_tokens,
                system=system,
                messages=messages,
            )
        except anthropic.RateLimitError as error:
            raise LLMProviderError(str(error), retryable=True) from error
        except anthropic.APIStatusError as error:
            raise LLMProviderError(str(error), retryable=error.status_code >= 500) from error
        except anthropic.APIConnectionError as error:
            raise LLMProviderError(str(error), retryable=True) from error

        if response.stop_reason == "refusal":
            raise LLMProviderError("The provider refused the request.", retryable=False)

        text = "".join(block.text for block in response.content if block.type == "text")
        return ProviderResponse(
            text=text,
            model=response.model,
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )

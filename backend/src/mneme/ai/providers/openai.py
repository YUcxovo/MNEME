"""OpenAI provider over the official OpenAI SDK."""

import openai
from openai.types.chat import ChatCompletionMessageParam

from mneme.ai.types import (
    CompletionRequest,
    LLMProviderError,
    ProviderName,
    ProviderResponse,
    TokenUsage,
)


class OpenAIProvider:
    """Text completions via the OpenAI Chat Completions API."""

    name = ProviderName.OPENAI

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        self._client = client or openai.AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def complete(self, *, model: str, request: CompletionRequest) -> ProviderResponse:
        """Call the Chat Completions API and normalize the response."""
        messages: list[ChatCompletionMessageParam] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        for message in request.messages:
            if message.role == "user":
                messages.append({"role": "user", "content": message.content})
            else:
                messages.append({"role": "assistant", "content": message.content})
        try:
            response = await self._client.chat.completions.create(
                model=model,
                max_completion_tokens=request.max_output_tokens,
                messages=messages,
            )
        except openai.RateLimitError as error:
            raise LLMProviderError(str(error), retryable=True) from error
        except openai.APIStatusError as error:
            raise LLMProviderError(str(error), retryable=error.status_code >= 500) from error
        except openai.APIConnectionError as error:
            raise LLMProviderError(str(error), retryable=True) from error

        choice = response.choices[0] if response.choices else None
        text = choice.message.content if choice is not None and choice.message.content else ""
        usage = response.usage
        return ProviderResponse(
            text=text,
            model=response.model,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage is not None else 0,
                output_tokens=usage.completion_tokens if usage is not None else 0,
            ),
        )

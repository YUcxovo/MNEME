"""DeepSeek provider over its OpenAI-compatible Chat Completions API."""

import openai
from openai.types.chat import ChatCompletionMessageParam

from mneme.ai.types import (
    CompletionRequest,
    LLMProviderError,
    ProviderName,
    ProviderResponse,
    TokenUsage,
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider:
    """Text completions via the official DeepSeek API."""

    name = ProviderName.DEEPSEEK

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        thinking_enabled: bool = False,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        self._client = client or openai.AsyncOpenAI(
            api_key=api_key,
            base_url=DEEPSEEK_BASE_URL,
            timeout=timeout_seconds,
        )
        self._thinking_enabled = thinking_enabled

    async def complete(self, *, model: str, request: CompletionRequest) -> ProviderResponse:
        """Call DeepSeek Chat Completions and normalize the response."""
        messages: list[ChatCompletionMessageParam] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        for message in request.messages:
            if message.role == "user":
                messages.append({"role": "user", "content": message.content})
            else:
                messages.append({"role": "assistant", "content": message.content})

        thinking = "enabled" if self._thinking_enabled else "disabled"
        try:
            response = await self._client.chat.completions.create(
                model=model,
                max_tokens=request.max_output_tokens,
                messages=messages,
                extra_body={"thinking": {"type": thinking}},
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

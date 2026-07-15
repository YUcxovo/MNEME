"""Provider protocol every LLM backend implements."""

from typing import Protocol, runtime_checkable

from mneme.ai.types import CompletionRequest, ProviderName, ProviderResponse


@runtime_checkable
class LLMProvider(Protocol):
    """A backend that can produce one text completion.

    Implementations translate the provider-agnostic request into the vendor
    SDK call and map vendor errors to :class:`mneme.ai.types.LLMProviderError`.
    """

    name: ProviderName

    async def complete(self, *, model: str, request: CompletionRequest) -> ProviderResponse:
        """Generate a completion for ``request`` using ``model``."""
        ...

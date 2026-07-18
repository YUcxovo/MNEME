"""Embedding provider abstraction and the batched embedding service.

Embeddings do not flow through :class:`~mneme.ai.service.LLMService` (no
chat semantics, no per-request cache) but they share the same BudgetGuard so
embedding spend counts against the daily AI cap.
"""

import math
from typing import Protocol, runtime_checkable

import openai
import structlog
from pydantic import BaseModel, ConfigDict, Field

from mneme.ai.budget import BudgetGuard
from mneme.ai.pricing import estimate_cost
from mneme.ai.types import LLMProviderError, TokenUsage

logger = structlog.get_logger(__name__)


class EmbeddingBatch(BaseModel):
    """Vectors for one input batch plus usage telemetry."""

    model_config = ConfigDict(frozen=True)

    vectors: tuple[tuple[float, ...], ...]
    model: str
    input_tokens: int = Field(ge=0)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """A backend that embeds a batch of texts into fixed-size vectors."""

    async def embed(self, *, model: str, texts: list[str]) -> EmbeddingBatch:
        """Return one vector per input text, in input order."""
        ...


class OpenAIEmbeddingProvider:
    """Embeddings via the OpenAI Embeddings API."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        self._client = client or openai.AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def embed(self, *, model: str, texts: list[str]) -> EmbeddingBatch:
        """Call the Embeddings API and normalize the response."""
        try:
            response = await self._client.embeddings.create(model=model, input=texts)
        except openai.RateLimitError as error:
            raise LLMProviderError(str(error), retryable=True) from error
        except openai.APIStatusError as error:
            raise LLMProviderError(str(error), retryable=error.status_code >= 500) from error
        except openai.APIConnectionError as error:
            raise LLMProviderError(str(error), retryable=True) from error

        ordered = sorted(response.data, key=lambda item: item.index)
        return EmbeddingBatch(
            vectors=tuple(tuple(item.embedding) for item in ordered),
            model=response.model,
            input_tokens=response.usage.prompt_tokens if response.usage is not None else 0,
        )


class FakeEmbeddingProvider:
    """Deterministic, network-free embeddings for tests and evaluation.

    Vectors are derived from a rolling hash of the text so that identical
    texts embed identically and similar texts stay unrelated -- enough to
    exercise storage, batching, and ANN plumbing.
    """

    def __init__(self, *, dimensions: int = 8) -> None:
        self._dimensions = dimensions
        self.calls: list[tuple[str, list[str]]] = []

    async def embed(self, *, model: str, texts: list[str]) -> EmbeddingBatch:
        self.calls.append((model, list(texts)))
        vectors = []
        for text in texts:
            seed = sum(ord(char) * (index + 1) for index, char in enumerate(text))
            raw = [math.sin(seed * (dim + 1)) for dim in range(self._dimensions)]
            norm = math.sqrt(sum(value * value for value in raw)) or 1.0
            vectors.append(tuple(value / norm for value in raw))
        total_words = sum(len(text.split()) for text in texts)
        return EmbeddingBatch(vectors=tuple(vectors), model=model, input_tokens=total_words)


class EmbeddingService:
    """Embed texts in bounded batches under the shared daily budget."""

    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        budget: BudgetGuard,
        model: str,
        batch_size: int,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._provider = provider
        self._budget = budget
        self._model = model
        self._batch_size = batch_size

    @property
    def model(self) -> str:
        """The embedding model identifier persisted next to each vector."""
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        """Embed all texts in input order, one budget check per batch."""
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            await self._budget.ensure_capacity()
            result = await self._provider.embed(model=self._model, texts=batch)
            if len(result.vectors) != len(batch):
                raise LLMProviderError(
                    f"Embedding provider returned {len(result.vectors)} vectors "
                    f"for {len(batch)} inputs.",
                    retryable=False,
                )
            cost = estimate_cost(
                result.model, TokenUsage(input_tokens=result.input_tokens, output_tokens=0)
            )
            await self._budget.record_spend(cost)
            vectors.extend(result.vectors)
            logger.info(
                "embedding_batch_completed",
                model=result.model,
                batch_size=len(batch),
                input_tokens=result.input_tokens,
                estimated_cost_usd=str(cost),
            )
        return vectors

    async def embed_query(self, text: str) -> tuple[float, ...]:
        """Embed one retrieval query."""
        vectors = await self.embed_texts([text])
        return vectors[0]

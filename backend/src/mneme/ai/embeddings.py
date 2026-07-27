"""Embedding provider abstraction and the batched embedding service.

Embeddings do not flow through :class:`~mneme.ai.service.LLMService` (no
chat semantics, no per-request cache) but they share the same BudgetGuard so
embedding spend counts against the daily AI cap.
"""

import asyncio
import math
from collections.abc import Callable, Iterable, Sequence
from decimal import Decimal
from importlib import import_module
from threading import Lock
from typing import Protocol, runtime_checkable

import openai
import structlog
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from mneme.ai.budget import BudgetGuard
from mneme.ai.pricing import estimate_cost
from mneme.ai.types import LLMProviderError, ProviderNotConfiguredError, TokenUsage
from mneme.core.config import EmbeddingBackend, Settings

logger = structlog.get_logger(__name__)

PGVECTOR_DIMENSIONS = 1536


class FastEmbedClient(Protocol):
    """Synchronous FastEmbed surface used behind a worker thread."""

    def embed(self, documents: list[str]) -> Iterable[Sequence[float]]:
        """Return one native model vector per document."""
        ...


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


class FastEmbedEmbeddingProvider:
    """Local ONNX embeddings adapted to the frozen pgvector width."""

    def __init__(
        self,
        *,
        source_model: str,
        dimensions: int = PGVECTOR_DIMENSIONS,
        client: FastEmbedClient | None = None,
    ) -> None:
        if not source_model:
            raise ValueError("source_model must not be empty")
        if dimensions < 1:
            raise ValueError("dimensions must be at least 1")
        self._source_model = source_model
        self._dimensions = dimensions
        self._client = client
        self._client_lock = Lock()

    def _get_client(self) -> FastEmbedClient:
        if self._client is not None:
            return self._client
        with self._client_lock:
            if self._client is None:
                try:
                    fastembed = import_module("fastembed")
                except ImportError as error:
                    raise ProviderNotConfiguredError(
                        "FastEmbed is not installed; install the local-embeddings extra."
                    ) from error
                self._client = fastembed.TextEmbedding(model_name=self._source_model)
        return self._client

    def _embed_sync(self, texts: list[str]) -> list[Sequence[float]]:
        return list(self._get_client().embed(texts))

    def _normalize_and_pad(self, raw: Sequence[float]) -> tuple[float, ...]:
        vector = tuple(float(value) for value in raw)
        if not vector:
            raise LLMProviderError("Embedding provider returned an empty vector.", retryable=False)
        if len(vector) > self._dimensions:
            raise LLMProviderError(
                f"Local embedding has {len(vector)} dimensions; "
                f"the configured store supports {self._dimensions}.",
                retryable=False,
            )
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise LLMProviderError("Embedding provider returned a zero vector.", retryable=False)
        normalized = tuple(value / norm for value in vector)
        return normalized + (0.0,) * (self._dimensions - len(normalized))

    async def embed(self, *, model: str, texts: list[str]) -> EmbeddingBatch:
        """Run local inference off the event loop and normalize its vectors."""
        try:
            raw_vectors = await asyncio.to_thread(self._embed_sync, texts)
        except ProviderNotConfiguredError:
            raise
        except Exception as error:
            raise LLMProviderError(
                "The local embedding model failed to load or run.", retryable=True
            ) from error
        return EmbeddingBatch(
            vectors=tuple(self._normalize_and_pad(vector) for vector in raw_vectors),
            model=model,
            input_tokens=sum(len(text.split()) for text in texts),
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
        spend_listener: Callable[[Decimal], None] | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._provider = provider
        self._budget = budget
        self._model = model
        self._batch_size = batch_size
        self._spend_listener = spend_listener

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
            if self._spend_listener is not None:
                self._spend_listener(cost)
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


def build_embedding_service(
    settings: Settings,
    redis: Redis,
    *,
    spend_listener: Callable[[Decimal], None] | None = None,
) -> EmbeddingService | None:
    """Build the explicitly configured embedding backend."""
    if settings.ai_embedding_backend is EmbeddingBackend.FASTEMBED:
        provider: EmbeddingProvider = FastEmbedEmbeddingProvider(
            source_model=settings.ai_local_embedding_model
        )
    else:
        if settings.openai_api_key is None:
            return None
        provider = OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return EmbeddingService(
        provider=provider,
        budget=BudgetGuard(redis, daily_cap_usd=settings.ai_daily_budget_usd),
        model=settings.ai_embedding_model,
        batch_size=settings.ai_embedding_batch_size,
        spend_listener=spend_listener,
    )

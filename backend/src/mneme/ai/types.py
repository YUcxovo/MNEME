"""Shared request/response types and errors for the AI service layer."""

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AITask(StrEnum):
    """AI workloads that route to (potentially) different models."""

    SUMMARIZE = "summarize"
    QA = "qa"


class ProviderName(StrEnum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    OPENAI = "openai"


class ChatMessage(BaseModel):
    """One conversational turn sent to a provider."""

    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class CompletionRequest(BaseModel):
    """Provider-agnostic completion request.

    ``prompt_version`` participates in the cache key so that bumping a prompt
    template invalidates previously cached generations without a manual flush.
    """

    model_config = ConfigDict(frozen=True)

    task: AITask
    messages: tuple[ChatMessage, ...] = Field(min_length=1)
    system: str | None = None
    max_output_tokens: int = Field(default=2048, ge=1)
    prompt_version: str = Field(default="v0", min_length=1, max_length=100)


class TokenUsage(BaseModel):
    """Token counts reported by a provider for one completion."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ProviderResponse(BaseModel):
    """Raw provider output before cost and latency accounting."""

    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    usage: TokenUsage


class CompletionResult(BaseModel):
    """Fully accounted completion, safe to cache and to persist."""

    model_config = ConfigDict(frozen=True)

    text: str
    task: AITask
    provider: ProviderName
    model: str
    prompt_version: str
    usage: TokenUsage
    estimated_cost: Decimal = Field(ge=Decimal(0))
    latency_ms: int = Field(ge=0)
    cached: bool = False


class AIError(Exception):
    """Base class for expected AI-layer failures."""


class LLMProviderError(AIError):
    """A provider call failed after leaving this process."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderNotConfiguredError(AIError):
    """The route resolved to a provider that has no configured credentials."""

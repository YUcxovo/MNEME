"""Task routing and provider inference."""

import pytest

from mneme.ai.routing import ModelRouter, UnroutableModelError, infer_provider
from mneme.ai.types import AITask, ProviderName


@pytest.mark.base
def test_provider_inferred_from_model_prefix() -> None:
    assert infer_provider("claude-opus-4-8") is ProviderName.ANTHROPIC
    assert infer_provider("deepseek-v4-flash") is ProviderName.DEEPSEEK
    assert infer_provider("gpt-4o-mini") is ProviderName.OPENAI


@pytest.mark.base
def test_unknown_model_prefix_is_unroutable() -> None:
    with pytest.raises(UnroutableModelError):
        infer_provider("llama-3-70b")


@pytest.mark.base
def test_router_resolves_every_task() -> None:
    router = ModelRouter({AITask.SUMMARIZE: "claude-haiku-4-5", AITask.QA: "gpt-4o"})

    assert router.resolve(AITask.SUMMARIZE).provider is ProviderName.ANTHROPIC
    assert router.resolve(AITask.QA).model == "gpt-4o"


@pytest.mark.base
def test_router_rejects_incomplete_configuration() -> None:
    with pytest.raises(UnroutableModelError):
        ModelRouter({AITask.SUMMARIZE: "claude-haiku-4-5"})


@pytest.mark.base
def test_router_rejects_unroutable_model_at_startup() -> None:
    with pytest.raises(UnroutableModelError):
        ModelRouter({AITask.SUMMARIZE: "mystery-model", AITask.QA: "gpt-4o"})

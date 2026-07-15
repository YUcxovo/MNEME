"""Task-to-model routing with provider inference from the model name."""

from pydantic import BaseModel, ConfigDict

from mneme.ai.types import AITask, ProviderName


class UnroutableModelError(ValueError):
    """A configured model name does not map to a known provider."""


class ModelRoute(BaseModel):
    """Resolved provider and model for one AI task."""

    model_config = ConfigDict(frozen=True)

    provider: ProviderName
    model: str


def infer_provider(model: str) -> ProviderName:
    """Infer the owning provider from a model identifier."""
    if model.startswith("claude-"):
        return ProviderName.ANTHROPIC
    if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return ProviderName.OPENAI
    raise UnroutableModelError(f"No provider known for model {model!r}.")


class ModelRouter:
    """Resolve which provider/model serves each :class:`AITask`.

    Routes are validated eagerly so a misconfigured model name fails at
    startup instead of on the first request.
    """

    def __init__(self, models: dict[AITask, str]) -> None:
        missing = set(AITask) - models.keys()
        if missing:
            raise UnroutableModelError(
                f"Missing model configuration for tasks: {sorted(task.value for task in missing)}."
            )
        self._routes = {
            task: ModelRoute(provider=infer_provider(model), model=model)
            for task, model in models.items()
        }

    def resolve(self, task: AITask) -> ModelRoute:
        """Return the route configured for a task."""
        return self._routes[task]

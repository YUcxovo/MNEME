"""Offline production-configuration checks."""

import re

from pydantic import SecretStr

from mneme.ai.routing import UnroutableModelError, infer_provider
from mneme.ai.types import ProviderName
from mneme.core.config import EmbeddingBackend, Environment, Settings
from mneme.ops.preflight_types import PreflightCheck, boolean_check

_TOKEN_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def static_preflight_checks(settings: Settings) -> tuple[PreflightCheck, ...]:
    """Evaluate production configuration without contacting dependencies."""
    checks: list[PreflightCheck] = []
    production_ok = (
        settings.environment is Environment.PRODUCTION
        and not settings.debug
        and settings.log_level.upper() in {"INFO", "WARNING", "ERROR", "CRITICAL"}
    )
    checks.append(boolean_check("production_mode", production_ok, "Production mode is safe."))
    checks.append(
        boolean_check(
            "loopback_binding",
            settings.api_host == "127.0.0.1",
            "The API is bound to the trusted reverse-proxy interface.",
        )
    )
    checks.append(
        boolean_check(
            "graceful_timeout",
            settings.api_graceful_timeout_seconds >= settings.llm_timeout_seconds,
            "Graceful shutdown covers the configured model timeout.",
        )
    )
    token = (
        settings.demo_token_sha256.get_secret_value()
        if settings.demo_token_sha256 is not None
        else ""
    )
    checks.append(
        boolean_check(
            "demo_identity",
            settings.demo_user_id is not None and bool(_TOKEN_DIGEST_PATTERN.fullmatch(token)),
            "The demo identity is configured.",
        )
    )
    checks.append(_provider_check(settings))
    database_safe = not _contains_placeholder(settings.database_url) and not any(
        marker in settings.database_url.lower()
        for marker in ("postgres:postgres@", "<db-user>", "<db-password>")
    )
    checks.append(
        boolean_check(
            "database_configuration",
            database_safe,
            "The database configuration does not use known development placeholders.",
        )
    )
    checks.append(
        boolean_check(
            "paper_storage_configuration",
            settings.paper_storage_dir.is_absolute(),
            "The paper storage location is absolute.",
        )
    )
    return tuple(checks)


def _provider_check(settings: Settings) -> PreflightCheck:
    keys = {
        ProviderName.ANTHROPIC: _usable_secret(settings.anthropic_api_key),
        ProviderName.DEEPSEEK: _usable_secret(settings.deepseek_api_key),
        ProviderName.OPENAI: _usable_secret(settings.openai_api_key),
    }
    try:
        routes = (infer_provider(settings.llm_summary_model), infer_provider(settings.llm_qa_model))
        configured = all(keys[route] for route in routes)
    except UnroutableModelError:
        configured = False
    if settings.ai_embedding_backend is EmbeddingBackend.OPENAI:
        configured = configured and keys[ProviderName.OPENAI]
    model_values = (
        settings.llm_summary_model,
        settings.llm_qa_model,
        settings.ai_embedding_model,
    )
    configured = configured and not any(_contains_placeholder(value) for value in model_values)
    return boolean_check("provider_routes", configured, "AI routes have configured credentials.")


def _contains_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(
        marker in lowered
        for marker in ("<", ">", "replace-me", "changeme", "placeholder", "your-key")
    )


def _usable_secret(value: SecretStr | None) -> bool:
    return value is not None and not _contains_placeholder(value.get_secret_value())

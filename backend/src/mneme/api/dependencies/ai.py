"""Shared dependencies for AI endpoints."""

from fastapi import Request

from mneme.ai.service import LLMService, build_llm_service


def get_llm_service(request: Request) -> LLMService:
    """Return the lazily constructed application-scoped LLM service."""
    service: LLMService | None = getattr(request.app.state, "llm_service", None)
    if service is None:
        service = build_llm_service(request.app.state.settings, request.app.state.redis)
        request.app.state.llm_service = service
    return service

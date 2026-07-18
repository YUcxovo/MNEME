"""Authenticated grounded Q&A endpoint (Milestone 3)."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.embeddings import EmbeddingService
from mneme.ai.qa import GroundedAnswerService
from mneme.ai.retrieval import RetrievalService
from mneme.ai.service import LLMService
from mneme.ai.types import AIError
from mneme.api.dependencies.ai import (
    get_artifact_repository,
    get_embedding_service,
    get_llm_service,
    get_qa_repository,
    map_ai_error,
)
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import get_paper_catalog_repository
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.qa import Answer, Question
from mneme.core.config import Settings, get_settings
from mneme.db.dependencies import get_session
from mneme.models.qa import QaMessage
from mneme.repositories.artifacts import ArtifactRepository
from mneme.repositories.paper_catalog import PaperCatalogRepository
from mneme.repositories.qa import ConversationMismatchError, QaConversationRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/qa", tags=["ai"])


def get_request_settings() -> Settings:
    """Return process settings; overridable in tests."""
    return get_settings()


@router.post(
    "/ask",
    response_model=Answer,
    operation_id="askQuestion",
    responses={"default": {"model": ErrorResponse}},
)
async def ask_question(
    payload: Question,
    principal: Annotated[Principal, Depends(require_principal)],
    catalog: Annotated[PaperCatalogRepository, Depends(get_paper_catalog_repository)],
    artifacts: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    conversations: Annotated[QaConversationRepository, Depends(get_qa_repository)],
    llm: Annotated[LLMService, Depends(get_llm_service)],
    embedder: Annotated[EmbeddingService, Depends(get_embedding_service)],
    settings: Annotated[Settings, Depends(get_request_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Answer:
    """Answer one single-paper question with verified citations.

    Papers without embedded chunks produce a stable refusal with
    ``source_match_status=insufficient_evidence`` instead of an error, so
    clients can distinguish "not answerable yet" from "broken".
    """
    paper = await catalog.get_paper(payload.paper_id)
    if paper is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "paper_not_found",
            "The requested paper does not exist.",
        )
    try:
        conversation = await conversations.resolve_conversation(
            conversation_id=payload.conversation_id,
            user_id=principal.user_id,
            paper_id=payload.paper_id,
        )
    except ConversationMismatchError as error:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "conversation_not_found",
            "The requested conversation does not exist for this user and paper.",
        ) from error

    retrieval = RetrievalService(
        embedder=embedder, artifacts=artifacts, top_k=settings.ai_retrieval_top_k
    )
    generator = GroundedAnswerService(
        llm,
        rerank_top_n=settings.ai_qa_rerank_top_n,
        min_evidence_score=settings.ai_qa_min_evidence_score,
        max_output_tokens=settings.ai_qa_max_output_tokens,
    )
    try:
        chunks = await retrieval.retrieve(paper_id=payload.paper_id, question=payload.question)
        grounded = await generator.answer(question=payload.question, chunks=chunks)
    except AIError as error:
        raise map_ai_error(error) from error

    completion = grounded.completion
    await conversations.append_exchange(
        conversation=conversation,
        question=payload.question,
        answer=QaMessage(
            content=grounded.answer,
            citations=[
                {
                    "chunk_id": str(citation.chunk.chunk_id),
                    "marker": citation.marker,
                    "section_title": citation.chunk.section_title,
                    "source_match": citation.source_match,
                }
                for citation in grounded.citations
            ],
            source_match_status=grounded.source_match_status,
            provider=completion.provider.value if completion is not None else None,
            model_snapshot=completion.model if completion is not None else None,
            prompt_version=completion.prompt_version if completion is not None else None,
            estimated_cost=completion.estimated_cost if completion is not None else None,
            input_tokens=completion.usage.input_tokens if completion is not None else None,
            output_tokens=completion.usage.output_tokens if completion is not None else None,
            latency_ms=completion.latency_ms if completion is not None else None,
        ),
    )
    await session.commit()

    logger.info(
        "qa_question_answered",
        paper_id=str(payload.paper_id),
        conversation_id=str(conversation.id),
        source_match_status=grounded.source_match_status.value,
    )
    return Answer.from_grounded(grounded, arxiv_id=paper.arxiv_id, conversation_id=conversation.id)

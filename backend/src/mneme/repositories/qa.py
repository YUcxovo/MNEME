"""Persistence for single-paper Q&A conversations and messages."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.qa import QaConversation, QaMessage, QaRole

QA_HISTORY_MAX_MESSAGES = 8


class ConversationMismatchError(ValueError):
    """The conversation exists but belongs to another user or paper."""


class QaConversationRepository:
    """Store Q&A exchanges through one request session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_conversation(
        self, *, conversation_id: UUID | None, user_id: UUID, paper_id: UUID
    ) -> QaConversation:
        """Return the requested conversation or start a new one.

        Raises :class:`ConversationMismatchError` when the id exists but is
        scoped to a different user or paper, so callers can map it to a
        stable API error instead of leaking cross-user history.
        """
        if conversation_id is not None:
            conversation = await self._session.get(QaConversation, conversation_id)
            if conversation is None:
                raise ConversationMismatchError("Unknown conversation.")
            if conversation.user_id != user_id or conversation.paper_id != paper_id:
                raise ConversationMismatchError("Conversation does not match user and paper.")
            return conversation
        conversation = QaConversation(user_id=user_id, paper_id=paper_id)
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def next_sequence_number(self, conversation_id: UUID) -> int:
        """Return the next free message slot in a conversation."""
        result = await self._session.scalar(
            select(func.max(QaMessage.sequence_number)).where(
                QaMessage.conversation_id == conversation_id
            )
        )
        return 0 if result is None else result + 1

    async def get_recent_messages(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID,
        paper_id: UUID,
        limit: int = QA_HISTORY_MAX_MESSAGES,
    ) -> list[QaMessage]:
        """Return a bounded chronological history for one user's paper conversation.

        The user and paper predicates deliberately repeat the checks performed by
        :meth:`resolve_conversation`. Keeping those boundaries in the history query
        prevents a future caller from loading turns by conversation id alone.
        """
        if limit < 0:
            raise ValueError("limit must not be negative")
        if limit == 0:
            return []
        statement = (
            select(QaMessage)
            .join(QaConversation, QaMessage.conversation_id == QaConversation.id)
            .where(
                QaConversation.id == conversation_id,
                QaConversation.user_id == user_id,
                QaConversation.paper_id == paper_id,
            )
            .order_by(QaMessage.sequence_number.desc())
            .limit(limit)
        )
        messages = list((await self._session.scalars(statement)).all())
        messages.reverse()
        return messages

    async def append_exchange(
        self,
        *,
        conversation: QaConversation,
        question: str,
        answer: QaMessage,
    ) -> QaMessage:
        """Persist one question/answer pair in sequence order.

        ``answer`` carries content, citations, and generation telemetry; its
        conversation and sequence fields are assigned here.
        """
        sequence = await self.next_sequence_number(conversation.id)
        self._session.add(
            QaMessage(
                conversation_id=conversation.id,
                sequence_number=sequence,
                role=QaRole.USER,
                content=question,
            )
        )
        answer.conversation_id = conversation.id
        answer.sequence_number = sequence + 1
        answer.role = QaRole.ASSISTANT
        self._session.add(answer)
        await self._session.flush()
        return answer

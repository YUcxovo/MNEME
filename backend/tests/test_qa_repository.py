"""Conversation-history boundaries for follow-up Q&A."""

import asyncio
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from mneme.models.qa import QaConversation, QaMessage, QaRole
from mneme.repositories.qa import ConversationMismatchError, QaConversationRepository


class FakeScalarResult:
    def __init__(self, messages: list[QaMessage]) -> None:
        self._messages = messages

    def all(self) -> list[QaMessage]:
        return self._messages


class FakeSession:
    def __init__(
        self,
        *,
        conversation: QaConversation | None = None,
        messages: list[QaMessage] | None = None,
    ) -> None:
        self.conversation = conversation
        self.messages = messages or []
        self.statements: list[Select[tuple[QaMessage]]] = []

    async def get(self, model: type[QaConversation], identity: UUID) -> QaConversation | None:
        del model, identity
        return self.conversation

    async def scalars(self, statement: Select[tuple[QaMessage]]) -> FakeScalarResult:
        self.statements.append(statement)
        return FakeScalarResult(self.messages)


@pytest.mark.base
@pytest.mark.parametrize("wrong_scope", ["user", "paper"])
def test_existing_conversation_is_rejected_outside_its_user_and_paper(wrong_scope: str) -> None:
    user_id = uuid4()
    paper_id = uuid4()
    conversation = QaConversation(
        id=uuid4(),
        user_id=uuid4() if wrong_scope == "user" else user_id,
        paper_id=uuid4() if wrong_scope == "paper" else paper_id,
    )
    repository = QaConversationRepository(
        cast(AsyncSession, FakeSession(conversation=conversation))
    )

    with pytest.raises(ConversationMismatchError):
        asyncio.run(
            repository.resolve_conversation(
                conversation_id=conversation.id,
                user_id=user_id,
                paper_id=paper_id,
            )
        )


@pytest.mark.base
def test_recent_history_is_bounded_scoped_and_returned_chronologically() -> None:
    conversation_id = uuid4()
    user_id = uuid4()
    paper_id = uuid4()
    newest_first = [
        QaMessage(
            conversation_id=conversation_id,
            sequence_number=sequence,
            role=QaRole.USER if sequence % 2 == 0 else QaRole.ASSISTANT,
            content=f"turn-{sequence}",
        )
        for sequence in range(11, 3, -1)
    ]
    session = FakeSession(messages=newest_first)
    repository = QaConversationRepository(cast(AsyncSession, session))

    messages = asyncio.run(
        repository.get_recent_messages(
            conversation_id=conversation_id,
            user_id=user_id,
            paper_id=paper_id,
            limit=8,
        )
    )

    assert [message.sequence_number for message in messages] == list(range(4, 12))
    statement = session.statements[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert f"qa_conversations.id = '{conversation_id}'" in sql
    assert f"qa_conversations.user_id = '{user_id}'" in sql
    assert f"qa_conversations.paper_id = '{paper_id}'" in sql
    assert "ORDER BY qa_messages.sequence_number DESC" in sql
    assert "LIMIT 8" in sql

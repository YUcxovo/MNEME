"""Strict schemas and adapters for controlled behavior evaluation fixtures."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from mneme.ai.recommendation import PaperCandidate
from mneme.models.user import UserEventType
from mneme.services.behavior import BehaviorSignal

_Item = TypeVar("_Item")
_Identity = TypeVar("_Identity", bound=Hashable)


class ScenarioFamily(StrEnum):
    """Mechanism families frozen by the evaluation protocol."""

    COLD_START = "cold_start"
    STABLE_POSITIVE = "stable_positive"
    RECENT_INTEREST_SHIFT = "recent_interest_shift"
    EXPOSED_NEGATIVE = "exposed_negative"
    UNEXPOSED_SKIP = "unexposed_skip"
    REPEATED_SAME_PAPER = "repeated_same_paper"
    CONTRADICTORY_FEEDBACK = "contradictory_feedback"
    MISSING_EMBEDDING = "missing_embedding"
    DUPLICATE_REPLAY = "duplicate_replay"


class ScenarioPhase(StrEnum):
    """Position of a case in a controlled pair."""

    SINGLE = "single"
    BEFORE = "before"
    AFTER = "after"
    REPLAY = "replay"


class EvaluationSettings(BaseModel):
    """Frozen analysis parameters declared before the recorded run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_k: int = Field(default=5, ge=1)
    bootstrap_seed: int
    bootstrap_replicates: int = Field(ge=1)
    confidence_interval: float = Field(default=0.95, gt=0, lt=1)
    round_digits: int = Field(default=6, ge=0, le=12)


class FixturePaper(BaseModel):
    """Artificial paper metadata and its controlled representation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paper_id: UUID
    title: str = Field(min_length=1)
    categories: tuple[str, ...]
    published_at: AwareDatetime
    embedding: tuple[float, ...] | None
    candidate: bool


class FixtureEvent(BaseModel):
    """One artificial, client-shaped behavioral event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    event_type: UserEventType
    paper_id: UUID | None
    occurred_at: AwareDatetime
    duration_ms: int | None = Field(default=None, ge=0)


class RelevanceJudgment(BaseModel):
    """Graded synthetic relevance for one candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paper_id: UUID
    grade: int = Field(ge=0, le=3)
    eligible: bool = True


class BehaviorScenario(BaseModel):
    """One controlled history and candidate-ranking problem."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str = Field(min_length=1)
    family: ScenarioFamily
    pair_id: str | None = None
    phase: ScenarioPhase = ScenarioPhase.SINGLE
    explicit_topics: tuple[str, ...] = ()
    candidate_ids: tuple[UUID, ...] = Field(min_length=1)
    events: tuple[FixtureEvent, ...] = ()
    judgments: tuple[RelevanceJudgment, ...] = ()
    target_paper_id: UUID | None = None


class BehaviorFixtureFile(BaseModel):
    """Versioned, self-validating controlled evaluation corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["behavior-controlled-fixture-v1"]
    fixture_version: Literal["behavior-controlled-v1"]
    controlled_synthetic: Literal[True]
    reference_time_utc: AwareDatetime
    embedding_dimensions: int = Field(ge=1)
    evaluation: EvaluationSettings
    papers: tuple[FixturePaper, ...] = Field(min_length=1)
    scenarios: tuple[BehaviorScenario, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Reject ambiguous identities, references, dimensions, and pairs."""
        papers = _unique_map(self.papers, key=lambda paper: paper.paper_id, label="paper")
        _unique_map(self.scenarios, key=lambda scenario: scenario.scenario_id, label="scenario")
        for paper in self.papers:
            if paper.embedding is not None and len(paper.embedding) != self.embedding_dimensions:
                raise ValueError("Paper embedding dimension does not match the fixture envelope.")
        for scenario in self.scenarios:
            self._validate_scenario(scenario, papers)
        self._validate_pairs()
        return self

    def _validate_scenario(
        self, scenario: BehaviorScenario, papers: dict[UUID, FixturePaper]
    ) -> None:
        candidates = set(scenario.candidate_ids)
        if len(candidates) != len(scenario.candidate_ids):
            raise ValueError("Candidate IDs must be unique within a scenario.")
        if any(
            candidate not in papers or not papers[candidate].candidate for candidate in candidates
        ):
            raise ValueError("Every candidate must reference a declared candidate paper.")
        _unique_map(scenario.events, key=lambda event: event.event_id, label="event")
        _unique_map(scenario.judgments, key=lambda item: item.paper_id, label="judgment")
        for event in scenario.events:
            if event.occurred_at > self.reference_time_utc:
                raise ValueError("Fixture events cannot occur after the reference time.")
            if event.event_type is UserEventType.DIGEST_DISMISSED:
                if event.paper_id is not None:
                    raise ValueError("Digest dismissal cannot reference a paper.")
            elif event.paper_id not in papers:
                raise ValueError("Every paper-scoped event must reference a declared paper.")
            if event.duration_ms is not None and event.event_type is not UserEventType.PAPER_OPENED:
                raise ValueError("Only opened events may declare duration.")
        if any(judgment.paper_id not in candidates for judgment in scenario.judgments):
            raise ValueError("Judgments must reference scenario candidates.")
        if scenario.target_paper_id is not None and scenario.target_paper_id not in candidates:
            raise ValueError("The target paper must be a scenario candidate.")
        if scenario.phase is not ScenarioPhase.SINGLE and scenario.pair_id is None:
            raise ValueError("Paired phases require a pair ID.")

    def _validate_pairs(self) -> None:
        pairs: dict[str, list[BehaviorScenario]] = {}
        for scenario in self.scenarios:
            if scenario.pair_id is not None:
                pairs.setdefault(scenario.pair_id, []).append(scenario)
        for cases in pairs.values():
            candidate_sets = {case.candidate_ids for case in cases}
            targets = {case.target_paper_id for case in cases}
            if len(candidate_sets) != 1 or len(targets) != 1:
                raise ValueError("Paired scenarios must share candidates and target paper.")
            if cases[0].family is ScenarioFamily.DUPLICATE_REPLAY and any(
                case.events != cases[0].events for case in cases[1:]
            ):
                raise ValueError("Duplicate replay cases must use identical event histories.")


def load_behavior_fixtures(path: Path) -> BehaviorFixtureFile:
    """Load and validate one UTF-8 fixture file."""
    return BehaviorFixtureFile.model_validate_json(path.read_text(encoding="utf-8"))


def scenario_signals(scenario: BehaviorScenario) -> tuple[BehaviorSignal, ...]:
    """Adapt fixture events to the production behavior-model input."""
    return tuple(
        BehaviorSignal(
            event_type=event.event_type,
            paper_id=event.paper_id,
            occurred_at=event.occurred_at,
            duration_ms=event.duration_ms,
        )
        for event in scenario.events
    )


def scenario_embeddings(fixture: BehaviorFixtureFile) -> dict[UUID, tuple[float, ...]]:
    """Return every available controlled paper representation."""
    return {
        paper.paper_id: paper.embedding for paper in fixture.papers if paper.embedding is not None
    }


def scenario_candidates(
    fixture: BehaviorFixtureFile, scenario: BehaviorScenario
) -> list[PaperCandidate]:
    """Adapt declared candidate IDs to production recommendation inputs."""
    papers = {paper.paper_id: paper for paper in fixture.papers}
    return [
        PaperCandidate(
            paper_id=paper_id,
            title=papers[paper_id].title,
            categories=papers[paper_id].categories,
            published_at=papers[paper_id].published_at,
            embedding=papers[paper_id].embedding,
        )
        for paper_id in scenario.candidate_ids
    ]


def _unique_map(
    items: tuple[_Item, ...],
    *,
    key: Callable[[_Item], _Identity],
    label: str,
) -> dict[_Identity, _Item]:
    values: dict[_Identity, _Item] = {}
    for item in items:
        identity = key(item)
        if identity in values:
            raise ValueError(f"Duplicate {label} identity in behavior fixture.")
        values[identity] = item
    return values

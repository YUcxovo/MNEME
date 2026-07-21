"""Canonical identities for durable pipeline jobs."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Final
from uuid import UUID

from mneme.models.job import PipelineJob, PipelineStage

PIPELINE_VERSION: Final = "v1"

_VERSION_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_HEX_DIGEST_PATTERN: Final = re.compile(r"[0-9a-f]{64}")
_REVISION_SCOPED_STAGES: Final = frozenset(
    {
        PipelineStage.DOWNLOAD_PDF,
        PipelineStage.PARSE_PDF,
        PipelineStage.SUMMARIZE_PAPER,
        PipelineStage.CHUNK_PAPER,
        PipelineStage.EMBED_CHUNKS,
    }
)


class PipelineJobIdentityConflictError(RuntimeError):
    """One idempotency key is already bound to a different durable identity."""

    code: Final = "pipeline_job_identity_conflict"

    def __init__(self) -> None:
        super().__init__("Pipeline job idempotency key conflicts with its stored identity.")


def _canonicalize(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("Pipeline job identity keys must be non-empty strings.")
            result[key] = _canonicalize(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    raise TypeError("Pipeline job identity contains an unsupported value.")


def _validate_version(pipeline_version: str) -> None:
    if _VERSION_PATTERN.fullmatch(pipeline_version) is None:
        raise ValueError("Pipeline version must be a non-empty portable identifier.")


def build_job_idempotency_key(
    *,
    stage: PipelineStage,
    scope: Mapping[str, object],
    inputs: Mapping[str, object],
    pipeline_version: str = PIPELINE_VERSION,
) -> str:
    """Hash the canonical pipeline version, stage, scope, and inputs."""
    if not isinstance(stage, PipelineStage):
        raise TypeError("Pipeline stage must be a PipelineStage value.")
    _validate_version(pipeline_version)
    if not scope:
        raise ValueError("Pipeline job scope must not be empty.")
    payload = {
        "inputs": _canonicalize(inputs),
        "pipeline_version": pipeline_version,
        "scope": _canonicalize(scope),
        "stage": stage.value,
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return f"{pipeline_version}:{stage.value}:{hashlib.sha256(encoded).hexdigest()}"


def download_idempotency_key(
    *, paper_id: UUID, paper_version_id: UUID, arxiv_id: str, version_number: int
) -> str:
    """Return the source-revision identity for a PDF download."""
    if not arxiv_id or version_number < 1:
        raise ValueError("A valid arXiv ID and positive version are required.")
    return build_job_idempotency_key(
        stage=PipelineStage.DOWNLOAD_PDF,
        scope={"paper_id": paper_id, "paper_version_id": paper_version_id},
        inputs={"arxiv_id": arxiv_id, "version_number": version_number},
    )


def parse_idempotency_key(*, paper_id: UUID, paper_version_id: UUID, source_checksum: str) -> str:
    """Return the source-artifact identity for parsing one revision."""
    _validate_checksum(source_checksum)
    return build_job_idempotency_key(
        stage=PipelineStage.PARSE_PDF,
        scope={"paper_id": paper_id, "paper_version_id": paper_version_id},
        inputs={"source_checksum": source_checksum},
    )


def summarize_idempotency_key(
    *,
    paper_id: UUID,
    paper_version_id: UUID,
    parsed_checksum: str,
    parser_version: str,
) -> str:
    """Return the parsed-artifact identity for summarizing one revision."""
    return _parsed_artifact_key(
        stage=PipelineStage.SUMMARIZE_PAPER,
        paper_id=paper_id,
        paper_version_id=paper_version_id,
        parsed_checksum=parsed_checksum,
        parser_version=parser_version,
    )


def chunk_idempotency_key(
    *,
    paper_id: UUID,
    paper_version_id: UUID,
    parsed_checksum: str,
    parser_version: str,
) -> str:
    """Return the parsed-artifact identity for chunking one revision."""
    return _parsed_artifact_key(
        stage=PipelineStage.CHUNK_PAPER,
        paper_id=paper_id,
        paper_version_id=paper_version_id,
        parsed_checksum=parsed_checksum,
        parser_version=parser_version,
    )


def _parsed_artifact_key(
    *,
    stage: PipelineStage,
    paper_id: UUID,
    paper_version_id: UUID,
    parsed_checksum: str,
    parser_version: str,
) -> str:
    _validate_checksum(parsed_checksum)
    if not parser_version:
        raise ValueError("Parser version must not be empty.")
    return build_job_idempotency_key(
        stage=stage,
        scope={"paper_id": paper_id, "paper_version_id": paper_version_id},
        inputs={"parsed_checksum": parsed_checksum, "parser_version": parser_version},
    )


def _validate_checksum(checksum: str) -> None:
    if _HEX_DIGEST_PATTERN.fullmatch(checksum) is None:
        raise ValueError("Artifact checksum must be a lowercase SHA-256 digest.")


def validate_requested_identity(
    *,
    idempotency_key: str,
    stage: PipelineStage,
    paper_id: UUID | None,
    paper_version_id: UUID | None,
    pipeline_version: str,
) -> None:
    """Reject malformed keys and incomplete revision scopes."""
    _validate_version(pipeline_version)
    prefix = f"{pipeline_version}:{stage.value}:"
    digest = idempotency_key.removeprefix(prefix)
    if not idempotency_key.startswith(prefix) or _HEX_DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError("Idempotency key does not match its pipeline version and stage.")
    if stage in _REVISION_SCOPED_STAGES:
        if paper_id is None or paper_version_id is None:
            raise ValueError("Revision-scoped pipeline jobs require paper and paper-version IDs.")
    elif paper_id is not None or paper_version_id is not None:
        raise ValueError("Collection-scoped pipeline jobs must not reference a paper revision.")


def validate_stored_identity(
    job: PipelineJob,
    *,
    stage: PipelineStage,
    paper_id: UUID | None,
    paper_version_id: UUID | None,
    pipeline_version: str,
) -> None:
    """Prevent one key from crossing stored job identities."""
    if (
        job.stage != stage
        or job.paper_id != paper_id
        or job.paper_version_id != paper_version_id
        or job.pipeline_version != pipeline_version
    ):
        raise PipelineJobIdentityConflictError

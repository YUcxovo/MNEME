#!/usr/bin/env python3
"""Snapshot settled pipeline identities and immutable seed artifacts."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

from mneme.db.session import Database

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DISPOSABLE_DATABASE_PREFIX = "mneme_eval_"
SETTLED_STATUS = "succeeded"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Wait for a disposable local seed pipeline to settle, then write a "
            "secret-free artifact snapshot."
        )
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument(
        "--phase", choices=("after_first", "after_reuse"), required=True
    )
    parser.add_argument("--wait-seconds", type=float, default=120.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument(
        "--quiet-polls",
        type=int,
        default=3,
        help="consecutive all-succeeded polls required before snapshotting (minimum: 3)",
    )
    return parser.parse_args()


def guarded_environment(pair_id: str) -> dict[str, Any]:
    database_url = os.environ.get("MNEME_DATABASE_URL", "")
    redis_url = os.environ.get("MNEME_REDIS_URL", "")
    queue_name = os.environ.get("MNEME_ARQ_QUEUE_NAME", "")
    storage_dir = Path(os.environ.get("MNEME_PAPER_STORAGE_DIR", ""))
    run_id = os.environ.get("MNEME_EVAL_RUN_ID", "")
    redis_instance_port = os.environ.get("MNEME_EVAL_REDIS_INSTANCE_PORT", "")
    environment = os.environ.get("MNEME_ENVIRONMENT", "")

    parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    database_name = parsed.path.removeprefix("/")
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError("Inspector requires a PostgreSQL database URL.")
    local_unix_socket = parsed.hostname is None and not parsed.netloc
    if parsed.hostname not in LOCAL_HOSTS and not local_unix_socket:
        raise RuntimeError("Inspector refuses a non-local PostgreSQL host.")
    if not database_name.startswith(DISPOSABLE_DATABASE_PREFIX):
        raise RuntimeError(
            "Inspector refuses a database without the mneme_eval_ prefix."
        )
    if environment != "testing":
        raise RuntimeError("Inspector requires MNEME_ENVIRONMENT=testing.")
    if not run_id.startswith(DISPOSABLE_DATABASE_PREFIX):
        raise RuntimeError(
            "Inspector requires a disposable mneme_eval_ run identifier."
        )

    parsed_redis = urlparse(redis_url)
    expected_queue = f"mneme:jobs:eval:{run_id}:{pair_id}"
    if (
        parsed_redis.scheme != "redis"
        or parsed_redis.hostname not in LOCAL_HOSTS
        or parsed_redis.username is not None
        or parsed_redis.password is not None
        or parsed_redis.path not in {"", "/", "/0"}
    ):
        raise RuntimeError(
            "Inspector requires a credential-free dedicated local Redis instance."
        )
    if not redis_instance_port.isdigit() or parsed_redis.port != int(
        redis_instance_port
    ):
        raise RuntimeError(
            "Inspector Redis URL does not match its dedicated instance port."
        )
    if queue_name != expected_queue:
        raise RuntimeError(
            "Inspector queue name does not match the isolated pair identity."
        )

    resolved_storage = storage_dir.expanduser().resolve()
    if not any(
        part.startswith(DISPOSABLE_DATABASE_PREFIX) for part in resolved_storage.parts
    ):
        raise RuntimeError("Inspector refuses storage outside a mneme_eval_ directory.")
    if resolved_storage in {Path("/"), Path.home().resolve()}:
        raise RuntimeError("Inspector refuses an unsafe storage path.")
    if (
        resolved_storage.name != "storage"
        or resolved_storage.parent.name != database_name
    ):
        raise RuntimeError(
            "Inspector storage is not namespaced by the disposable database."
        )
    return {
        "database_url": database_url,
        "database_name": database_name,
        "storage_dir": resolved_storage,
        "storage_identity_sha256": hashlib.sha256(
            str(resolved_storage).encode()
        ).hexdigest(),
        "redis_host": parsed_redis.hostname,
        "redis_port": parsed_redis.port,
        "redis_database": int(parsed_redis.path.removeprefix("/") or "0"),
        "queue_name": queue_name,
    }


async def query_rows(database: Database, statement: str) -> list[dict[str, Any]]:
    async with database.session_factory() as session:
        result = await session.execute(text(statement))
        return [dict(row) for row in result.mappings().all()]


async def read_jobs(database: Database) -> list[dict[str, Any]]:
    return await query_rows(
        database,
        """
        SELECT
            id::text AS id,
            idempotency_key,
            stage::text AS stage,
            status::text AS status,
            attempt_count,
            paper_id::text AS paper_id,
            paper_version_id::text AS paper_version_id
        FROM pipeline_jobs
        ORDER BY idempotency_key, id::text
        """,
    )


async def wait_for_settled_jobs(
    database: Database,
    *,
    wait_seconds: float,
    poll_seconds: float,
    quiet_polls: int,
) -> list[dict[str, Any]]:
    if wait_seconds <= 0 or poll_seconds <= 0 or quiet_polls < 3:
        raise ValueError(
            "Wait and poll values must be positive; quiet-polls must be at least 3."
        )
    deadline = time.monotonic() + wait_seconds
    consecutive_quiet_polls = 0
    previous_fingerprint: tuple[tuple[object, ...], ...] | None = None
    while True:
        jobs = await read_jobs(database)
        status_counts = Counter(str(job["status"]) for job in jobs)
        if status_counts["failed"]:
            raise RuntimeError(
                "A pipeline job failed; the formal run is retained and not retried."
            )
        if jobs and set(status_counts) == {SETTLED_STATUS}:
            fingerprint = tuple(
                (
                    job["id"],
                    job["idempotency_key"],
                    job["stage"],
                    job["status"],
                    job["attempt_count"],
                    job["paper_id"],
                    job["paper_version_id"],
                )
                for job in jobs
            )
            consecutive_quiet_polls = (
                consecutive_quiet_polls + 1
                if fingerprint == previous_fingerprint
                else 1
            )
            previous_fingerprint = fingerprint
            if consecutive_quiet_polls >= quiet_polls:
                return jobs
        else:
            consecutive_quiet_polls = 0
            previous_fingerprint = None
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Pipeline jobs did not reach a non-empty all-succeeded state before timeout."
            )
        await asyncio.sleep(poll_seconds)


async def database_artifact_payload(
    database: Database,
) -> dict[str, list[dict[str, Any]]]:
    papers = await query_rows(
        database,
        """
        SELECT
            id::text AS id,
            arxiv_id,
            processing_status::text AS processing_status
        FROM papers
        ORDER BY id::text
        """,
    )
    versions = await query_rows(
        database,
        """
        SELECT
            id::text AS id,
            paper_id::text AS paper_id,
            version_number,
            source_checksum,
            source_size_bytes,
            parsed_checksum,
            parser_version,
            parse_quality::text AS parse_quality,
            downloaded_at::text AS downloaded_at,
            parsed_at::text AS parsed_at,
            submitted_at::text AS submitted_at,
            created_at::text AS created_at
        FROM paper_versions
        ORDER BY paper_id::text, version_number, id::text
        """,
    )
    summaries = await query_rows(
        database,
        """
        SELECT
            id::text AS id,
            paper_id::text AS paper_id,
            paper_version_id::text AS paper_version_id,
            status::text AS status,
            source_match_status::text AS source_match_status,
            content,
            provider,
            model_snapshot,
            prompt_version,
            input_hash,
            estimated_cost::text AS estimated_cost,
            generation_parameters,
            input_tokens,
            output_tokens,
            latency_ms,
            created_at::text AS created_at
        FROM paper_summaries
        ORDER BY paper_version_id::text, input_hash, id::text
        """,
    )
    chunks = await query_rows(
        database,
        """
        SELECT
            id::text AS id,
            paper_id::text AS paper_id,
            paper_version_id::text AS paper_version_id,
            chunk_index,
            section_title,
            page_start,
            page_end,
            content_hash,
            token_count,
            embedding_model,
            embedding::text AS embedding,
            created_at::text AS created_at
        FROM paper_chunks
        ORDER BY paper_version_id::text, chunk_index, id::text
        """,
    )
    return {
        "papers": papers,
        "paper_versions": versions,
        "paper_summaries": summaries,
        "paper_chunks": chunks,
    }


def storage_payload(storage_dir: Path) -> list[dict[str, Any]]:
    if not storage_dir.is_dir():
        raise RuntimeError("The isolated paper storage directory does not exist.")
    files: list[dict[str, Any]] = []
    for path in sorted(item for item in storage_dir.rglob("*") if item.is_file()):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        files.append(
            {
                "relative_path": path.relative_to(storage_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    if not files:
        raise RuntimeError(
            "The settled seed pipeline produced no stored document artifacts."
        )
    return files


def canonical_checksum(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def paper_artifact_manifest(
    database_artifacts: dict[str, list[dict[str, Any]]],
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for paper in database_artifacts["papers"]:
        paper_id = paper["id"]
        versions = [
            item
            for item in database_artifacts["paper_versions"]
            if item["paper_id"] == paper_id
        ]
        summaries = [
            item
            for item in database_artifacts["paper_summaries"]
            if item["paper_id"] == paper_id
        ]
        chunks = [
            item
            for item in database_artifacts["paper_chunks"]
            if item["paper_id"] == paper_id
        ]
        paper_jobs = [item for item in jobs if item["paper_id"] == paper_id]
        manifest.append(
            {
                "paper_id": paper_id,
                "arxiv_id": paper["arxiv_id"],
                "processing_status": paper["processing_status"],
                "version_ids": [item["id"] for item in versions],
                "version_count": len(versions),
                "summary_count": len(summaries),
                "chunk_count": len(chunks),
                "job_ids": [item["id"] for item in paper_jobs],
                "job_count": len(paper_jobs),
                "artifact_checksum_sha256": canonical_checksum(
                    {
                        "paper": paper,
                        "versions": versions,
                        "summaries": summaries,
                        "chunks": chunks,
                    }
                ),
            }
        )
    return manifest


async def create_snapshot(arguments: argparse.Namespace) -> dict[str, Any]:
    environment = guarded_environment(arguments.pair_id)
    database = Database(environment["database_url"])
    try:
        jobs = await wait_for_settled_jobs(
            database,
            wait_seconds=arguments.wait_seconds,
            poll_seconds=arguments.poll_seconds,
            quiet_polls=arguments.quiet_polls,
        )
        database_artifacts = await database_artifact_payload(database)
    finally:
        await database.dispose()

    storage_artifacts = storage_payload(environment["storage_dir"])
    per_paper_artifacts = paper_artifact_manifest(database_artifacts, jobs)
    artifact_payload = {
        "database_artifacts": database_artifacts,
        "storage_artifacts": storage_artifacts,
    }
    status_counts = Counter(str(job["status"]) for job in jobs)
    return {
        "schema_version": "seed-artifact-reuse-backend-snapshot-v1",
        "run_id": os.environ["MNEME_EVAL_RUN_ID"],
        "pair_id": arguments.pair_id,
        "seed_arxiv_id": arguments.seed,
        "phase": arguments.phase,
        "database_name": environment["database_name"],
        "redis_instance_host": environment["redis_host"],
        "redis_instance_port": environment["redis_port"],
        "redis_database": environment["redis_database"],
        "queue_name": environment["queue_name"],
        "storage_namespace": environment["database_name"],
        "storage_identity_sha256": environment["storage_identity_sha256"],
        "settled_window": {
            "poll_seconds": arguments.poll_seconds,
            "quiet_polls": arguments.quiet_polls,
            "minimum_quiet_seconds": arguments.poll_seconds
            * (arguments.quiet_polls - 1),
            "requires_identical_job_fingerprint": True,
        },
        "job_count": len(jobs),
        "job_status_counts": dict(sorted(status_counts.items())),
        "jobs": jobs,
        "artifact_counts": {
            "paper_versions": len(database_artifacts["paper_versions"]),
            "paper_summaries": len(database_artifacts["paper_summaries"]),
            "paper_chunks": len(database_artifacts["paper_chunks"]),
            "storage_files": len(storage_artifacts),
        },
        "artifact_checksum_sha256": canonical_checksum(artifact_payload),
        "paper_artifacts": per_paper_artifacts,
        "storage_files": storage_artifacts,
        "secrets_retained": False,
    }


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    arguments = parse_arguments()
    snapshot = asyncio.run(create_snapshot(arguments))
    write_snapshot(arguments.output, snapshot)
    print(
        json.dumps(
            {
                "artifact_checksum_sha256": snapshot["artifact_checksum_sha256"],
                "job_count": snapshot["job_count"],
                "output": str(arguments.output),
                "status": "ok",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

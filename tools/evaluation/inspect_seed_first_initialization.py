#!/usr/bin/env python3
"""Capture precondition and five-paper backend evidence for one seed trial."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import text

from mneme.db.session import Database

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
RUN_PREFIX = "mneme_eval_si_"
EXPECTED_PAPER_COUNT = 5
EXPECTED_MEASUREMENT_FIELDS = (
    "schema_version",
    "trial_id",
    "seed_arxiv_id",
    "duration_ms",
    "success",
    "outcome",
    "paper_count",
    "paper_ids",
    "content_origin",
)
FIXED_TRIALS = {
    "trial_01": "1706.03762",
    "trial_02": "2010.11929",
    "trial_03": "2106.09685",
}
EMPTY_DOMAIN_TABLES = (
    "papers",
    "paper_versions",
    "paper_summaries",
    "paper_chunks",
    "pipeline_jobs",
    "digests",
    "digest_entries",
    "citations",
    "authors",
    "paper_authors",
    "user_events",
    "qa_conversations",
    "qa_messages",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect one disposable seed first-initialization backend."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("precondition", "post"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--output", type=Path, required=True)
        subparser.add_argument("--trial-id", required=True)
        subparser.add_argument("--seed", required=True)
    subparsers.choices["post"].add_argument("--measurement", type=Path, required=True)
    return parser


def guarded_environment(trial_id: str) -> dict[str, Any]:
    database_url = os.environ.get("MNEME_DATABASE_URL", "")
    redis_url = os.environ.get("MNEME_REDIS_URL", "")
    queue_name = os.environ.get("MNEME_ARQ_QUEUE_NAME", "")
    storage_dir = Path(os.environ.get("MNEME_PAPER_STORAGE_DIR", ""))
    run_id = os.environ.get("MNEME_EVAL_RUN_ID", "")
    redis_instance_port = os.environ.get("MNEME_EVAL_REDIS_INSTANCE_PORT", "")
    user_id = os.environ.get("MNEME_DEMO_USER_ID", "")
    environment = os.environ.get("MNEME_ENVIRONMENT", "")

    if not run_id.startswith(RUN_PREFIX):
        raise RuntimeError("Inspector requires a disposable seed-initialization run ID.")
    if trial_id not in {"trial_01", "trial_02", "trial_03"}:
        raise RuntimeError("Inspector received an invalid trial ID.")
    expected_database = f"{run_id}_{trial_id}"
    parsed_database = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    database_name = parsed_database.path.removeprefix("/")
    local_unix_socket = parsed_database.hostname is None and not parsed_database.netloc
    if (
        parsed_database.scheme not in {"postgresql", "postgres"}
        or (parsed_database.hostname not in LOCAL_HOSTS and not local_unix_socket)
        or database_name != expected_database
        or parsed_database.query
        or parsed_database.fragment
    ):
        raise RuntimeError("Inspector requires the exact disposable local PostgreSQL database.")

    parsed_redis = urlparse(redis_url)
    expected_queue = f"mneme:jobs:eval:{run_id}:{trial_id}"
    if (
        parsed_redis.scheme != "redis"
        or parsed_redis.hostname not in LOCAL_HOSTS
        or parsed_redis.username is not None
        or parsed_redis.password is not None
        or parsed_redis.path not in {"", "/", "/0"}
        or not redis_instance_port.isdigit()
        or parsed_redis.port != int(redis_instance_port)
        or queue_name != expected_queue
    ):
        raise RuntimeError(
            "Inspector requires the dedicated credential-free Redis instance and queue."
        )

    resolved_storage = storage_dir.expanduser().resolve()
    if (
        resolved_storage.name != "storage"
        or resolved_storage.parent.name != database_name
        or not str(resolved_storage).startswith("/tmp/")
    ):
        raise RuntimeError(
            "Inspector requires temporary storage namespaced by the disposable database."
        )
    if environment != "testing":
        raise RuntimeError("Inspector requires MNEME_ENVIRONMENT=testing.")
    try:
        normalized_user_id = str(UUID(user_id))
    except ValueError as error:
        raise RuntimeError("Inspector requires a valid disposable demo user ID.") from error
    return {
        "database_url": database_url,
        "database_name": database_name,
        "redis_host": parsed_redis.hostname,
        "redis_port": parsed_redis.port,
        "redis_database": int(parsed_redis.path.removeprefix("/") or "0"),
        "redis_url": redis_url,
        "queue_name": queue_name,
        "run_id": run_id,
        "storage_dir": resolved_storage,
        "user_id": normalized_user_id,
    }


async def query_rows(
    database: Database,
    statement: str,
    parameters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    async with database.session_factory() as session:
        result = await session.execute(text(statement), parameters or {})
        return [dict(row) for row in result.mappings().all()]


async def table_counts(database: Database) -> dict[str, int]:
    tables = ("users", "user_preferences", *EMPTY_DOMAIN_TABLES)
    counts: dict[str, int] = {}
    for table in tables:
        rows = await query_rows(
            database,
            f"SELECT count(*)::integer AS row_count FROM {table}",
        )
        counts[table] = int(rows[0]["row_count"])
    return counts


def storage_files(storage_dir: Path) -> list[dict[str, Any]]:
    if not storage_dir.is_dir():
        raise RuntimeError("The disposable storage directory does not exist.")
    result: list[dict[str, Any]] = []
    for path in sorted(item for item in storage_dir.rglob("*") if item.is_file()):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        result.append(
            {
                "relative_path": path.relative_to(storage_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    return result


def read_android_measurement(path: Path, trial_id: str, seed: str) -> tuple[str, ...]:
    if not path.is_file():
        raise FileNotFoundError(f"Android measurement is missing: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_MEASUREMENT_FIELDS:
            raise ValueError("The Android measurement header is not the fixed schema.")
        rows = list(reader)
    if len(rows) != 1:
        raise ValueError("The Android measurement must contain exactly one data row.")
    if FIXED_TRIALS.get(trial_id) != seed:
        raise ValueError("The trial ID and fixed seed do not match.")
    row = rows[0]
    expected = {
        "schema_version": "seed-first-initialization-android-v1",
        "trial_id": trial_id,
        "seed_arxiv_id": seed,
        "success": "true",
        "outcome": "live_five_paper_briefing_visible",
        "paper_count": str(EXPECTED_PAPER_COUNT),
        "content_origin": "LIVE_BACKEND",
    }
    for field, value in expected.items():
        if row.get(field) != value:
            raise ValueError(
                f"Android measurement has {field}={row.get(field)!r}; expected {value!r}."
            )
    duration = float(row.get("duration_ms", ""))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Android measurement duration must be finite and positive.")
    paper_ids = tuple(item for item in row.get("paper_ids", "").split(";") if item)
    if len(paper_ids) != EXPECTED_PAPER_COUNT or len(set(paper_ids)) != len(paper_ids):
        raise ValueError("Android measurement must contain five unique paper IDs.")
    for paper_id in paper_ids:
        UUID(paper_id)
    return paper_ids


def canonical_checksum(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


async def create_precondition(
    arguments: argparse.Namespace, environment: dict[str, Any]
) -> dict[str, Any]:
    database = Database(environment["database_url"])
    try:
        counts = await table_counts(database)
        users = await query_rows(
            database,
            "SELECT id::text AS id FROM users ORDER BY id::text",
        )
        preferences = await query_rows(
            database,
            """
            SELECT user_id::text AS user_id, model_version
            FROM user_preferences
            ORDER BY user_id::text
            """,
        )
    finally:
        await database.dispose()
    redis = Redis.from_url(environment["redis_url"])
    try:
        redis_key_count = int(await redis.dbsize())
    finally:
        await redis.aclose()
    files = storage_files(environment["storage_dir"])
    expected_user = environment["user_id"]
    if counts["users"] != 1 or users != [{"id": expected_user}]:
        raise RuntimeError("Fresh database does not contain exactly the disposable user.")
    if (
        counts["user_preferences"] != 1
        or len(preferences) != 1
        or preferences[0]["user_id"] != expected_user
    ):
        raise RuntimeError(
            "Fresh database does not contain exactly the disposable user's preferences."
        )
    nonempty = {table: counts[table] for table in EMPTY_DOMAIN_TABLES if counts[table] != 0}
    if nonempty:
        raise RuntimeError(f"Fresh database contains experiment state: {nonempty}.")
    if files:
        raise RuntimeError("Fresh disposable storage is not empty.")
    if redis_key_count != 0:
        raise RuntimeError("Fresh dedicated Redis instance is not empty.")
    return {
        "schema_version": "seed-first-initialization-precondition-v1",
        "run_id": environment["run_id"],
        "trial_id": arguments.trial_id,
        "seed_arxiv_id": arguments.seed,
        "database_name": environment["database_name"],
        "redis_instance_host": environment["redis_host"],
        "redis_instance_port": environment["redis_port"],
        "redis_database": environment["redis_database"],
        "queue_name": environment["queue_name"],
        "storage_namespace": environment["database_name"],
        "disposable_user_id": expected_user,
        "database_counts": counts,
        "storage_file_count": 0,
        "redis_key_count": redis_key_count,
        "passed": True,
        "secrets_retained": False,
    }


async def create_post_snapshot(arguments: argparse, environment: dict[str, Any]) -> dict[str, Any]:
    paper_ids = read_android_measurement(arguments.measurement, arguments.trial_id, arguments.seed)
    database = Database(environment["database_url"])
    try:
        seeds = await query_rows(
            database,
            """
            SELECT id::text AS id, arxiv_id
            FROM papers
            WHERE arxiv_id = :seed
            ORDER BY id::text
            """,
            {"seed": arguments.seed},
        )
        digests = await query_rows(
            database,
            """
            SELECT
                d.id::text AS digest_id,
                d.user_id::text AS user_id,
                d.digest_type::text AS digest_type,
                d.generator_version,
                d.generated_at::text AS generated_at,
                de.rank,
                de.paper_id::text AS paper_id,
                de.relevance_score::text AS relevance_score,
                de.recommendation_reason,
                p.arxiv_id,
                p.processing_status::text AS processing_status
            FROM digests AS d
            JOIN digest_entries AS de ON de.digest_id = d.id
            JOIN papers AS p ON p.id = de.paper_id
            ORDER BY d.generated_at, d.id::text, de.rank
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
                parsed_checksum,
                parse_quality::text AS parse_quality
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
                provider,
                model_snapshot,
                prompt_version,
                input_hash
            FROM paper_summaries
            ORDER BY paper_id::text, paper_version_id::text, id::text
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
                content_hash,
                token_count,
                embedding_model
            FROM paper_chunks
            ORDER BY paper_id::text, paper_version_id::text, chunk_index, id::text
            """,
        )
        jobs = await query_rows(
            database,
            """
            SELECT
                id::text AS id,
                paper_id::text AS paper_id,
                paper_version_id::text AS paper_version_id,
                stage::text AS stage,
                status::text AS status,
                attempt_count,
                error_code
            FROM pipeline_jobs
            ORDER BY paper_id::text, paper_version_id::text, stage::text, id::text
            """,
        )
        counts = await table_counts(database)
    finally:
        await database.dispose()

    if len(seeds) != 1 or seeds[0]["arxiv_id"] != arguments.seed:
        raise RuntimeError("The requested seed paper is absent from the fresh backend.")
    digest_ids = {row["digest_id"] for row in digests}
    if len(digest_ids) != 1 or len(digests) != EXPECTED_PAPER_COUNT:
        raise RuntimeError("Fresh backend must contain one five-entry briefing.")
    if any(
        row["user_id"] != environment["user_id"]
        or row["digest_type"] != "manual"
        or row["generator_version"] != "seed-onboarding-v1"
        for row in digests
    ):
        raise RuntimeError("Backend briefing does not belong to the disposable seed user.")
    ordered_backend_ids = tuple(
        row["paper_id"] for row in sorted(digests, key=lambda item: item["rank"])
    )
    if ordered_backend_ids != paper_ids:
        raise RuntimeError("The ordered five-paper backend briefing does not match the visible UI.")

    def scoped(rows: list[dict[str, Any]], paper_id: str) -> list[dict[str, Any]]:
        return [row for row in rows if row.get("paper_id") == paper_id]

    all_files = storage_files(environment["storage_dir"])
    ui_papers: list[dict[str, Any]] = []
    for digest_row in sorted(digests, key=lambda item: item["rank"]):
        paper_id = digest_row["paper_id"]
        paper_versions = scoped(versions, paper_id)
        paper_summaries = scoped(summaries, paper_id)
        paper_chunks = scoped(chunks, paper_id)
        paper_jobs = scoped(jobs, paper_id)
        paper_files = [
            item
            for item in all_files
            if Path(item["relative_path"]).parts
            and Path(item["relative_path"]).parts[0] == paper_id
        ]
        ui_papers.append(
            {
                **digest_row,
                "versions": paper_versions,
                "summaries": paper_summaries,
                "chunk_count": len(paper_chunks),
                "chunk_identity_sha256": canonical_checksum(paper_chunks),
                "jobs": paper_jobs,
                "job_status_counts": dict(
                    sorted(Counter(str(item["status"]) for item in paper_jobs).items())
                ),
                "storage_files": paper_files,
            }
        )
    ui_file_paths = {
        item["relative_path"] for paper in ui_papers for item in paper["storage_files"]
    }
    payload = {
        "digest_id": next(iter(digest_ids)),
        "ordered_ui_paper_ids": list(paper_ids),
        "ui_papers": ui_papers,
    }
    return {
        "schema_version": "seed-first-initialization-backend-snapshot-v1",
        "run_id": environment["run_id"],
        "trial_id": arguments.trial_id,
        "seed_arxiv_id": arguments.seed,
        "database_name": environment["database_name"],
        "redis_instance_host": environment["redis_host"],
        "redis_instance_port": environment["redis_port"],
        "redis_database": environment["redis_database"],
        "queue_name": environment["queue_name"],
        "storage_namespace": environment["database_name"],
        "disposable_user_id": environment["user_id"],
        "paper_count": len(paper_ids),
        "ordered_ui_paper_ids": list(paper_ids),
        "digest_id": payload["digest_id"],
        "ui_papers": ui_papers,
        "database_counts": counts,
        "storage_total_file_count": len(all_files),
        "ui_paper_storage_file_count": len(ui_file_paths),
        "non_ui_storage_file_count": len(all_files) - len(ui_file_paths),
        "backend_snapshot_sha256": canonical_checksum(payload),
        "secrets_retained": False,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


async def run(arguments: argparse.Namespace) -> dict[str, Any]:
    if FIXED_TRIALS.get(arguments.trial_id) != arguments.seed:
        raise RuntimeError("The trial ID and fixed seed do not match.")
    environment = guarded_environment(arguments.trial_id)
    if arguments.command == "precondition":
        return await create_precondition(arguments, environment)
    return await create_post_snapshot(arguments, environment)


def main() -> None:
    arguments = build_parser().parse_args()
    payload = asyncio.run(run(arguments))
    write_json(arguments.output, payload)
    print(
        json.dumps(
            {
                "command": arguments.command,
                "output": str(arguments.output),
                "status": "ok",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

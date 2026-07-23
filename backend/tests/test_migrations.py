"""Tests for the v0.1 Alembic migration chain."""

import os
import re
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]


EXPECTED_TABLES = {
    "authors",
    "citations",
    "digest_entries",
    "digests",
    "paper_authors",
    "paper_chunks",
    "paper_summaries",
    "paper_versions",
    "papers",
    "pipeline_jobs",
    "qa_conversations",
    "qa_messages",
    "user_events",
    "user_preferences",
    "users",
}


def alembic_config(*, output_buffer: StringIO | None = None) -> Config:
    """Load the repository's Alembic configuration."""
    return Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output_buffer)


def render_upgrade_sql() -> str:
    """Render the complete upgrade chain without connecting to PostgreSQL."""
    output = StringIO()
    command.upgrade(alembic_config(output_buffer=output), "head", sql=True)
    return output.getvalue()


def render_downgrade_sql() -> str:
    """Render the complete downgrade chain without connecting to PostgreSQL."""
    output = StringIO()
    command.downgrade(alembic_config(output_buffer=output), "head:base", sql=True)
    return output.getvalue()


@pytest.mark.base
@pytest.mark.db
def test_alembic_script_directory_is_configured() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    assert Path(script.dir).resolve() == BACKEND_ROOT / "alembic"
    assert Path(script.versions).resolve() == BACKEND_ROOT / "alembic" / "versions"
    assert script.get_current_head() == "0006"


@pytest.mark.base
@pytest.mark.db
def test_migration_chain_renders_offline() -> None:
    sql = render_upgrade_sql()

    rendered_tables = set(re.findall(r"CREATE TABLE (\w+)", sql))
    assert rendered_tables - {"alembic_version"} == EXPECTED_TABLES

    extension_position = sql.index("CREATE EXTENSION IF NOT EXISTS vector")
    first_vector_table_position = sql.index("CREATE TABLE user_preferences")
    assert extension_position < first_vector_table_position
    assert sql.count("VECTOR(1536)") == 2
    assert "ADD COLUMN parsed_checksum VARCHAR(64)" in sql
    assert "ADD COLUMN paper_version_id UUID" in sql
    assert "ADD COLUMN dispatched_at TIMESTAMP WITH TIME ZONE" in sql
    assert "ADD COLUMN semantic_scholar_id VARCHAR(128)" in sql
    assert "ADD COLUMN external_source_id VARCHAR(200)" in sql
    assert "CREATE INDEX ix_citations_external_target_id" in sql
    assert "ck_citations_has_local_endpoint" in sql
    assert sql.index("UPDATE citations SET external_target_id = NULL") < sql.index(
        "ck_citations_one_target"
    )
    assert "fk_pipeline_jobs_version_paper" in sql


@pytest.mark.base
@pytest.mark.db
def test_downgrade_renders_in_reverse_order_and_keeps_vector_extension() -> None:
    sql = render_downgrade_sql()

    rendered_tables = set(re.findall(r"DROP TABLE (\w+)", sql))
    assert rendered_tables - {"alembic_version"} == EXPECTED_TABLES
    assert sql.index("DROP TABLE qa_messages") < sql.index("DROP TABLE authors")
    assert "DROP INDEX ix_citations_external_target_id" in sql
    assert "DROP EXTENSION" not in sql


@pytest.mark.db
def test_live_upgrade_downgrade_upgrade_cycle() -> None:
    if os.getenv("MNEME_DATABASE_URL") is None:
        pytest.skip("MNEME_DATABASE_URL is not configured for an integration test")

    config = alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

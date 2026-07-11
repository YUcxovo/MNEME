"""Tests for the Alembic migration scaffold."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    """Load the repository's Alembic configuration."""
    return Config(BACKEND_ROOT / "alembic.ini")


@pytest.mark.base
@pytest.mark.db
def test_alembic_script_directory_is_configured() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    assert Path(script.dir).resolve() == BACKEND_ROOT / "alembic"
    assert Path(script.versions).resolve() == BACKEND_ROOT / "alembic" / "versions"


@pytest.mark.base
@pytest.mark.db
def test_migration_chain_renders_offline() -> None:
    command.upgrade(alembic_config(), "head", sql=True)

"""Shared document contracts and atomic local storage."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from mneme.models.paper import ParseQuality
from mneme.services.documents import DocumentStorage, ParsedDocument, ParsedSection
from mneme.services.documents import storage as storage_module

PAPER_ID = UUID("11111111-1111-4111-8111-111111111111")
VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")
SOURCE_CHECKSUM = "a" * 64


def _document() -> ParsedDocument:
    return ParsedDocument(
        parser_version="parser-v1",
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        source_checksum=SOURCE_CHECKSUM,
        parse_quality=ParseQuality.STRUCTURED,
        page_count=2,
        sections=[
            ParsedSection(
                title="Introduction",
                text="A compact parsed section.",
                page_start=1,
                page_end=2,
            )
        ],
        parsed_at=datetime(2026, 7, 21, tzinfo=UTC),
    )


@pytest.mark.base
@pytest.mark.pipeline
def test_paths_use_only_versioned_uuid_components(tmp_path: Path) -> None:
    storage = DocumentStorage(tmp_path / "papers")

    paths = storage.paths_for(PAPER_ID, VERSION_ID)

    assert paths.directory == storage.root / str(PAPER_ID) / str(VERSION_ID)
    assert paths.source_pdf == paths.directory / "source.pdf"
    assert paths.parsed_json == paths.directory / "parsed.json"
    assert paths.directory.is_relative_to(storage.root)


@pytest.mark.base
@pytest.mark.pipeline
def test_source_and_parsed_artifacts_round_trip(tmp_path: Path) -> None:
    storage = DocumentStorage(tmp_path / "papers")
    source = b"%PDF-1.7\nsmall fixture\n"

    stored_source = storage.write_source_pdf(PAPER_ID, VERSION_ID, source)
    stored_document = storage.write_parsed_document(PAPER_ID, VERSION_ID, _document())

    assert storage.read_source_pdf(PAPER_ID, VERSION_ID) == source
    assert stored_source.path.name == "source.pdf"
    assert stored_source.byte_size == len(source)
    assert len(stored_source.checksum) == 64
    assert storage.read_parsed_document(PAPER_ID, VERSION_ID) == _document()
    assert stored_document.path.name == "parsed.json"
    assert stored_document.byte_size > 0
    assert len(stored_document.checksum) == 64


@pytest.mark.base
@pytest.mark.pipeline
def test_failed_replace_preserves_existing_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = DocumentStorage(tmp_path / "papers")
    storage.write_source_pdf(PAPER_ID, VERSION_ID, b"old")

    def fail_replace(source: os.PathLike[str], destination: os.PathLike[str]) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(storage_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        storage.write_source_pdf(PAPER_ID, VERSION_ID, b"new")

    paths = storage.paths_for(PAPER_ID, VERSION_ID)
    assert paths.source_pdf.read_bytes() == b"old"
    assert list(paths.directory.glob("*.tmp")) == []
    assert list(paths.directory.glob(".*.tmp")) == []

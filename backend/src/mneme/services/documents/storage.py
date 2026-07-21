"""Atomic local storage for versioned paper document artifacts."""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from mneme.services.documents.types import ParsedDocument


@dataclass(frozen=True, slots=True)
class DocumentPaths:
    """Deterministic artifact paths for one observed paper revision."""

    directory: Path
    source_pdf: Path
    parsed_json: Path


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """Metadata returned after an artifact is installed atomically."""

    path: Path
    checksum: str
    byte_size: int


class DocumentStorage:
    """Store each paper revision below UUID-only directory components."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve(strict=False)

    @property
    def root(self) -> Path:
        """Return the normalized document storage root."""
        return self._root

    def paths_for(self, paper_id: UUID, paper_version_id: UUID) -> DocumentPaths:
        """Return deterministic paths for one paper revision."""
        directory = self._root / str(paper_id) / str(paper_version_id)
        return DocumentPaths(
            directory=directory,
            source_pdf=directory / "source.pdf",
            parsed_json=directory / "parsed.json",
        )

    def write_source_pdf(
        self, paper_id: UUID, paper_version_id: UUID, content: bytes
    ) -> StoredArtifact:
        """Atomically write source PDF bytes for one paper revision."""
        return self._atomic_write(self.paths_for(paper_id, paper_version_id).source_pdf, content)

    def read_source_pdf(self, paper_id: UUID, paper_version_id: UUID) -> bytes:
        """Read the persisted source PDF bytes."""
        return self.paths_for(paper_id, paper_version_id).source_pdf.read_bytes()

    def write_parsed_document(
        self,
        paper_id: UUID,
        paper_version_id: UUID,
        document: ParsedDocument,
    ) -> StoredArtifact:
        """Serialize and atomically persist validated parser output."""
        content = (document.model_dump_json(indent=2) + "\n").encode()
        return self._atomic_write(self.paths_for(paper_id, paper_version_id).parsed_json, content)

    def read_parsed_document(self, paper_id: UUID, paper_version_id: UUID) -> ParsedDocument:
        """Load and validate persisted parser output."""
        content = self.paths_for(paper_id, paper_version_id).parsed_json.read_bytes()
        return ParsedDocument.model_validate_json(content)

    @staticmethod
    def _atomic_write(target: Path, content: bytes) -> StoredArtifact:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, target)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

        return StoredArtifact(
            path=target,
            checksum=hashlib.sha256(content).hexdigest(),
            byte_size=len(content),
        )

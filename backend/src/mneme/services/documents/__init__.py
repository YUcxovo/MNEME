"""Shared parsed-document contracts and local artifact storage."""

from mneme.services.documents.downloader import PdfDownloader
from mneme.services.documents.pdf_transport import (
    PdfDownloadError,
    PdfDownloadResult,
    versioned_pdf_url,
)
from mneme.services.documents.storage import DocumentPaths, DocumentStorage, StoredArtifact
from mneme.services.documents.types import ParsedDocument, ParsedSection

__all__ = [
    "DocumentPaths",
    "DocumentStorage",
    "ParsedDocument",
    "ParsedSection",
    "PdfDownloadError",
    "PdfDownloadResult",
    "PdfDownloader",
    "StoredArtifact",
    "versioned_pdf_url",
]

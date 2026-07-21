"""Shared parsed-document contracts and local artifact storage."""

from mneme.services.documents.downloader import PdfDownloader
from mneme.services.documents.parser import PARSER_VERSION, PdfParseError, PdfParser
from mneme.services.documents.pdf_transport import (
    PdfDownloadError,
    PdfDownloadResult,
    versioned_pdf_url,
)
from mneme.services.documents.storage import DocumentPaths, DocumentStorage, StoredArtifact
from mneme.services.documents.types import ParsedDocument, ParsedSection

__all__ = [
    "PARSER_VERSION",
    "DocumentPaths",
    "DocumentStorage",
    "ParsedDocument",
    "ParsedSection",
    "PdfDownloadError",
    "PdfDownloadResult",
    "PdfDownloader",
    "PdfParseError",
    "PdfParser",
    "StoredArtifact",
    "versioned_pdf_url",
]

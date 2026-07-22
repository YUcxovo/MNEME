"""Focused tests for local-demo seed reference handling."""

import pytest

from mneme.api.routes.onboarding_support import normalize_arxiv_reference


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("2607.01234", "2607.01234"),
        ("2607.01234v2", "2607.01234"),
        ("https://arxiv.org/abs/2607.01234v3", "2607.01234"),
        ("https://arxiv.org/pdf/2607.01234v3.pdf", "2607.01234"),
        ("https://export.arxiv.org/abs/hep-th/9901001", "hep-th/9901001"),
    ],
)
def test_normalize_arxiv_reference(reference: str, expected: str) -> None:
    assert normalize_arxiv_reference(reference) == expected


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "not-an-id",
        "https://example.com/abs/2607.01234",
        "https://arxiv.org/search/?query=agents",
    ],
)
def test_invalid_arxiv_reference_is_rejected(reference: str) -> None:
    with pytest.raises(ValueError):
        normalize_arxiv_reference(reference)

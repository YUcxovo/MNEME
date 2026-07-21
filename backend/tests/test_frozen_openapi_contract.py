"""Regression checks against the committed v0.1 OpenAPI contract."""

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from mneme.main import app

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "docs/api/openapi-v0.1.yaml"
IMPLEMENTED_OPERATIONS = (
    ("/health", "get"),
    ("/papers", "get"),
    ("/papers/{paper_id}", "get"),
    ("/papers/{paper_id}/summary", "get"),
    ("/users/me/preferences", "get"),
    ("/users/me/preferences", "put"),
    ("/digests", "get"),
    ("/digests/recommended", "post"),
    ("/qa/ask", "post"),
    ("/jobs/{job_id}", "get"),
)


def _load_contract() -> dict[str, Any]:
    loaded = yaml.safe_load(CONTRACT_PATH.read_text())
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


@pytest.mark.base
@pytest.mark.api
def test_implemented_operations_preserve_frozen_responses() -> None:
    frozen = _load_contract()
    generated = app.openapi()

    for path, method in IMPLEMENTED_OPERATIONS:
        frozen_operation = frozen["paths"][path][method]
        generated_operation = generated["paths"][f"/v1{path}"][method]

        assert generated_operation["operationId"] == frozen_operation["operationId"]
        for status_code, frozen_response in frozen_operation["responses"].items():
            generated_response = generated_operation["responses"][status_code]
            if "content" in frozen_response:
                assert (
                    generated_response["content"]["application/json"]["schema"]
                    == (frozen_response["content"]["application/json"]["schema"])
                )

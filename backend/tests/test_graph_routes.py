"""Contract tests for the public paper citation graph endpoint."""

import asyncio
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient, Response

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.graph import (
    get_graph_preparation_service,
    get_graph_service,
    get_graph_settings,
)
from mneme.api.errors import register_error_handlers
from mneme.api.middleware import request_context_middleware
from mneme.api.routes.graphs import router as graphs_router
from mneme.core.config import Settings
from mneme.graph.algorithms import GraphEdge, GraphNode, GraphView
from mneme.services.graph import GraphAlgorithmStatus, GraphResult
from mneme.services.graph_preparation import GraphPreparationResult

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
PAPER_ID = UUID("00000000-0000-0000-0000-000000000001")
NEIGHBOR_ID = UUID("00000000-0000-0000-0000-000000000002")


class FakeGraphService:
    def __init__(self, result: GraphResult | None) -> None:
        self.result = result
        self.calls: list[tuple[UUID, int, int]] = []

    async def get_graph(self, paper_id: UUID, *, depth: int, limit: int) -> GraphResult | None:
        self.calls.append((paper_id, depth, limit))
        return self.result


class FakeGraphPreparationService:
    def __init__(self, *, found: bool = True) -> None:
        self.found = found
        self.calls: list[tuple[UUID, int]] = []

    async def prepare(
        self,
        paper_id: UUID,
        *,
        neighbor_limit: int,
    ) -> GraphPreparationResult | None:
        self.calls.append((paper_id, neighbor_limit))
        if not self.found:
            return None
        return GraphPreparationResult(
            paper_id=paper_id,
            evidence_source="none",
            cached=False,
            resolved_neighbors=0,
        )


def _application(service: FakeGraphService) -> FastAPI:
    async def principal_override() -> Principal:
        return Principal(user_id=USER_ID)

    async def service_override() -> FakeGraphService:
        return service

    application = FastAPI()
    application.middleware("http")(request_context_middleware)
    register_error_handlers(application)
    application.include_router(graphs_router, prefix="/v1")
    application.dependency_overrides[require_principal] = principal_override
    application.dependency_overrides[get_graph_service] = service_override
    return application


def _preparation_application(
    service: FakeGraphService,
    preparation: FakeGraphPreparationService,
) -> FastAPI:
    application = _application(service)

    async def preparation_override() -> FakeGraphPreparationService:
        return preparation

    application.dependency_overrides[get_graph_preparation_service] = preparation_override
    return application


async def _get(application: FastAPI, path: str) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers={"X-Request-ID": "graph-test"})


async def _post(application: FastAPI, path: str) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, headers={"X-Request-ID": "graph-test"})


def _result(*, status: GraphAlgorithmStatus = "ready") -> GraphResult:
    return GraphResult(
        view=GraphView(
            center_id=PAPER_ID,
            nodes=(
                GraphNode(
                    id=PAPER_ID,
                    title="Center paper",
                    category="cs.AI",
                    cluster_id="cluster-1",
                    rank_score=1,
                ),
                GraphNode(id=NEIGHBOR_ID, title="Neighbor paper"),
            ),
            edges=(GraphEdge(source=PAPER_ID, target=NEIGHBOR_ID, weight=0.5),),
        ),
        algorithm_status=status,
        graph_version="citation-graph-v1",
    )


@pytest.mark.base
@pytest.mark.api
def test_graph_endpoint_returns_bounded_view() -> None:
    service = FakeGraphService(_result())

    response = asyncio.run(_get(_application(service), f"/v1/graph/{PAPER_ID}?depth=2&limit=10"))

    assert response.status_code == 200
    assert service.calls == [(PAPER_ID, 2, 10)]
    assert response.json() == {
        "center_id": str(PAPER_ID),
        "nodes": [
            {
                "id": str(PAPER_ID),
                "title": "Center paper",
                "category": "cs.AI",
                "cluster_id": "cluster-1",
                "rank_score": 1.0,
            },
            {
                "id": str(NEIGHBOR_ID),
                "title": "Neighbor paper",
                "category": None,
                "cluster_id": None,
                "rank_score": None,
            },
        ],
        "edges": [{"source": str(PAPER_ID), "target": str(NEIGHBOR_ID), "weight": 0.5}],
        "algorithm_status": "ready",
        "graph_version": "citation-graph-v1",
    }


@pytest.mark.base
@pytest.mark.api
def test_graph_settings_come_from_the_request_application() -> None:
    application = FastAPI()
    configured = Settings(_env_file=None, app_name="Graph test application")
    application.state.settings = configured
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/graph/test",
            "headers": [],
            "app": application,
        }
    )

    assert get_graph_settings(request) is configured


@pytest.mark.base
@pytest.mark.api
def test_graph_endpoint_returns_stable_missing_paper_error() -> None:
    response = asyncio.run(_get(_application(FakeGraphService(None)), f"/v1/graph/{PAPER_ID}"))

    assert response.status_code == 404
    assert response.json() == {
        "code": "paper_not_found",
        "message": "The requested paper does not exist.",
        "request_id": "graph-test",
    }


@pytest.mark.base
@pytest.mark.api
def test_prepare_endpoint_prepares_then_returns_the_standard_graph() -> None:
    service = FakeGraphService(_result())
    preparation = FakeGraphPreparationService()
    response = asyncio.run(
        _post(
            _preparation_application(service, preparation),
            f"/v1/graph/{PAPER_ID}/prepare?depth=2&limit=10",
        )
    )

    assert response.status_code == 200
    assert preparation.calls == [(PAPER_ID, 20)]
    assert service.calls == [(PAPER_ID, 2, 10)]
    assert response.json()["center_id"] == str(PAPER_ID)
    assert len(response.json()["nodes"]) == 2


@pytest.mark.base
@pytest.mark.api
def test_prepare_endpoint_returns_missing_without_reading_a_graph() -> None:
    service = FakeGraphService(_result())
    preparation = FakeGraphPreparationService(found=False)
    response = asyncio.run(
        _post(
            _preparation_application(service, preparation),
            f"/v1/graph/{PAPER_ID}/prepare",
        )
    )

    assert response.status_code == 404
    assert response.json()["code"] == "paper_not_found"
    assert service.calls == []


@pytest.mark.base
@pytest.mark.api
@pytest.mark.parametrize("query", ["depth=0", "depth=3", "limit=0", "limit=201"])
def test_graph_endpoint_rejects_out_of_bounds_queries(query: str) -> None:
    service = FakeGraphService(_result())

    response = asyncio.run(_get(_application(service), f"/v1/graph/{PAPER_ID}?{query}"))

    assert response.status_code == 422
    assert service.calls == []


@pytest.mark.base
@pytest.mark.api
def test_graph_openapi_matches_frozen_contract() -> None:
    schema = _application(FakeGraphService(_result())).openapi()
    operation = schema["paths"]["/v1/graph/{paper_id}"]["get"]

    assert operation["operationId"] == "getPaperGraph"
    assert [parameter["name"] for parameter in operation["parameters"]] == [
        "paper_id",
        "depth",
        "limit",
    ]
    assert operation["security"] == [{"demoToken": []}]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Graph"
    }

    prepare_operation = schema["paths"]["/v1/graph/{paper_id}/prepare"]["post"]
    assert prepare_operation["operationId"] == "preparePaperGraph"
    assert [parameter["name"] for parameter in prepare_operation["parameters"]] == [
        "paper_id",
        "depth",
        "limit",
    ]
    assert prepare_operation["security"] == [{"demoToken": []}]
    assert prepare_operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Graph"
    }

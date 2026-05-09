"""Интеграционные тесты для bot.api через aiohttp test client.

Покрывают: health, scenarios index/detail, aed, dispatcher, panic,
OpenAPI и CORS preflight.
"""

from __future__ import annotations

import pytest

aiohttp_pytest_plugin = pytest.importorskip("aiohttp.pytest_plugin")

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from bot.api import build_api  # noqa: E402


@pytest.fixture
async def client() -> TestClient:
    app = build_api()
    async with TestClient(TestServer(app)) as c:
        yield c


@pytest.mark.asyncio
async def test_health_ok(client: TestClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status == 200
    body = await resp.json()
    assert body["ok"] is True


@pytest.mark.asyncio
async def test_scenarios_list_returns_array(client: TestClient) -> None:
    resp = await client.get("/api/scenarios")
    assert resp.status == 200
    body = await resp.json()
    assert isinstance(body, dict)
    assert isinstance(body["scenarios"], list)
    assert body["scenarios"], "scenarios.json должен содержать хотя бы один сценарий"
    assert body["total"] == len(body["scenarios"])
    assert "id" in body["scenarios"][0]


@pytest.mark.asyncio
async def test_scenario_detail_404_on_unknown(client: TestClient) -> None:
    resp = await client.get("/api/scenarios/no_such_id_42")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_scenario_detail_for_existing(client: TestClient) -> None:
    list_resp = await client.get("/api/scenarios")
    first_id = (await list_resp.json())["scenarios"][0]["id"]
    resp = await client.get(f"/api/scenarios/{first_id}")
    assert resp.status == 200
    body = await resp.json()
    assert body["id"] == first_id


@pytest.mark.asyncio
async def test_aed_endpoint(client: TestClient) -> None:
    resp = await client.get("/api/aed")
    assert resp.status == 200
    body = await resp.json()
    assert isinstance(body, dict)
    assert isinstance(body["locations"], list)


@pytest.mark.asyncio
async def test_dispatcher_endpoint(client: TestClient) -> None:
    resp = await client.get("/api/dispatcher")
    assert resp.status == 200
    body = await resp.json()
    assert "questions" in body or "intro" in body


@pytest.mark.asyncio
async def test_panic_endpoint(client: TestClient) -> None:
    resp = await client.get("/api/panic")
    assert resp.status == 200
    body = await resp.json()
    assert "intro" in body or "breathing" in body


@pytest.mark.asyncio
async def test_openapi_doc(client: TestClient) -> None:
    resp = await client.get("/api/openapi.json")
    assert resp.status == 200
    body = await resp.json()
    assert body.get("openapi", "").startswith("3.")
    assert "/api/scenarios" in body.get("paths", {})


@pytest.mark.asyncio
async def test_cors_preflight(client: TestClient) -> None:
    resp = await client.options("/api/scenarios")
    assert resp.status in (200, 204)
    assert resp.headers.get("Access-Control-Allow-Origin")


@pytest.mark.asyncio
async def test_cors_header_on_get(client: TestClient) -> None:
    resp = await client.get("/api/scenarios")
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"

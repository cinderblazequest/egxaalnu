"""Тест OpenAPI 3.0 спецификации (H7)."""

from __future__ import annotations

from bot.api import build_openapi_spec


def test_openapi_basic_shape() -> None:
    spec = build_openapi_spec()
    assert spec["openapi"].startswith("3.0")
    assert "info" in spec
    assert spec["info"]["title"]
    assert "paths" in spec
    assert "/api/health" in spec["paths"]
    assert "/api/scenarios" in spec["paths"]
    assert "/api/scenarios/{scenario_id}" in spec["paths"]
    assert "/api/openapi.json" in spec["paths"]


def test_openapi_health_response_schema_ref() -> None:
    spec = build_openapi_spec()
    health = spec["paths"]["/api/health"]["get"]
    schema = health["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/Health"
    health_schema = spec["components"]["schemas"]["Health"]
    assert "ok" in health_schema["properties"]
    assert "version" in health_schema["properties"]

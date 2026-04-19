"""测试 GET /health 健康检查端点。"""

from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body_has_status_ok(client: TestClient) -> None:
    response = client.get("/health")
    body = response.json()
    assert body["status"] == "ok"


def test_health_body_has_checks(client: TestClient) -> None:
    response = client.get("/health")
    body = response.json()
    assert "checks" in body
    checks = body["checks"]
    assert checks["llm"] == "skipped"
    assert checks["milvus"] == "skipped"
    assert checks["postgres"] == "skipped"


def test_health_body_has_version(client: TestClient) -> None:
    response = client.get("/health")
    body = response.json()
    assert "version" in body

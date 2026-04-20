"""测试 POST /api/v1/agent/jd-routing stub 接口。"""

from fastapi.testclient import TestClient

_VALID_JD = (
    "我们正在招聘一名后端工程师，要求熟悉 Python 和 TypeScript，"
    "有分布式系统经验，负责核心服务研发与架构演进，具备良好的团队协作能力。"
)

_REQUEST_BODY = {
    "request_id": "test-req-001",
    "user_id": "test-user-001",
    "jd_text": _VALID_JD,
}


def test_jd_routing_returns_200(client: TestClient) -> None:
    response = client.post("/api/v1/agent/jd-routing", json=_REQUEST_BODY)
    assert response.status_code == 200


def test_jd_routing_response_has_request_id(client: TestClient) -> None:
    response = client.post("/api/v1/agent/jd-routing", json=_REQUEST_BODY)
    body = response.json()
    assert body["request_id"] == "test-req-001"


def test_jd_routing_response_has_classification(client: TestClient) -> None:
    response = client.post("/api/v1/agent/jd-routing", json=_REQUEST_BODY)
    body = response.json()
    classification = body["classification"]
    assert "job_type" in classification
    assert "level" in classification


def test_jd_routing_response_has_results(client: TestClient) -> None:
    response = client.post("/api/v1/agent/jd-routing", json=_REQUEST_BODY)
    body = response.json()
    results = body["results"]
    assert "jd_summary" in results
    assert isinstance(results["resume_advice"], list)
    assert isinstance(results["interview_questions"], list)


def test_jd_routing_response_has_metadata(client: TestClient) -> None:
    response = client.post("/api/v1/agent/jd-routing", json=_REQUEST_BODY)
    body = response.json()
    assert "metadata" in body
    assert body["metadata"]["latency_ms"] >= 0


def test_jd_routing_invalid_short_jd_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agent/jd-routing",
        json={**_REQUEST_BODY, "jd_text": "too short"},
    )
    assert response.status_code == 422


def test_jd_routing_response_header_has_request_id(client: TestClient) -> None:
    response = client.post("/api/v1/agent/jd-routing", json=_REQUEST_BODY)
    assert "x-request-id" in response.headers

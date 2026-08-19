from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from explanation.provider import ProviderRateLimited, ProviderUnavailable
from main import app
from storage import memory
from storage.memory import create_session


client = TestClient(app)


def make_session():
    graph = {
        "nodes": [
            {
                "id": "selected",
                "name": "selected",
                "symbol_type": "function",
                "language": "python",
                "file_path": "main.py",
                "start_line": 1,
                "end_line": 3,
                "start_column": 0,
                "end_column": 1,
                "parent_id": None,
                "node_type": "symbol",
            }
        ],
        "edges": [],
    }
    return create_session(graph, {"main.py": "def selected():\n    return 1\n"})


def test_successful_explanations_return_grounded_response(monkeypatch):
    analysis_id = make_session()
    captured = []

    def provider(system_prompt, user_prompt):
        captured.append((system_prompt, user_prompt))
        return "The selected function returns 1."

    monkeypatch.setattr("explanation.service.complete", provider)
    for action in ("explain", "how_it_works", "impact"):
        response = client.post("/api/explain", json={"analysis_id": analysis_id, "symbol_id": "selected", "action": action})
        assert response.status_code == 200
        payload = response.json()
        assert payload["answer"] == "The selected function returns 1."
        assert payload["context"]["symbol"]["name"] == "selected"
        assert payload["context"]["file"] == "main.py"
        assert payload["context"]["relationships_used"] == 0
    assert len(captured) == 3
    assert "Use only the supplied context" in captured[0][0]
    assert "selected" in captured[0][1]


def test_invalid_analysis_symbol_and_action_are_rejected():
    assert client.post("/api/explain", json={"analysis_id": "missing", "symbol_id": "selected", "action": "explain"}).status_code == 404
    analysis_id = make_session()
    assert client.post("/api/explain", json={"analysis_id": analysis_id, "symbol_id": "missing", "action": "explain"}).status_code == 404
    assert client.post("/api/explain", json={"analysis_id": analysis_id, "symbol_id": "selected", "action": "chat"}).status_code == 422


def test_missing_configuration_and_provider_failure_are_safe(monkeypatch):
    analysis_id = make_session()
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    response = client.post("/api/explain", json={"analysis_id": analysis_id, "symbol_id": "selected", "action": "explain"})
    assert response.status_code == 503
    assert "API" not in response.text

    def fail(system_prompt, user_prompt):
        raise ProviderUnavailable("secret provider payload")

    monkeypatch.setattr("explanation.service.complete", fail)
    response = client.post("/api/explain", json={"analysis_id": analysis_id, "symbol_id": "selected", "action": "explain"})
    assert response.status_code == 502
    assert "secret provider payload" not in response.text

    def rate_limited(system_prompt, user_prompt):
        raise ProviderRateLimited("7")

    monkeypatch.setattr("explanation.service.complete", rate_limited)
    response = client.post("/api/explain", json={"analysis_id": analysis_id, "symbol_id": "selected", "action": "explain"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"
    assert response.json()["detail"] == "AI provider rate limit reached; retry after 7 seconds"


def test_expired_analysis_is_rejected():
    analysis_id = make_session()
    session = memory.get_session(analysis_id)
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    response = client.post("/api/explain", json={"analysis_id": analysis_id, "symbol_id": "selected", "action": "explain"})
    assert response.status_code == 404


def teardown_function():
    memory.clear_sessions()

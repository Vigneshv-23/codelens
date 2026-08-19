from datetime import datetime, timedelta, timezone
from io import BytesIO
import zipfile

from fastapi.testclient import TestClient

from main import app
from routes import analysis
from storage import memory


client = TestClient(app)


def zip_bytes(files):
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def post_zip(files):
    return client.post(
        "/api/analyze",
        files={"file": ("repository.zip", zip_bytes(files), "application/zip")},
    )


def function_node(payload):
    return next(node for node in payload["nodes"] if node["name"] == "getSlotState")


def test_valid_symbol_source_request_returns_exact_source_and_metadata():
    source = "const before = true;\nfunction getSlotState() {\n  return before;\n}\n"
    response = post_zip({"background.js": source})
    node = function_node(response.json())

    source_response = client.get(f"/api/source/{response.headers['X-Analysis-ID']}/{node['id']}")

    assert source_response.status_code == 200
    assert source_response.json() == {
        "symbol": {
            "id": node["id"],
            "name": "getSlotState",
            "type": "function",
            "language": "javascript",
            "file": "background.js",
            "start_line": 2,
            "end_line": 4,
            "start_column": 0,
            "end_column": 1,
        },
        "source": source,
        "start_line": 1,
    }


def test_invalid_analysis_and_symbol_ids_are_rejected():
    assert client.get("/api/source/missing/symbol").status_code == 404
    response = post_zip({"main.py": "def answer():\n    return 42\n"})
    assert client.get(f"/api/source/{response.headers['X-Analysis-ID']}/missing").status_code == 404


def test_symbol_from_another_analysis_is_rejected():
    first = post_zip({"one.py": "def one():\n    return 1\n"})
    second = post_zip({"two.py": "def two():\n    return 2\n"})
    first_node = next(node for node in first.json()["nodes"] if node["name"] == "one")

    response = client.get(f"/api/source/{second.headers['X-Analysis-ID']}/{first_node['id']}")

    assert response.status_code == 404


def test_missing_file_and_traversal_metadata_are_rejected(monkeypatch):
    response = post_zip({"main.py": "def answer():\n    return 42\n"})
    analysis_id = response.headers["X-Analysis-ID"]
    node = next(node for node in response.json()["nodes"] if node["name"] == "answer")
    session = memory.get_session(analysis_id)
    session.sources.clear()
    assert client.get(f"/api/source/{analysis_id}/{node['id']}").status_code == 404

    session.sources[node["file_path"]] = "def answer():\n    return 42\n"
    stored_node = next(item for item in session.graph["nodes"] if item["id"] == node["id"])
    stored_node["file_path"] = "../secret.py"
    assert client.get(f"/api/source/{analysis_id}/{node['id']}").status_code == 404


def test_expired_analysis_is_rejected(monkeypatch):
    response = post_zip({"main.py": "def answer():\n    return 42\n"})
    analysis_id = response.headers["X-Analysis-ID"]
    node = next(node for node in response.json()["nodes"] if node["name"] == "answer")
    session = memory.get_session(analysis_id)
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert client.get(f"/api/source/{analysis_id}/{node['id']}").status_code == 404


def test_unsupported_language_metadata_is_rejected(monkeypatch):
    response = post_zip({"main.py": "def answer():\n    return 42\n"})
    analysis_id = response.headers["X-Analysis-ID"]
    node = next(node for node in response.json()["nodes"] if node["name"] == "answer")
    session = memory.get_session(analysis_id)
    stored_node = next(item for item in session.graph["nodes"] if item["id"] == node["id"])
    stored_node["language"] = "ruby"

    assert client.get(f"/api/source/{analysis_id}/{node['id']}").status_code == 404


def teardown_function():
    memory.clear_sessions()

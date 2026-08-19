from io import BytesIO
import shutil
import zipfile

from fastapi.testclient import TestClient

from main import app
from routes import analysis


client = TestClient(app)


def zip_bytes(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def post_zip(data: bytes):
    return client.post(
        "/api/analyze",
        files={"file": ("repository.zip", data, "application/zip")},
    )


def test_valid_zip_returns_graph_serialization():
    response = post_zip(zip_bytes({"main.py": "class Answer:\n    pass\n"}))

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"analysis_id", "nodes", "edges"}
    assert payload["analysis_id"]
    assert any(node["name"] == "Answer" for node in payload["nodes"])


def test_zip_with_multiple_supported_files_resolves_import():
    response = post_zip(
        zip_bytes(
            {
                "main.py": "from helper import value\n",
                "helper.py": "value = 42\n",
                "widget.ts": "export class Widget {}\n",
            }
        )
    )

    assert response.status_code == 200
    assert len(response.json()["nodes"]) >= 1


def test_empty_zip_is_rejected():
    assert post_zip(zip_bytes({})).status_code == 400


def test_missing_upload_is_rejected():
    response = client.post("/api/analyze")

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing ZIP upload"


def test_non_zip_upload_is_rejected():
    response = client.post(
        "/api/analyze",
        files={"file": ("repository.txt", b"not a zip", "text/plain")},
    )

    assert response.status_code == 400


def test_unsupported_only_repository_returns_empty_graph():
    response = post_zip(zip_bytes({"README.md": "No source here"}))

    assert response.status_code == 200
    payload = response.json()
    assert payload["nodes"] == []
    assert payload["edges"] == []
    assert payload["analysis_id"]


def test_malformed_source_does_not_fail_request():
    response = post_zip(zip_bytes({"broken.py": "class Broken(:\n"}))

    assert response.status_code == 200
    assert set(response.json()) == {"analysis_id", "nodes", "edges"}


def test_temporary_files_are_cleaned_up(monkeypatch, tmp_path):
    created = tmp_path / "request"

    def temporary_repository():
        from contextlib import contextmanager

        @contextmanager
        def repository():
            created.mkdir()
            yield created / "repository.zip", created / "repository"
            shutil.rmtree(created)

        return repository()

    monkeypatch.setattr(analysis, "temporary_repository", temporary_repository)
    response = post_zip(zip_bytes({"main.py": "answer = 42\n"}))

    assert response.status_code == 200
    assert not created.exists()

from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from routes import analysis
from storage.repository import ArchiveError, github_archive_url


client = TestClient(app)


@contextmanager
def temporary_repository(tmp_path):
    root = tmp_path / "request"
    root.mkdir()
    try:
        yield root / "repository.zip", root / "repository"
    finally:
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        root.rmdir()


def test_github_archive_url_accepts_repository_and_trailing_slash():
    expected = "https://github.com/user/repository/archive/HEAD.zip"

    assert github_archive_url("https://github.com/user/repository") == expected
    assert github_archive_url("https://github.com/user/repository/") == expected
    assert github_archive_url("https://github.com/user/repository.git") == expected


def test_github_archive_url_rejects_invalid_urls():
    invalid_urls = (
        "https://gitlab.com/user/repository",
        "http://github.com/user/repository",
        "https://github.com/user",
        "https://github.com/user/repository/issues",
        "not a url",
    )

    for url in invalid_urls:
        response = client.post("/api/analyze/github", json={"url": url})
        assert response.status_code == 400


def test_github_repository_returns_graph_from_downloaded_repository(monkeypatch, tmp_path):
    captured = {}

    def download(url, destination):
        captured["url"] = url
        destination.write_bytes(b"archive")
        destination.with_name("repository").mkdir()
        (destination.with_name("repository") / "main.py").write_text(
            "class Answer:\n    pass\n", encoding="utf-8"
        )

    monkeypatch.setattr(analysis, "temporary_repository", lambda: temporary_repository(tmp_path))
    monkeypatch.setattr(analysis, "download_github_repository", download)
    monkeypatch.setattr(analysis, "extract_archive", lambda archive, repository: None)

    response = client.post(
        "/api/analyze/github",
        json={"url": "https://github.com/user/repository/"},
    )

    assert response.status_code == 200
    assert captured["url"] == "https://github.com/user/repository/"
    assert set(response.json()) == {"analysis_id", "nodes", "edges"}
    assert any(node["name"] == "Answer" for node in response.json()["nodes"])


def test_github_download_failure_returns_bad_gateway(monkeypatch, tmp_path):
    def download(url, destination):
        raise ArchiveError("download failed")

    monkeypatch.setattr(analysis, "temporary_repository", lambda: temporary_repository(tmp_path))
    monkeypatch.setattr(analysis, "download_github_repository", download)

    response = client.post(
        "/api/analyze/github",
        json={"url": "https://github.com/user/repository"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "download failed"


def test_github_analyzer_failure_returns_server_error(monkeypatch, tmp_path):
    monkeypatch.setattr(analysis, "temporary_repository", lambda: temporary_repository(tmp_path))
    monkeypatch.setattr(analysis, "download_github_repository", lambda url, destination: None)
    monkeypatch.setattr(analysis, "extract_archive", lambda archive, repository: None)
    monkeypatch.setattr(
        analysis,
        "analyze_repository",
        lambda repository: (_ for _ in ()).throw(RuntimeError("analysis failed")),
    )

    response = client.post(
        "/api/analyze/github",
        json={"url": "https://github.com/user/repository"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Repository analysis failed"
    assert not (tmp_path / "request").exists()


def test_github_cleanup_runs_after_success(monkeypatch, tmp_path):
    monkeypatch.setattr(analysis, "temporary_repository", lambda: temporary_repository(tmp_path))
    monkeypatch.setattr(analysis, "download_github_repository", lambda url, destination: None)
    monkeypatch.setattr(analysis, "extract_archive", lambda archive, repository: None)
    monkeypatch.setattr(analysis, "analyze_repository", lambda repository: {"nodes": [], "edges": []})

    response = client.post(
        "/api/analyze/github",
        json={"url": "https://github.com/user/repository"},
    )

    assert response.status_code == 200
    assert not (tmp_path / "request").exists()

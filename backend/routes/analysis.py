from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from analyzer.service import SUPPORTED_EXTENSIONS, analyze_repository, relative_path
from storage.memory import create_session, get_session, source_for_symbol
from storage.repository import (
    ArchiveError,
    download_github_repository,
    extract_archive,
    github_archive_url,
    save_upload,
    temporary_repository,
)

router = APIRouter()


class GithubAnalysisRequest(BaseModel):
    url: str


def _source_files(repository_path: Path) -> dict[str, str]:
    sources = {}
    for path in repository_path.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            sources[relative_path(repository_path, path)] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
    return sources


def _analysis_response(response: Response, repository_path: Path) -> dict[str, object]:
    graph = analyze_repository(repository_path)
    analysis_id = create_session(graph, _source_files(repository_path))
    response.headers["X-Analysis-ID"] = analysis_id
    return {"analysis_id": analysis_id, **graph}


@router.post("/analyze")
def analyze(response: Response, file: Optional[UploadFile] = File(None)) -> dict[str, object]:
    if file is None:
        raise HTTPException(status_code=400, detail="Missing ZIP upload")

    try:
        with temporary_repository() as (archive_path, repository_path):
            save_upload(file, archive_path)
            extract_archive(archive_path, repository_path)
            return _analysis_response(response, repository_path)
    except ArchiveError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/analyze/github")
def analyze_github(response: Response, request: GithubAnalysisRequest) -> dict[str, object]:
    try:
        github_archive_url(request.url)
    except ArchiveError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        with temporary_repository() as (archive_path, repository_path):
            try:
                download_github_repository(request.url, archive_path)
            except ArchiveError as error:
                raise HTTPException(status_code=502, detail=str(error)) from error

            try:
                extract_archive(archive_path, repository_path)
            except ArchiveError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error

            try:
                return _analysis_response(response, repository_path)
            except Exception as error:
                raise HTTPException(status_code=500, detail="Repository analysis failed") from error
    except HTTPException:
        raise
    except OSError as error:
        raise HTTPException(status_code=500, detail="Temporary repository handling failed") from error


@router.get("/source/{analysis_id}/{symbol_id}")
def source(analysis_id: str, symbol_id: str) -> dict[str, object]:
    if get_session(analysis_id) is None:
        raise HTTPException(status_code=404, detail="Analysis not found or expired")

    result = source_for_symbol(analysis_id, symbol_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Symbol source not found")
    return result

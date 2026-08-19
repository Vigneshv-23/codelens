from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

MAX_ARCHIVE_SIZE = 50 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 200 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000


class ArchiveError(ValueError):
    pass


GITHUB_PART = re.compile(r"^[A-Za-z0-9._-]+$")
DOWNLOAD_TIMEOUT = 30


def github_archive_url(repository_url: str) -> str:
    parsed = urlsplit(repository_url.strip())
    parts = parsed.path.strip("/").split("/") if parsed.path.strip("/") else []
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.query
        or parsed.fragment
        or len(parts) != 2
        or not all(GITHUB_PART.fullmatch(part) for part in parts)
    ):
        raise ArchiveError("Invalid public GitHub repository URL")
    owner, repository = parts
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    return f"https://github.com/{owner}/{repository}/archive/HEAD.zip"


def download_github_repository(repository_url: str, destination: Path) -> None:
    archive_url = github_archive_url(repository_url)
    request = Request(archive_url, headers={"User-Agent": "CodeLens"})
    try:
        with urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response, destination.open("wb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_ARCHIVE_SIZE:
                    raise ArchiveError("Downloaded repository is too large")
                output.write(chunk)
    except ArchiveError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise ArchiveError("Unable to download public GitHub repository") from error


@contextmanager
def temporary_repository() -> Iterator[tuple[Path, Path]]:
    with tempfile.TemporaryDirectory(prefix="codelens-") as directory:
        root = Path(directory)
        yield root / "repository.zip", root / "repository"


def save_upload(upload, destination: Path) -> int:
    total = 0
    with destination.open("wb") as output:
        while chunk := upload.file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_ARCHIVE_SIZE:
                raise ArchiveError("Archive is too large")
            output.write(chunk)
    return total


def extract_archive(archive_path: Path, destination: Path) -> int:
    if not zipfile.is_zipfile(archive_path):
        raise ArchiveError("Uploaded file must be a ZIP archive")

    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if not entries:
            raise ArchiveError("ZIP archive is empty")
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ArchiveError("ZIP archive contains too many files")

        total_size = sum(entry.file_size for entry in entries)
        if total_size > MAX_UNCOMPRESSED_SIZE:
            raise ArchiveError("ZIP archive expands to too much data")

        destination.mkdir()
        for entry in entries:
            relative = PurePosixPath(entry.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ArchiveError("ZIP archive contains an unsafe path")
            target = destination.joinpath(*relative.parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

        return sum(1 for entry in entries if not entry.is_dir())

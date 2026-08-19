"""Small OpenAI-compatible provider adapter."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderError(Exception):
    pass


class MissingConfiguration(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    def __init__(self, retry_after=None):
        self.retry_after = retry_after
        super().__init__("AI provider rate limit reached")


class InvalidProviderResponse(ProviderError):
    pass


def _configuration() -> Tuple[str, str, str]:
    api_key = os.getenv("AI_API_KEY", "").strip()
    base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    model = os.getenv("AI_MODEL", "").strip()
    if not api_key or not model or not base_url:
        raise MissingConfiguration("AI explanation is not configured")
    return api_key, base_url, model


def complete(system_prompt: str, user_prompt: str, timeout: int = 30) -> str:
    api_key, base_url, model = _configuration()
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }).encode("utf-8")
    request = Request(
        base_url + "/chat/completions",
        data=payload,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "User-Agent": "CodeLens/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if getattr(response, "status", 200) < 200 or getattr(response, "status", 200) >= 300:
                raise ProviderUnavailable("AI provider request failed")
            body = response.read()
    except TimeoutError as error:
        raise ProviderTimeout("AI provider timed out") from error
    except HTTPError as error:
        if error.code == 429:
            raise ProviderRateLimited(error.headers.get("Retry-After")) from error
        if error.code in (408, 504):
            raise ProviderTimeout("AI provider timed out") from error
        raise ProviderUnavailable("AI provider request failed") from error
    except (URLError, OSError) as error:
        raise ProviderUnavailable("AI provider unavailable") from error

    try:
        result: Dict[str, Any] = json.loads(body.decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise InvalidProviderResponse("AI provider returned an invalid response") from error
    if not isinstance(content, str) or not content.strip():
        raise InvalidProviderResponse("AI provider returned an invalid response")
    return content.strip()

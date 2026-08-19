from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from explanation.context import ContextError, EmptyContext, SymbolNotFound
from explanation.provider import (
    InvalidProviderResponse,
    MissingConfiguration,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from explanation.service import ACTIONS, explain_symbol
from storage.memory import get_session

router = APIRouter()


class ExplanationRequest(BaseModel):
    analysis_id: str
    symbol_id: str
    action: str


@router.post("/explain")
def explain(request: ExplanationRequest, response: Response) -> dict[str, object]:
    session = get_session(request.analysis_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Analysis not found or expired")
    if request.action not in ACTIONS:
        raise HTTPException(status_code=422, detail="Unsupported explanation action")
    try:
        return explain_symbol(session, request.symbol_id, request.action)
    except SymbolNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except EmptyContext as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MissingConfiguration as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ProviderRateLimited as error:
        if error.retry_after:
            response.headers["Retry-After"] = str(error.retry_after)
            detail = "AI provider rate limit reached; retry after " + str(error.retry_after) + " seconds"
        else:
            detail = "AI provider rate limit reached; please retry shortly"
        raise HTTPException(status_code=429, detail=detail, headers={"Retry-After": str(error.retry_after)} if error.retry_after else None) from error
    except ProviderTimeout as error:
        raise HTTPException(status_code=504, detail="AI provider timed out") from error
    except ProviderUnavailable as error:
        raise HTTPException(status_code=502, detail="AI provider unavailable") from error
    except InvalidProviderResponse as error:
        raise HTTPException(status_code=502, detail="AI provider returned an invalid response") from error
    except ContextError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

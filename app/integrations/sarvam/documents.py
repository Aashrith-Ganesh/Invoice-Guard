import httpx
from fastapi import HTTPException

from app.config import get_settings


async def sarvam_request(method: str, path: str, **kwargs) -> dict:
    api_key = get_settings().sarvam_api_key.get_secret_value()
    if not api_key:
        raise HTTPException(503, "Sarvam credentials are missing on the server.")
    try:
        async with httpx.AsyncClient(
            base_url="https://api.sarvam.ai",
            headers={"api-subscription-key": api_key},
            timeout=30,
        ) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Sarvam timed out.") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {400, 404, 413, 422, 429}:
            raise HTTPException(status, "Sarvam could not process the request.") from exc
        raise HTTPException(502, "Sarvam returned an upstream error.") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(502, "Could not read the Sarvam response.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(502, "Unexpected Sarvam response format.")
    return payload

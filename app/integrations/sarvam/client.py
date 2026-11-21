import httpx

from app.config import get_settings


async def complete_chat(payload: dict) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.sarvam_timeout_seconds) as client:
        response = await client.post(
            "https://api.sarvam.ai/v1/chat/completions",
            headers={"api-subscription-key": settings.sarvam_api_key.get_secret_value()},
            json=payload,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]

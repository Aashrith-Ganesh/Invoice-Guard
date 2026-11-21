"""Sarvam translation adapter (Mayura). Used only when `SARVAM_API_KEY` is set; tests use fakes."""
import logging

import httpx

LANGUAGES = {
    "en": "English", "ta": "தமிழ்", "hi": "हिन्दी", "kn": "ಕನ್ನಡ", "te": "తెలుగు", "ml": "മലയാളം",
    "mr": "मराठी", "bn": "বাংলা", "gu": "ગુજરાતી", "pa": "ਪੰਜਾਬੀ", "od": "ଓଡ଼ିଆ",
}
log = logging.getLogger(__name__)


class SarvamTranslator:
    name = "sarvam"
    url = "https://api.sarvam.ai/translate"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client(timeout=15)

    def translate(self, texts: list[str], target: str) -> list[str] | None:
        out = []
        try:
            for text in texts:
                if not text.strip():
                    out.append(text)
                    continue
                response = self._client.post(self.url, headers={"api-subscription-key": self._key}, json={
                    "input": text[:1000], "source_language_code": "en-IN",
                    "target_language_code": f"{target}-IN", "model": "mayura:v1",
                })
                response.raise_for_status()
                out.append(response.json()["translated_text"])
        except (httpx.HTTPError, KeyError, ValueError) as error:
            log.warning("Sarvam translation unavailable: %s", type(error).__name__)
            return None
        return out

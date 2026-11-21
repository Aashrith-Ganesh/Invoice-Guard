import json
import os
from dataclasses import dataclass
from typing import Annotated, Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import BaseModel, PositiveInt, StringConstraints, TypeAdapter


class Principal(BaseModel):
    business_id: PositiveInt
    role: Literal["service", "owner", "mcp"]
    subject: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")] | None = None


@dataclass(frozen=True)
class Settings:
    database_url: str
    bearer_keys: dict[str, Principal]
    simulator_secret: str
    sarvam_api_key: str = ""
    document_extractor_mode: Literal["demo", "sarvam"] = "demo"
    cors_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        cors_origins = tuple(value.strip() for value in os.getenv("CHECK_CORS_ORIGINS", "").split(",") if value.strip())
        for origin in cors_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None
                    or parsed.path or parsed.query or parsed.fragment or "*" in origin):
                raise ValueError("CHECK_CORS_ORIGINS must contain explicit HTTP(S) origins.")
        return cls(
            database_url=os.getenv("CHECK_DATABASE_URL", "sqlite:///check.db"),
            bearer_keys=TypeAdapter(dict[str, Principal]).validate_python(
                json.loads(os.getenv("CHECK_BEARER_KEYS", "{}"))
            ),
            simulator_secret=os.getenv("CHECK_SIMULATOR_SECRET", ""),
            sarvam_api_key=os.getenv("SARVAM_API_KEY", ""),
            document_extractor_mode=TypeAdapter(Literal["demo", "sarvam"]).validate_python(
                os.getenv("CHECK_DOCUMENT_EXTRACTOR", "demo")
            ),
            cors_origins=cors_origins,
        )

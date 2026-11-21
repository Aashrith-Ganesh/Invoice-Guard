import json
import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, PositiveInt, TypeAdapter


class Principal(BaseModel):
    business_id: PositiveInt
    role: Literal["service", "owner"]


@dataclass(frozen=True)
class Settings:
    database_url: str
    bearer_keys: dict[str, Principal]
    simulator_secret: str
    sarvam_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            database_url=os.getenv("CHECK_DATABASE_URL", "sqlite:///check.db"),
            bearer_keys=TypeAdapter(dict[str, Principal]).validate_python(
                json.loads(os.getenv("CHECK_BEARER_KEYS", "{}"))
            ),
            simulator_secret=os.getenv("CHECK_SIMULATOR_SECRET", ""),
            sarvam_api_key=os.getenv("SARVAM_API_KEY", ""),
        )

import json
import os
from dataclasses import dataclass
from typing import Annotated, Literal

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

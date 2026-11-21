from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Type

from pydantic import BaseModel


ToolHandler = Callable[[BaseModel, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: Type[BaseModel]
    handler: ToolHandler
    requires_approval: bool = False

    def to_sarvam_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        # The function parameters field expects a JSON Schema object.
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }

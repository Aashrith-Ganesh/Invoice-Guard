from pydantic import BaseModel, ConfigDict

from app.tools.base import Tool
from app.tools.registry import ToolRegistry


class EchoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


async def echo(args: EchoArgs, context: dict):
    return {"echo": args.value}


def test_registry_exports_function_schema():
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="Echo a value for testing.",
            args_model=EchoArgs,
            handler=echo,
        )
    )
    schema = registry.schemas_for(("echo",))[0]
    assert schema["function"]["name"] == "echo"
    assert "value" in schema["function"]["parameters"]["properties"]

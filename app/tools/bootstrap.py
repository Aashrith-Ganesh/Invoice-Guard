from app.integrations.existing_backend import GetVendorArgs, get_vendor
from app.tools.base import Tool
from app.tools.registry import ToolRegistry


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="get_vendor",
            description="Retrieve a vendor record from the existing business application using its vendor ID.",
            args_model=GetVendorArgs,
            handler=get_vendor,
            requires_approval=False,
        )
    )

    return registry

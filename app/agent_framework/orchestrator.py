import json
from typing import Any

from app.config import get_settings
from app.integrations.sarvam.client import complete_chat
from app.tools.registry import ToolRegistry


class AgentOrchestrator:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def run(
        self,
        *,
        agent_config,
        user_input: str,
        history: list[dict[str, Any]] | None = None,
        tool_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        tool_outputs = []
        tool_context = tool_context or {}

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": agent_config.system_prompt}
        ]
        # Only pass known conversation roles/content. Never accept system messages
        # supplied by the browser as trusted prompts.
        for item in (history or [])[-12:]:
            if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
                messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": user_input})

        tools = self.registry.schemas_for(agent_config.allowed_tools)
        total_tool_calls = 0

        for _round in range(settings.agent_max_tool_rounds):
            request = {
                "model": agent_config.model or settings.sarvam_model,
                "messages": messages,
                "max_tokens": 2048,
            }
            if tools:
                request["tools"] = tools
                request["tool_choice"] = "auto"

            message = await complete_chat(request)
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                content = message.get("content") or ""
                return {
                    "status": "completed",
                    "outputs": tool_outputs,
                    "message": content,
                    "tool_calls": total_tool_calls,
                }

            # Keep the assistant tool-call message in the conversation.
            assistant_tool_message = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["function"]["name"],
                            "arguments": call["function"]["arguments"],
                        },
                    }
                    for call in tool_calls
                ],
            }
            messages.append(assistant_tool_message)

            for call in tool_calls:
                total_tool_calls += 1
                if total_tool_calls > settings.agent_max_tool_calls:
                    return {
                        "status": "limit_reached",
                        "message": "Maximum number of tool calls reached.",
                        "tool_calls": total_tool_calls - 1,
                    }

                tool_name = call["function"]["name"]
                if tool_name not in agent_config.allowed_tools:
                    raise PermissionError(f"Agent is not allowed to use tool: {tool_name}")

                tool = self.registry.get(tool_name)
                args = tool.args_model.model_validate_json(call["function"]["arguments"])

                if tool.requires_approval:
                    # Do not execute. A production approval flow must persist this
                    # request and resume execution only after authenticated approval.
                    return {
                        "status": "awaiting_approval",
                        "message": "This action requires human approval.",
                        "pending_tool": tool_name,
                        "pending_arguments": args.model_dump(),
                        "tool_calls": total_tool_calls,
                    }

                result = await tool.handler(args, tool_context)
                tool_outputs.append({"tool": tool_name, "call_id": call["id"], "data": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        return {
            "status": "limit_reached",
            "message": "The agent reached its maximum reasoning/tool-call rounds.",
            "tool_calls": total_tool_calls,
        }

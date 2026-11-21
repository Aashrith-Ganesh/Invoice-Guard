from app.agent_framework.orchestrator import AgentOrchestrator
from app.tools.bootstrap import build_tool_registry


tool_registry = build_tool_registry()
orchestrator = AgentOrchestrator(tool_registry)

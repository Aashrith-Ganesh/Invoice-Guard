from uuid import uuid4
from app.api.dependencies import Actor, Database

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.agent_framework.configs import AGENTS
from app.agent_framework.runtime import orchestrator

router = APIRouter(prefix="/api/v1/agent-runs", tags=["AI Agents"])


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field(default="text", pattern="^text$")
    content: str = Field(min_length=1, max_length=12000)


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str
    session_id: str | None = None
    input: AgentInput
    history: list[dict] = Field(default_factory=list, max_length=12)


def get_tool_context(actor: Actor, engine: Database) -> dict:
    return {"business_id": actor.business_id, "engine": engine}


@router.get("")
async def list_agents(actor: Actor):
    return [{"agent_id": a.agent_id, "name": a.name, "description": a.description} for a in AGENTS.values()]


@router.post("")
async def run_agent(request: AgentRunRequest, context: dict = Depends(get_tool_context)):
    agent_config = AGENTS.get(request.agent_id)
    if not agent_config:
        raise HTTPException(status_code=404, detail="Unknown agent_id")

    run_id = str(uuid4())
    try:
        result = await orchestrator.run(
            agent_config=agent_config,
            user_input=request.input.content,
            history=request.history,
            tool_context=context,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        # Replace with structured logging/exception mapping in the host app.
        raise HTTPException(status_code=502, detail="Agent execution failed") from exc

    return {
        "run_id": run_id,
        "session_id": request.session_id,
        "agent_id": request.agent_id,
        **result,
    }

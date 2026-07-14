"""Agent management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories as repo
from app.__init_db import get_db
from app.auth.deps import get_current_user, get_current_space
from app.models.user import User

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.post("")
async def create_agent(data: dict, db: AsyncSession = Depends(get_db),
                       current_space: str | None = Depends(get_current_space)):
    if current_space:
        data["space_id"] = current_space
    return await repo.create_agent(db, data)


@router.get("")
async def list_agents(status: str | None = None, db: AsyncSession = Depends(get_db),
                      current_space: str | None = Depends(get_current_space)):
    return await repo.list_agents(db, space_id=current_space, status=status)


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user),
                     current_space: str | None = Depends(get_current_space)):
    agent = await repo.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    if not await repo.verify_space_access(db, repo.Agent, agent_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    return agent


@router.put("/{agent_id}")
async def update_agent(agent_id: str, data: dict, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user),
                        current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Agent, agent_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    agent = await repo.update_agent(db, agent_id, data)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user),
                        current_space: str | None = Depends(get_current_space)):
    if not await repo.verify_space_access(db, repo.Agent, agent_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    if not await repo.delete_agent(db, agent_id):
        raise HTTPException(404, "Agent not found")


@router.post("/{agent_id}/check")
async def check_agent(agent_id: str, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user),
                       current_space: str | None = Depends(get_current_space)):
    """Connectivity check for an agent."""
    if not await repo.verify_space_access(db, repo.Agent, agent_id, current_space, current_user.role):
        raise HTTPException(403, "Access denied")
    agent = await repo.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    from app.engine import AgentInvoker
    invoker = AgentInvoker()
    agent_cfg = {
        "api_base_url": agent.api_base_url,
        "method": agent.method,
        "headers_template": agent.headers_template or {},
        "body_template": agent.body_template or {},
        "auth_type": agent.auth_type,
        "auth_credentials": agent.auth_credentials or "",
    }
    result = await invoker.invoke(agent_cfg, "ping", timeout_ms=agent.timeout_ms or 30_000)
    return {
        "reachable": result.error is None,
        "status_code": result.status_code,
        "response_time_ms": result.response_time_ms,
        "error": result.error,
    }

from pydantic import BaseModel
from uuid import UUID

from app.models.enums import AgentStatus,AgentType

class AgentEvent(BaseModel):
    project_id:str
    agent: AgentType
    status: AgentStatus
    message: str
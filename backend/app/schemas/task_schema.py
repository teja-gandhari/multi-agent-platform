from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import TaskPriority,TaskStatus

class TaskCreate(BaseModel):
    title: str
    description: str | None= None
    priority: TaskPriority = TaskPriority.MEDIUM

class TaskResponse(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    description: str | None= None
    status: TaskStatus
    priority: TaskPriority
    created_at: datetime
    updated_at: datetime

    model_config={
        "from_attributes": True
    }

class TaskUpdate(BaseModel):
    title: str | None= None
    description: str | None= None
    priority: TaskPriority | None= None
    status: TaskStatus | None= None

class TaskStatusUpdate(BaseModel):
    status:TaskStatus


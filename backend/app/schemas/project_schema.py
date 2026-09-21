from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

from app.models.enums import ProjectStatus


class ProjectCreate(BaseModel):
    title:str
    description:str | None

class ProjectReponse(BaseModel):
    id:UUID
    name:str
    description:str | None
    owner_id:UUID
    status:ProjectStatus
    created_at:datetime
    updated_at:datetime

    model_config={
        "from_attributes":True
    }

class ProjectListResponse(BaseModel):
    items:list[ProjectReponse]
    page:int
    limit:int
    total:int
    total_pages:int

class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None

class ProjectStatusUpdate(BaseModel):
    status:ProjectStatus
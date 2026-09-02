from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class ProjectCreate(BaseModel):
    title:str
    description:str | None

class ProjectReponse(BaseModel):
    id:UUID
    name:str
    description:str | None
    owner_id:UUID
    created_at:datetime
    updated_at:datetime

    model_config={
        "from_attributes":True
    }

class ProjectListResponse(BaseModel):
    item:list[ProjectReponse]
    page:int
    limit:int
    total:int
    total_pages:int

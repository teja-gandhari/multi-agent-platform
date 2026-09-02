from fastapi import APIRouter,Depends,Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.project_schema import ProjectCreate,ProjectReponse,ProjectListResponse
from app.models.user import User
from app.services.project_service import ProjectService

project_router=APIRouter(
    prefix="/project",
    tags=["Projects"]
)

@project_router.post("",response_model=ProjectReponse)
def create_projects(project_data:ProjectCreate,
db:Session=Depends(get_db),current_user : User = Depends(get_current_user)):
    service=ProjectService(db)
    return service.create_project(
        name=project_data.title,
        description=project_data.description,
        current_user=current_user
        )
@project_router.get("",response_model=list[ProjectReponse])
def get_owner_projects(page:int=Query(1,ge=1),limit:int=Query(10,ge=1,le=100),
db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    service=ProjectService(db)
    projects,total,total_pages=service.get_projects(
        page=page,
        limit=limit,
        current_user=current_user
    )
    return ProjectListResponse(
        item=projects,
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages
    )
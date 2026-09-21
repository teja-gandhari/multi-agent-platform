from fastapi import APIRouter,Depends,Query
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.schemas.project_schema import ProjectCreate,ProjectReponse,ProjectListResponse,ProjectUpdate,ProjectStatusUpdate
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

@project_router.get("",response_model=ProjectListResponse)
def get_owner_projects(page:int=Query(1,ge=1),limit:int=Query(10,ge=1,le=100),
db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    service=ProjectService(db)
    projects,total,total_pages=service.get_projects(
        page=page,
        limit=limit,
        current_user=current_user
    )
    return ProjectListResponse(
        items=projects,
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages
    )

@project_router.get("/{project_id}",response_model=ProjectReponse)
def get_project_by_id(project_id:UUID,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    service=ProjectService(db)
    return service.get_project(project_id=project_id,current_user=current_user)


@project_router.put("/{project_id}",response_model=ProjectReponse)
def project_update(project_id:UUID,project_data:ProjectUpdate,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    service=ProjectService(db)
    return service.update_project(project_id=project_id,project_data=project_data,current_user=current_user)
    
@project_router.delete("/{project_id}",status_code=204)
def delete_project(project_id:UUID,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    service=ProjectService(db)
    return service.delete_project(project_id=project_id,current_user=current_user)

@project_router.patch("/{project_id}/status",response_model=ProjectReponse)
def update_project_status(project_id:UUID,status_data:ProjectStatusUpdate,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    service=ProjectService(db)
    return service.update_status(project_id=project_id,
                                  status=status_data.status,
                                  current_user=current_user)


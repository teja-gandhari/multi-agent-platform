from uuid import UUID

from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.schemas.task_schema import TaskCreate,TaskResponse,TaskUpdate,TaskStatusUpdate
from app.services.task_service import TaskService
from app.models.user import User


task_router=APIRouter(
    tags=["Tasks"],
    prefix="/projects",

    
)

@task_router.post("/{project_id}/tasks",response_model=TaskResponse)
def create_task(project_id: UUID,task_data: TaskCreate,db:Session=Depends(get_db),current_user: User=Depends(get_current_user)):
    service=TaskService(db)

    return service.create_task(
        project_id=project_id,
        title=task_data.title,
        description=task_data.description,
        priority=task_data.priority,
        current_user=current_user
    )

@task_router.get("/{project_id}/tasks",response_model=list[TaskResponse])
def get_project_task(project_id: UUID,db:Session=Depends(get_db),current_user: User=Depends(get_current_user)):
    service=TaskService(db)
    return service.get_project_tasks(project_id=project_id,current_user=current_user)

@task_router.get("/{project_id}/tasks/{task_id}",response_model=TaskResponse)
def get_task(project_id: UUID,task_id: UUID,db:Session=Depends(get_db),current_user: User=Depends(get_current_user)):
    service = TaskService(db)

    return service.get_task(task_id=task_id,project_id=project_id,current_user=current_user)

@task_router.patch("/{project_id}/tasks/{task_id}",response_model=TaskResponse)
def task_update(task_id: UUID,project_id: UUID,task_data:TaskUpdate,db:Session=Depends(get_db),current_user: User=Depends(get_current_user)):
    service = TaskService(db)
    return service.update_task(project_id=project_id,task_id=task_id,task_data=task_data,current_user=current_user)

@task_router.delete("/{project_id}/tasks/{task_id}",status_code=204)
def delete_project(project_id:UUID,task_id: UUID,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    service=TaskService(db)
    return service.delete_task(project_id=project_id,task_id=task_id,current_user=current_user)

@task_router.patch("/{project_id}/tasks/{task_id}/status",response_model=TaskResponse)
def updated_status(task_id: UUID,project_id: UUID,task_status:TaskStatusUpdate,db:Session=Depends(get_db),current_user: User=Depends(get_current_user)):
    service = TaskService(db)
    return service.update_status(project_id=project_id,
                                 task_id=task_id,
                                 status=task_status.status,
                                 current_user=current_user)


from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session


from app.models.task import Task
from app.models.user import User
from app.models.enums import TaskPriority,TaskStatus
from app.repositories.task_repository import TaskRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.task_schema import TaskUpdate



class TaskService:

    VALID_TRANSITIONS={
        TaskStatus.PENDING:[TaskStatus.IN_PROGRESS],
        TaskStatus.IN_PROGRESS:[TaskStatus.COMPLETED,TaskStatus.FAILED],
        TaskStatus.COMPLETED:[],
        TaskStatus.FAILED:[]
    }


    def __init__(self,db: Session):
        self.task_repository=TaskRepository(db)
        self.project_repository=ProjectRepository(db)

    def create_task(self,project_id: UUID,title: str, description: str | None,priority: TaskPriority,current_user: User):
        project=self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        if project.owner_id!=current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )
        task= Task(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority
        )
        return self.task_repository.create(task)

    def get_project_tasks(self,project_id: UUID,current_user: User):
        project=self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        if project.owner_id!=current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )
        return self.task_repository.get_by_project(project_id)

    
    def get_task(self,task_id: UUID,project_id: UUID,current_user: User):
        project=self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        if project.owner_id!=current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )
        task=self.task_repository.get_by_id(task_id)
        if not task:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        if task.project_id != project_id:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        return task
    
    def update_task(self,task_id: UUID,task_data:TaskUpdate,project_id: UUID, current_user: User):
        project=self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        if project.owner_id!=current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )
        task=self.task_repository.get_by_id(task_id)
        if not task:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        if task.project_id != project_id:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        
        updated_data=task_data.model_dump(exclude_unset=True)

        for field, value in updated_data.items():
            setattr(task,field,value)
            
    
        return self.task_repository.update(task)

    def delete_task(self,task_id: UUID,project_id: UUID,current_user: User):
        project=self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        if project.owner_id!=current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )
        task=self.task_repository.get_by_id(task_id)
        if not task:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        if task.project_id != project_id:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        return self.task_repository.delete(task)

    def update_status(self,task_id:UUID,project_id:UUID,status:TaskStatus,current_user:User):
        project=self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="project not found"
            )
        if project.owner_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )
        task=self.task_repository.get_by_id(task_id)
        if not task:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        if task.project_id != project_id:
            raise HTTPException(
                status_code=404,
                detail="Task not found"
            )
        allowed_status=self.VALID_TRANSITIONS.get(task.status,[])
        if status not in allowed_status:
            raise HTTPException(
                status_code=400,
                detail="Invalid Status transition"
            )
        task.status=status
        return self.task_repository.update(task)
        

    
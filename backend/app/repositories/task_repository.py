from uuid import UUID
from sqlalchemy.orm import Session

from app.models.task import Task

class TaskRepository:

    def  __init__(self,db: Session):
        self.db=db

    def create(self,task: Task)->Task:
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task
    
    def get_by_project(self,project_id: UUID)->list[Task]:
        return self.db.query(Task).filter(
            Task.project_id==project_id
        ).all()

    def get_by_id(self,task_id: UUID)->Task | None:
        return self.db.query(Task).filter(Task.id==task_id).first()
    
    
    def update(self,task:Task)->Task:
        self.db.commit()
        self.db.refresh(task)
        return task

    def delete(self,task:Task)->None:
        self.db.delete(task)
        self.db.commit()
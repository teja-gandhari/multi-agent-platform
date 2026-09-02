from sqlalchemy.orm import Session
from fastapi import Depends
from uuid import UUID

from app.models.project import Project
from app.core.dependencies import get_current_user
from app.models.user import User


class ProjectRepository:
    def __init__(self,db:Session):
        self.db=db

    def create(self,project:Project):
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)

        return project

    def get_by_owner(self,owner_id:UUID,offset:int,limit:int)->list[Project]:
        return(
            self.db.query(Project).filter(
                Project.owner_id==owner_id
            ).offset(offset).limit(limit).all()
        )
    def get_by_count(self,owner_id:UUID)->int:
            return self.db.query(Project).filter(Project.owner_id==owner_id).count()

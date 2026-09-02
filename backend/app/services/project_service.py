from sqlalchemy.orm import Session
from math import ceil
from uuid import UUID

from app.models.project import Project
from app.models.user import User
from app.repositories.project_repository import ProjectRepository


class ProjectService:
    def __init__(self,db:Session):
        self.project_repository=ProjectRepository(db)

    def create_project(self,name:str,description:str | None , current_user:User)->Project:
        
        project=Project(
            name=name,
            description=description,
            owner_id=current_user.id
        )
        return self.project_repository.create(project)

    def get_projects(self,page:int,limit:int,current_user:User)->list[Project]:
        offset=(page-1)*limit
        total=self.project_repository.get_by_count(current_user.id)
        total_pages=ceil(total/limit)

        projects = self.project_repository.get_by_owner(
            current_user.id,offset,limit
        )

        return projects,total,total_pages
    


    


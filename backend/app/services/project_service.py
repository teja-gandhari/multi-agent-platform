from sqlalchemy.orm import Session
from math import ceil
from uuid import UUID
from fastapi import HTTPException

from app.models.project import Project
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.project_schema import ProjectUpdate
from app.models.enums import ProjectStatus


class ProjectService:
        
    VALID_TRANSITION={
        ProjectStatus.CREATED:[ProjectStatus.PLANNING],
        ProjectStatus.PLANNING:[ProjectStatus.RUNNING],
        ProjectStatus.RUNNING:[ProjectStatus.COMPLETED,ProjectStatus.FAILED],
        ProjectStatus.COMPLETED:[],
        ProjectStatus.FAILED:[]
    }


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

    def get_project(self,project_id:UUID,current_user:User) -> Project:
        project = self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        
        if project.owner_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )
        return project

    def update_project(self,project_id:UUID,project_data:ProjectUpdate,current_user:User)->Project:
        project = self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        if project.owner_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )

        project.name=project_data.name
        project.description=project_data.description
        return self.project_repository.update(project)

    def delete_project(self,project_id:UUID,current_user:User)->None:
        project = self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        if project.owner_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )
        return self.project_repository.delete(project)

    def update_status(self,project_id:UUID,status:ProjectStatus,current_user:User):
        project=self.project_repository.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        if project.owner_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized"
            )
        allowed_status=self.VALID_TRANSITION.get(project.status,[])
        if status not in allowed_status:
            raise HTTPException(
                status_code=400,
                detail="Invalid status transition"
            )
        project.status=status
        return self.project_repository.update(project)
    
    

            




    


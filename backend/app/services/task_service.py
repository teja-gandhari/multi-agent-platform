
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.enums import TaskPriority, TaskStatus
from app.models.task import Task
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.task_schema import TaskUpdate


class TaskService:
    VALID_TRANSITIONS = {
        TaskStatus.PENDING: [TaskStatus.IN_PROGRESS],
        TaskStatus.IN_PROGRESS: [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
        ],
        TaskStatus.COMPLETED: [],
        TaskStatus.FAILED: [],
    }

    def __init__(self, db: Session):
        self.task_repository = TaskRepository(db)
        self.project_repository = ProjectRepository(db)

    def _get_owned_project(
        self,
        project_id: UUID,
        current_user: User,
    ):
        project = self.project_repository.get_by_id(project_id)

        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found",
            )

        if project.owner_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized",
            )

        return project

    def _get_project_task(
        self,
        task_id: UUID,
        project_id: UUID,
        current_user: User,
    ) -> Task:
        self._get_owned_project(project_id, current_user)

        task = self.task_repository.get_by_id(task_id)

        if not task or task.project_id != project_id:
            raise HTTPException(
                status_code=404,
                detail="Task not found",
            )

        return task

    def create_task(
        self,
        project_id: UUID,
        title: str,
        description: str | None,
        priority: TaskPriority,
        current_user: User,
    ) -> Task:
        self._get_owned_project(project_id, current_user)

        task = Task(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
        )
        return self.task_repository.create(task)

    def get_project_tasks(
        self,
        project_id: UUID,
        current_user: User,
    ) -> list[Task]:
        self._get_owned_project(project_id, current_user)
        return self.task_repository.get_by_project(project_id)

    def get_task(
        self,
        task_id: UUID,
        project_id: UUID,
        current_user: User,
    ) -> Task:
        return self._get_project_task(
            task_id, project_id, current_user
        )

    def update_task(
        self,
        task_id: UUID,
        task_data: TaskUpdate,
        project_id: UUID,
        current_user: User,
    ) -> Task:
        task = self._get_project_task(
            task_id, project_id, current_user
        )
        changes = task_data.model_dump(exclude_unset=True)

        if "status" in changes:
            allowed = self.VALID_TRANSITIONS.get(task.status, [])

            if changes["status"] not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid status transition",
                )

        if "title" in changes:
            if changes["title"] is None or not changes["title"].strip():
                raise HTTPException(
                    status_code=422,
                    detail="Task title cannot be empty",
                )

        for field, value in changes.items():
            setattr(task, field, value)

        return self.task_repository.update(task)

    def delete_task(
        self,
        task_id: UUID,
        project_id: UUID,
        current_user: User,
    ) -> None:
        task = self._get_project_task(
            task_id, project_id, current_user
        )
        self.task_repository.delete(task)

    def update_status(
        self,
        task_id: UUID,
        project_id: UUID,
        status: TaskStatus,
        current_user: User,
    ) -> Task:
        task = self._get_project_task(
            task_id, project_id, current_user
        )
        allowed = self.VALID_TRANSITIONS.get(task.status, [])

        if status not in allowed:
            raise HTTPException(
                status_code=400,
                detail="Invalid status transition",
            )

        task.status = status
        return self.task_repository.update(task)

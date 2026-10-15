
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.models.agent_message import AgentMessage
from app.models.agent_run import AgentRun
from app.models.user import User
from app.services.nexus_workflow_adapter import run_nexus_workflow
from app.services.project_service import ProjectService

router = APIRouter(prefix="/agents", tags=["Agents"])


class AgentRequest(BaseModel):
    task: str = Field(min_length=1, max_length=2000)
    project_id: str = Field(min_length=1, max_length=100)


class AgentResponse(BaseModel):
    project_id: str
    workflow_status: str
    application_url: str = ""
    revision_count: int = 0
    plan: str = ""
    research_output: str = ""
    developer_output: str = ""
    test_result: dict = Field(default_factory=dict)
    review: dict = Field(default_factory=dict)
    runner_result: dict = Field(default_factory=dict)
    error_message: str = ""


class AgentRunHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    requested_task: str
    status: str
    result: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class AgentMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    agent: str
    status: str
    message: str
    event_data: dict | None
    created_at: datetime


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    request: AgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        project_id = UUID(request.project_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID format.",
        ) from exc

    ProjectService(db).get_project(project_id, current_user)

    run = AgentRun(
        project_id=project_id,
        requested_task=request.task,
        status="running",
    )

    try:
        db.add(run)
        db.commit()
        db.refresh(run)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create workflow run.",
        ) from exc

    try:
        result = await run_nexus_workflow(
            project_id=str(project_id),
            user_request=request.task,
            run_id=str(run.id),
        )

        response = AgentResponse(**result)

        run.status = response.workflow_status.lower()
        run.result = response.model_dump(mode="json")
        run.error_message = response.error_message or None

        db.commit()
        return response

    except Exception as exc:
        db.rollback()

        try:
            failed_run = db.get(AgentRun, run.id)
            if failed_run:
                failed_run.status = "failed"
                failed_run.error_message = str(exc)[:2000]
                db.commit()
        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Agent workflow execution failed.",
        ) from exc


@router.get(
    "/runs/{project_id}",
    response_model=list[AgentRunHistoryItem],
)
def get_agent_run_history(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ProjectService(db).get_project(project_id, current_user)

    return (
        db.query(AgentRun)
        .filter(AgentRun.project_id == project_id)
        .order_by(AgentRun.created_at.desc())
        .limit(50)
        .all()
    )


@router.get(
    "/runs/{run_id}/messages",
    response_model=list[AgentMessageResponse],
)
def get_agent_run_messages(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Find the requested run.
    run = (
        db.query(AgentRun)
        .filter(AgentRun.id == run_id)
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Agent run not found.",
        )

    # Check ownership before exposing any run messages.
    ProjectService(db).get_project(run.project_id, current_user)

    # Return up to 500 messages in chronological order.
    return (
        db.query(AgentMessage)
        .filter(AgentMessage.run_id == run_id)
        .order_by(AgentMessage.created_at.asc())
        .limit(500)
        .all()
    )

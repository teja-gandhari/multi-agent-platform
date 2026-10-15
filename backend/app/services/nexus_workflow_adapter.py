import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from app.database.session import SessionLocal
from app.models.agent_message import AgentMessage
from app.services.redis_service import publish_project_event

WORKFLOW_ROOT = Path(__file__).resolve().parents[3] / "nexuxai_workflow"

if not WORKFLOW_ROOT.is_dir():
    raise RuntimeError(f"LangGraph workflow directory not found: {WORKFLOW_ROOT}")

workflow_path = str(WORKFLOW_ROOT)
if workflow_path not in sys.path:
    sys.path.insert(0, workflow_path)

from workflow import (  # noqa: E402
    run_workflow_async as _run_workflow_async,
    resume_workflow_async as _resume_workflow_async,
)


def _persist_event(run_id: str, event: dict) -> None:
    """Persist one progress event in an independent SQLAlchemy session."""
    db = SessionLocal()
    try:
        db.add(
            AgentMessage(
                run_id=UUID(str(run_id)),
                agent=str(event.get("agent", "workflow")),
                status=str(event.get("status", "in_progress")),
                message=str(event.get("message", "")),
                event_data=event,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _build_progress_callback(project_id: str, run_id: str):
    """Persist and publish progress without making transport failures fatal."""
    loop = asyncio.get_running_loop()

    def on_progress(event: dict) -> None:
        event = {**event, "project_id": project_id, "run_id": run_id}
        event_json = json.dumps(event, default=str)

        try:
            persist_future = asyncio.run_coroutine_threadsafe(
                asyncio.to_thread(_persist_event, run_id, event), loop
            )
            persist_future.result()
        except Exception as exc:
            print(f"[Agent event persistence warning] {type(exc).__name__}: {exc}")

        try:
            publish_future = asyncio.run_coroutine_threadsafe(
                asyncio.to_thread(publish_project_event, project_id, event_json),
                loop,
            )
            publish_future.result()
        except Exception as exc:
            print(f"[Redis publish warning] {type(exc).__name__}: {exc}")

    return on_progress


async def run_nexus_workflow(
    project_id: str,
    user_request: str,
    run_id: str,
) -> dict:
    """Start a workflow and return either its result or the plan approval pause."""
    on_progress = _build_progress_callback(project_id, run_id)
    return await _run_workflow_async(
        project_id=project_id,
        user_request=user_request,
        run_id=run_id,
        on_progress=on_progress,
    )


async def resume_nexus_workflow(
    project_id: str,
    run_id: str,
    approved: bool,
    feedback: str = "",
) -> dict:
    """Resume a saved workflow after plan approval or a revision request."""
    on_progress = _build_progress_callback(project_id, run_id)
    return await _resume_workflow_async(
        project_id=project_id,
        run_id=run_id,
        approved=approved,
        feedback=feedback,
        on_progress=on_progress,
    )

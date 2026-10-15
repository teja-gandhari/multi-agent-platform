
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from app.database.session import SessionLocal
from app.models.agent_message import AgentMessage
from app.services.redis_service import publish_project_event

WORKFLOW_ROOT = (
    Path(__file__).resolve().parents[3] / "nexuxai_workflow"
)

if not WORKFLOW_ROOT.is_dir():
    raise RuntimeError(
        f"LangGraph workflow directory not found: {WORKFLOW_ROOT}"
    )

workflow_path = str(WORKFLOW_ROOT)

if workflow_path not in sys.path:
    sys.path.insert(0, workflow_path)

from workflow import run_workflow_async as _run_workflow_async


def persist_agent_event(run_id: str, event: dict) -> None:
    """Save one workflow progress event in its own database session."""
    db = SessionLocal()

    try:
        db.add(
            AgentMessage(
                run_id=UUID(run_id),
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


async def run_nexus_workflow(
    project_id: str,
    user_request: str,
    run_id: str,
) -> dict:
    """Run NexusAI, persist progress events, and publish them through Redis."""

    loop = asyncio.get_running_loop()

    def on_progress(event: dict) -> None:
        event_json = json.dumps(event)

        # The callback may run in the workflow's worker thread.
        future = asyncio.run_coroutine_threadsafe(
            asyncio.to_thread(
                persist_agent_event,
                run_id,
                event,
            ),
            loop,
        )
        future.result()

        publish_future = asyncio.run_coroutine_threadsafe(
            asyncio.to_thread(
                publish_project_event,
                project_id,
                event_json,
            ),
            loop,
        )
        publish_future.result()

    return await _run_workflow_async(
        project_id=project_id,
        user_request=user_request,
        on_progress=on_progress,
    )

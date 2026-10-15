"""Host-backend integration facade for the existing LangGraph workflow."""
from concurrent.futures import Future
from typing import Any, Callable
from workflow import (
    run_workflow as _run_workflow,
    run_workflow_async as _run_workflow_async,
    submit_workflow_background as _submit_workflow_background,
)

ProgressCallback = Callable[[dict[str, Any]], Any]

def run_workflow(project_id: str, user_request: str, on_progress: ProgressCallback | None = None) -> dict[str, Any]:
    """Run synchronously; use only from a worker/background thread in async FastAPI."""
    return _run_workflow(project_id, user_request, on_progress=on_progress)

async def run_workflow_async(project_id: str, user_request: str, on_progress: ProgressCallback | None = None) -> dict[str, Any]:
    """Run without blocking the FastAPI event loop; returns final result when done."""
    return await _run_workflow_async(project_id, user_request, on_progress=on_progress)

def submit_workflow_background(project_id: str, user_request: str, on_progress: ProgressCallback | None = None) -> Future:
    """Submit a background run and return a Future immediately."""
    return _submit_workflow_background(project_id, user_request, on_progress=on_progress)

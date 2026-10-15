
import argparse
import asyncio
import contextvars
import inspect
import re
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.coder import coder_agent
from agents.developer import developer_agent
from agents.planner import planner_agent
from agents.researcher import researcher_agent
from agents.reviewer import reviewer_agent
from agents.runner import runner, stop_application
from agents.tester import tester
from services import llm


MAX_CODER_ATTEMPTS = 3

PROJECT_CONTEXT = """
Generated application: frontend-only HTML, CSS, and JavaScript.
Do not create a generated-app backend, API server, or database.
The NexusAI orchestration and LLM service run in Python internally.
Use browser-side interactions and optional localStorage for prototype state.
Do not use Flutter or Dart. Application features come from the user request.
""".strip()


_progress_callback: contextvars.ContextVar[Any | None] = contextvars.ContextVar("nexusai_progress_callback", default=None)
_progress_loop: contextvars.ContextVar[Any | None] = contextvars.ContextVar("nexusai_progress_loop", default=None)


def _emit_progress(project_id: str, agent: str, status: str, message: str, **extra: Any) -> None:
    """Emit a JSON-serializable progress event without coupling to FastAPI/Redis."""
    callback = _progress_callback.get()
    if callback is None:
        return
    event = {"project_id": project_id, "agent": agent, "status": status, "message": message, **extra}
    try:
        result = callback(event)
        if inspect.isawaitable(result):
            loop = _progress_loop.get()
            if loop is not None and loop.is_running():
                # Run async Redis/WebSocket publisher on the host event loop.
                asyncio.run_coroutine_threadsafe(result, loop).result()
            else:
                asyncio.run(result)
    except Exception as exc:
        # Progress transport failures must not fail the actual generation.
        print(f"[Progress callback warning] {type(exc).__name__}: {exc}")


def _progress_node(agent: str, fn):
    """Wrap a node to emit in-progress and terminal status events."""
    def wrapped(state: WorkflowState) -> dict:
        project_id = str(state.get("project_id", ""))
        attempt = state.get("revision_count", 0)
        if agent == "coder" and attempt:
            _emit_progress(project_id, agent, "retry", f"Coder retry attempt {attempt + 1} started", attempt=attempt + 1)
        _emit_progress(project_id, agent, "in_progress", f"{agent.title()} started", attempt=(attempt + 1 if agent == "coder" else (attempt or None)))
        try:
            update = fn(state)
            update = update if isinstance(update, dict) else {}
            status_keys = {
                "planner": ("planner_status",), "researcher": ("research_status",),
                "developer": ("developer_status",), "coder": ("coder_status",),
                "tester": ("test_status",), "reviewer": ("review_status",),
                "runner": ("runner_status",), "finish": ("workflow_status",),
            }
            raw_status = next((update.get(k) for k in status_keys.get(agent, ()) if update.get(k)), "COMPLETED")
            normalized = str(raw_status).upper()
            failed = normalized in {"FAILED", "NEEDS_REVISION", "UNKNOWN"} or (agent == "tester" and normalized != "PASSED") or (agent == "reviewer" and normalized != "APPROVED") or (agent == "runner" and normalized != "RUNNING") or (agent == "finish" and normalized != "COMPLETED")
            event_status = "failed" if failed else "completed"
            message = (f"{agent.title()} failed" if failed else f"{agent.title()} completed")
            if agent == "tester" and not failed: message = "Tester passed frontend checks"
            if agent == "reviewer" and not failed: message = "Reviewer approved the generated UI"
            if agent == "runner" and not failed: message = "Generated UI is running"
            if agent == "finish": message = f"Workflow {normalized.lower()}"
            _emit_progress(project_id, agent, event_status, message, result_status=normalized)
            return update
        except Exception as exc:
            _emit_progress(project_id, agent, "failed", f"{agent.title()} failed: {type(exc).__name__}: {exc}")
            raise
    return wrapped


class WorkflowState(TypedDict, total=False):
    project_id: str
    user_request: str
    project_context: str

    plan: Any
    planner_status: str
    planner_error: str

    research: Any
    research_output: Any
    research_status: str
    research_error: str

    developer_output: Any
    developer_status: str
    developer_error: str

    coder_output: Any
    coder_status: str
    coder_error: str
    coder_error_code: str
    coder_retryable: bool
    revision_count: int

    test_result: Any
    test_status: str
    test_error: str

    review: Any
    review_status: str
    review_feedback: str

    runner_result: Any
    runner_status: str
    application_url: str

    failure_details: str
    workflow_status: str
    error_message: str
    llm_usage: dict


def result_status(result: Any, *keys: str) -> str:
    """Extract a normalized status from an agent result."""
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if value is not None and str(value).strip():
                return str(value).strip().upper()

        return "UNKNOWN"

    if result is None:
        return "UNKNOWN"

    return str(result).strip().upper()


def result_error(result: Any) -> str:
    """Extract error information from different agent result formats."""
    if not isinstance(result, dict):
        return str(result or "No error details were returned.")

    messages = []

    error_keys = (
        "error",
        "errors",
        "message",
        "explanation",
        "planner_error",
        "research_error",
        "developer_error",
        "coder_error",
        "test_error",
        "review_feedback",
        "runner_error",
        "details",
    )

    for key in error_keys:
        value = result.get(key)

        if isinstance(value, str) and value.strip():
            messages.append(value.strip())

        elif isinstance(value, (list, tuple)):
            messages.extend(str(item) for item in value if item)

        elif isinstance(value, dict):
            messages.append(str(value))

    return "\n".join(dict.fromkeys(messages)) or (
        "The agent did not provide error details."
    )


def safe_text(value: Any) -> str:
    """Convert agent output into readable text."""
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    return str(value)


def planner_node(state: WorkflowState) -> dict:
    print("\n" + "=" * 60 + "\nPLANNER\n" + "=" * 60)

    try:
        result = planner_agent(dict(state))
        status = result_status(result, "planner_status", "status")
        plan = result.get("plan", "") if isinstance(result, dict) else ""

        if status == "COMPLETED" and plan:
            return {
                "plan": plan,
                "planner_status": "COMPLETED",
                "planner_error": "",
                "error_message": "",
            }

        error = result_error(result)

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    print(f"[Planner] FAILED: {error}")

    return {
        "planner_status": "FAILED",
        "planner_error": error,
        "error_message": f"Planner failed: {error}",
    }


def planner_router(state: WorkflowState) -> str:
    return (
        "researcher"
        if state.get("planner_status") == "COMPLETED"
        else "finish"
    )


def researcher_node(state: WorkflowState) -> dict:
    print("\n" + "=" * 60 + "\nRESEARCHER\n" + "=" * 60)

    try:
        result = researcher_agent(dict(state))
        status = result_status(result, "research_status", "status")

        research = ""
        if isinstance(result, dict):
            research = (
                result.get("research_output")
                or result.get("research_result")
                or result.get("research", "")
            )

        if status == "COMPLETED" and research:
            return {
                "research": research,
                "research_output": research,
                "research_status": "COMPLETED",
                "research_error": "",
                "error_message": "",
            }

        error = result_error(result)

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    print(f"[Researcher] FAILED: {error}")

    return {
        "research_status": "FAILED",
        "research_error": error,
        "error_message": f"Researcher failed: {error}",
    }


def researcher_router(state: WorkflowState) -> str:
    return (
        "developer"
        if state.get("research_status") == "COMPLETED"
        else "finish"
    )


def developer_node(state: WorkflowState) -> dict:
    print("\n" + "=" * 60 + "\nDEVELOPER / ARCHITECT\n" + "=" * 60)

    try:
        result = developer_agent(dict(state))
        status = result_status(result, "developer_status", "status")

        specification = ""
        if isinstance(result, dict):
            specification = (
                result.get("developer_output")
                or result.get("developer_result")
                or ""
            )

        if status == "COMPLETED" and specification:
            return {
                "developer_output": specification,
                "developer_status": "COMPLETED",
                "developer_error": "",
                "error_message": "",
            }

        error = result_error(result)

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    print(f"[Developer] FAILED: {error}")

    return {
        "developer_status": "FAILED",
        "developer_error": error,
        "error_message": f"Developer failed: {error}",
    }


def developer_router(state: WorkflowState) -> str:
    return (
        "coder"
        if state.get("developer_status") == "COMPLETED"
        else "finish"
    )


def coder_node(state: WorkflowState) -> dict:
    print("\n" + "=" * 60 + "\nCODER\n" + "=" * 60)

    attempt = int(state.get("revision_count", 0)) + 1
    print(f"[Workflow] Coder attempt {attempt}/{MAX_CODER_ATTEMPTS}")

    coder_state = {
        **state,
        "revision_count": attempt,
        "project_context": (
            state.get("project_context") or PROJECT_CONTEXT
        ),
    }

    try:
        result = coder_agent(coder_state)
        status = result_status(result, "coder_status", "status")

        if status == "COMPLETED":
            error, code, retryable = "", "", False
        else:
            error = result_error(result)
            code = str(result.get("coder_error_code", "")) if isinstance(result, dict) else ""
            # The Coder decides whether another attempt can help.
            retryable = bool(result.get("coder_retryable", False)) if isinstance(result, dict) else False

    except Exception as exc:
        traceback.print_exc()
        result = {}
        status = "FAILED"
        error = f"{type(exc).__name__}: {exc}"
        code = "INTERNAL"
        retryable = False

    print(f"[Coder] Status: {status}")

    if error:
        print(f"[Coder] Error: {error}")

    return {
        "coder_output": result,
        "coder_status": status,
        "coder_error": error,
        "coder_error_code": code,
        "coder_retryable": retryable,
        "revision_count": attempt,
        "failure_details": error,
        "error_message": error,
    }


def coder_router(state: WorkflowState) -> str:
    if state.get("coder_status") == "COMPLETED":
        return "tester"

    if (
        state.get("coder_retryable", False)
        and int(state.get("revision_count", 0)) < MAX_CODER_ATTEMPTS
    ):
        return "coder"

    return "finish"


def tester_node(state: WorkflowState) -> dict:
    print("\n" + "=" * 60 + "\nTESTER\n" + "=" * 60)

    try:
        result = tester(project_id=state["project_id"])
        status = result_status(result, "status", "overall")

        error = "" if status == "PASSED" else result_error(result)

    except Exception as exc:
        result = {
            "status": "FAILED",
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
        status = "FAILED"
        error = result_error(result)

    print(f"[Tester] Status: {status}")

    if status != "PASSED":
        print(f"[Tester] Error: {error}")

    return {
        "test_result": result,
        "test_status": status,
        "test_error": error,
        "failure_details": (
            "" if status == "PASSED"
            else "Generated application failed testing.\n" + error
        ),
        "error_message": (
            "" if status == "PASSED" else error
        ),
    }


def tester_router(state: WorkflowState) -> str:
    if state.get("test_status") == "PASSED":
        return "reviewer"

    # Infrastructure problems (venv, pip/network) cannot be fixed by
    # regenerating code. Never decide this by searching error text.
    test_result = state.get("test_result")
    if isinstance(test_result, dict) and test_result.get("repairable") is False:
        return "finish"

    if int(state.get("revision_count", 0)) < MAX_CODER_ATTEMPTS:
        return "coder"

    return "finish"


def reviewer_node(state: WorkflowState) -> dict:
    print("\n" + "=" * 60 + "\nREVIEWER\n" + "=" * 60)

    # The Reviewer expects separate keyword arguments.
    coder_result = state.get("coder_output", {})

    if not isinstance(coder_result, dict):
        coder_result = {"output": safe_text(coder_result)}

    # The Reviewer implementation checks coder_output["status"].
    coder_result = {
        **coder_result,
        "status": state.get("coder_status", "UNKNOWN"),
    }

    try:
        result = reviewer_agent(
            user_request=state.get("user_request", ""),
            project_context=state.get("project_context", PROJECT_CONTEXT),
            plan=state.get("plan", ""),
            research=state.get("research_output", ""),
            developer_output=state.get("developer_output", ""),
            coder_output=coder_result,
            test_result=state.get("test_result", {}),
            project_id=state.get("project_id"),
        )

        decision = result_status(
            result, "decision", "review_status", "status"
        )

        feedback = ""
        if isinstance(result, dict):
            feedback = safe_text(
                result.get("explanation")
                or result.get("review_feedback")
                or ""
            )

            problems = result.get("problems", [])
            if problems:
                feedback += "\n" + "\n".join(
                    str(problem) for problem in problems
                )

    except Exception as exc:
        decision = "NEEDS_REVISION"
        feedback = f"{type(exc).__name__}: {exc}"
        result = {
            "decision": decision,
            "explanation": feedback,
        }

    print(f"[Reviewer] Decision: {decision}")

    approved = decision == "APPROVED"

    return {
        "review": result,
        "review_status": decision,
        "review_feedback": feedback,
        "failure_details": (
            "" if approved
            else "Reviewer requested changes.\n" + feedback
        ),
        "error_message": "" if approved else feedback,
    }


def review_router(state: WorkflowState) -> str:
    if state.get("review_status") == "APPROVED":
        return "runner"

    if int(state.get("revision_count", 0)) < MAX_CODER_ATTEMPTS:
        return "coder"

    return "finish"


def runner_node(state: WorkflowState) -> dict:
    print("\n" + "=" * 60 + "\nRUNNER\n" + "=" * 60)

    try:
        result = runner(project_id=state["project_id"])
        status = result_status(result, "status")

        application_url = ""
        backend_url = ""

        if isinstance(result, dict):
            application_url = (
                result.get("frontend_url")
                or result.get("application_url")
                or result.get("url")
                or ""
            )
            backend_url = result.get("backend_url", "")

        if status == "RUNNING" and not application_url:
            status = "FAILED"
            error = (
                "Runner reported RUNNING but did not return an "
                "application URL."
            )
        else:
            error = "" if status == "RUNNING" else result_error(result)

    except Exception as exc:
        result = {}
        status = "FAILED"
        application_url = ""
        backend_url = ""
        error = f"{type(exc).__name__}: {exc}"

    print(f"[Runner] Status: {status}")

    if error:
        print(f"[Runner] Error: {error}")

    return {
        "runner_result": result,
        "runner_status": status,
        "application_url": application_url if status == "RUNNING" else "",
        "error_message": error,
    }


def runner_router(state: WorkflowState) -> str:
    return "finish"


def finish_node(state: WorkflowState) -> dict:
    print("\n" + "=" * 60 + "\nWORKFLOW FINISHED\n" + "=" * 60)

    statuses = {
        "Planner": state.get("planner_status", "UNKNOWN"),
        "Researcher": state.get("research_status", "UNKNOWN"),
        "Developer": state.get("developer_status", "UNKNOWN"),
        "Coder": state.get("coder_status", "UNKNOWN"),
        "Tester": state.get("test_status", "UNKNOWN"),
        "Reviewer": state.get("review_status", "UNKNOWN"),
        "Runner": state.get("runner_status", "UNKNOWN"),
    }

    successful = (
        statuses["Planner"] == "COMPLETED"
        and statuses["Researcher"] == "COMPLETED"
        and statuses["Developer"] == "COMPLETED"
        and statuses["Coder"] == "COMPLETED"
        and statuses["Tester"] == "PASSED"
        and statuses["Reviewer"] == "APPROVED"
        and statuses["Runner"] == "RUNNING"
        and bool(state.get("application_url"))
    )

    workflow_status = "COMPLETED" if successful else "FAILED"

    error_message = ""
    if not successful:
        error_message = (
            state.get("error_message", "")
            or state.get("failure_details", "")
            or (
                "Workflow did not complete successfully. "
                + "; ".join(
                    f"{name}={status}"
                    for name, status in statuses.items()
                )
            )
        )

    print(f"Workflow status: {workflow_status}")
    print(f"Project ID: {state.get('project_id', '')}")
    print(f"Coder attempts: {state.get('revision_count', 0)}")
    usage = llm.usage_summary()
    print(
        f"LLM requests: {usage['requests']} "
        f"({usage['failed']} failed), tokens in/out: "
        f"{usage['prompt_tokens']}/{usage['completion_tokens']}"
    )

    if successful:
        print(f"Application: {state.get('application_url', '')}")
        runner_result = state.get("runner_result", {})
        if isinstance(runner_result, dict):
            backend_url = runner_result.get("backend_url")
            if backend_url:
                print(f"Backend: {backend_url}")
    else:
        print("Application: Not confirmed running")
        print(f"Reason: {error_message}")

    return {
        "workflow_status": workflow_status,
        "error_message": error_message,
        "llm_usage": usage,
    }


# Build the LangGraph workflow.
builder = StateGraph(WorkflowState)

builder.add_node("planner", _progress_node("planner", planner_node))
builder.add_node("researcher", _progress_node("researcher", researcher_node))
builder.add_node("developer", _progress_node("developer", developer_node))
builder.add_node("coder", _progress_node("coder", coder_node))
builder.add_node("tester", _progress_node("tester", tester_node))
builder.add_node("reviewer", _progress_node("reviewer", reviewer_node))
builder.add_node("runner", _progress_node("runner", runner_node))
builder.add_node("finish", _progress_node("finish", finish_node))

builder.add_edge(START, "planner")

builder.add_conditional_edges(
    "planner",
    planner_router,
    {
        "researcher": "researcher",
        "finish": "finish",
    },
)

builder.add_conditional_edges(
    "researcher",
    researcher_router,
    {
        "developer": "developer",
        "finish": "finish",
    },
)

builder.add_conditional_edges(
    "developer",
    developer_router,
    {
        "coder": "coder",
        "finish": "finish",
    },
)

builder.add_conditional_edges(
    "coder",
    coder_router,
    {
        "tester": "tester",
        "coder": "coder",
        "finish": "finish",
    },
)

builder.add_conditional_edges(
    "tester",
    tester_router,
    {
        "reviewer": "reviewer",
        "coder": "coder",
        "finish": "finish",
    },
)

builder.add_conditional_edges(
    "reviewer",
    review_router,
    {
        "runner": "runner",
        "coder": "coder",
        "finish": "finish",
    },
)

builder.add_conditional_edges(
    "runner",
    runner_router,
    {"finish": "finish"},
)

builder.add_edge("finish", END)

app = builder.compile()


def make_project_id(user_request: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", user_request.lower()).strip("_")
    slug = (slug[:35] or "application").strip("_")
    return f"{slug}_{uuid.uuid4().hex[:8]}"


def build_initial_state(user_request: str, project_id: str | None = None) -> WorkflowState:
    """Build workflow state, preserving a project ID supplied by the host backend."""
    if not isinstance(user_request, str) or not user_request.strip():
        raise ValueError("user_request must be a non-empty string.")
    resolved_project_id = str(project_id).strip() if project_id is not None else make_project_id(user_request)
    if not resolved_project_id or any(part in resolved_project_id for part in ("/", "\\", "..")):
        raise ValueError("project_id must be a non-empty path-safe identifier.")
    return {
        "project_id": resolved_project_id,
        "user_request": user_request,
        "project_context": PROJECT_CONTEXT,
        "plan": "",
        "planner_status": "PENDING",
        "research": "",
        "research_output": "",
        "research_status": "PENDING",
        "developer_output": "",
        "developer_status": "PENDING",
        "coder_output": {},
        "coder_status": "PENDING",
        "coder_retryable": True,
        "test_result": {},
        "test_status": "PENDING",
        "review": {},
        "review_status": "PENDING",
        "runner_result": {},
        "runner_status": "PENDING",
        "application_url": "",
        "revision_count": 0,
        "workflow_status": "STARTING",
        "error_message": "",
        "failure_details": "",
    }


def _public_result(state: dict[str, Any], project_id: str) -> dict[str, Any]:
    """Return a stable integration result without removing the original state fields."""
    return {
        **state,
        "project_id": project_id,
        "workflow_status": state.get("workflow_status", "FAILED"),
        "application_url": state.get("application_url", ""),
        "revision_count": int(state.get("revision_count", 0) or 0),
        "plan": state.get("plan", ""),
        "research_output": state.get("research_output", ""),
        "developer_output": state.get("developer_output", ""),
        "test_result": state.get("test_result", {}),
        "review": state.get("review", {}),
        "runner_result": state.get("runner_result", {}),
        "error_message": state.get("error_message", ""),
    }


def run_workflow(project_id: str, user_request: str, on_progress=None) -> dict[str, Any]:
    """Synchronously run the existing graph for a host-owned project ID.

    `on_progress` is an optional callable receiving JSON-serializable event dicts.
    This function is synchronous; async FastAPI handlers should call
    `await run_workflow_async(...)` or use a background task.
    """
    state = build_initial_state(user_request=user_request, project_id=project_id)
    token = _progress_callback.set(on_progress)
    _emit_progress(project_id, "workflow", "in_progress", "Workflow started")
    try:
        final_state = app.invoke(state, config={"recursion_limit": 60})
        result = _public_result(final_state, project_id)
        _emit_progress(project_id, "workflow", "completed" if result["workflow_status"] == "COMPLETED" else "failed", f"Workflow {result['workflow_status'].lower()}", result_status=result["workflow_status"], application_url=result.get("application_url", ""), error_message=result.get("error_message", ""))
        return result
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _emit_progress(project_id, "workflow", "failed", "Workflow execution failed", error_message=message)
        return _public_result({"workflow_status": "FAILED", "error_message": message, "application_url": "", "revision_count": 0}, project_id)
    finally:
        _progress_callback.reset(token)


async def run_workflow_async(project_id: str, user_request: str, on_progress=None) -> dict[str, Any]:
    """Async-safe wrapper; runs the synchronous graph in a worker thread.

    Awaiting this returns the final result but does not block the event loop.
    For an HTTP endpoint that must return immediately, use submit_workflow_background.
    """
    loop = asyncio.get_running_loop()
    token = _progress_loop.set(loop)
    try:
        return await asyncio.to_thread(run_workflow, project_id, user_request, on_progress)
    finally:
        _progress_loop.reset(token)


_BACKGROUND_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="nexusai-workflow")


def submit_workflow_background(project_id: str, user_request: str, on_progress=None) -> Future:
    """Submit generation and return immediately with a Future handle.

    The host FastAPI service can return HTTP 202 immediately, store the job/future
    reference in its own job manager, and persist the eventual result. For
    multi-process production deployment, use the host's durable task queue instead.
    """
    return _BACKGROUND_EXECUTOR.submit(run_workflow, project_id, user_request, on_progress)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NexusAI multi-agent app generator")
    parser.add_argument("request", nargs="*", help="what to build (prompted if omitted)")
    parser.add_argument("--detach", action="store_true",
                        help="leave the generated app running after this command exits")
    parser.add_argument("--stop", action="store_true",
                        help="stop the application started by a previous run and exit")
    args = parser.parse_args(argv)

    if args.stop:
        print(stop_application()["message"])
        return 0

    user_request = " ".join(args.request).strip() or input(
        "\nEnter your project request: "
    ).strip()

    if not user_request:
        print("No project request provided.")
        return 1

    initial_state = build_initial_state(user_request)
    print(f"\nProject ID: {initial_state['project_id']}")

    try:
        final_state = app.invoke(initial_state, config={"recursion_limit": 60})
    except Exception as exc:
        traceback.print_exc()
        print("\nWorkflow execution failed.")
        print(f"{type(exc).__name__}: {exc}")
        return 1

    print("\n" + "=" * 60 + "\nFINAL RESULT\n" + "=" * 60)
    print("Status:", final_state.get("workflow_status", "UNKNOWN"))
    print("Attempts:", final_state.get("revision_count", 0))

    if final_state.get("workflow_status") != "COMPLETED":
        if final_state.get("error_message"):
            print("Reason:", final_state["error_message"])
        return 1

    print("Application:", final_state.get("application_url", ""))

    if args.detach:
        print("Left running. Stop it with: python main.py --stop")
        return 0

    print("\nPress Ctrl+C to stop the application.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n" + stop_application(final_state.get("project_id"))["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Coder agent: turns the Developer's specification into real project files.

The model writes files only through a ``write_file`` tool. This module owns
the tool-calling cycle:

    request -> tool_calls -> execute each call -> tool results -> request ...

It reports COMPLETED only if every required file exists on disk, and it
reports partial progress accurately when it cannot finish.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from services import llm
from services.llm import LLMError, explain

BASE_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = BASE_DIR / "generated_projects"

MAX_ROUNDS = 16          # model requests per attempt
MAX_NUDGES = 2           # times we re-prompt a model that ignored the tool
MAX_REWRITES = 4         # times one path may be rewritten per attempt

REQUIRED_FILES = [
    "index.html",
    "style.css",
    "script.js",
    "README.md",
    ".gitignore",
]

# Platform-managed frontend-only project files.
PLATFORM_MANAGED = {".gitignore"}

CONTEXT_FILES = ["index.html", "style.css", "script.js", "README.md"]

SPEC_LIMIT = 30_000
PLAN_LIMIT = 8_000
RESEARCH_LIMIT = 8_000
FAILURE_LIMIT = 8_000
CONTEXT_FILES_LIMIT = 40_000

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write one complete source file inside the generated project. "
                "Replaces the file if it already exists."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path, e.g. index.html",
                    },
                    "content": {
                        "type": "string",
                        "description": "The complete file content.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    }
]

SYSTEM_PROMPT = """
You are the Coder Agent in a general-purpose FRONTEND-ONLY application generator.
Generate the UI requested by the user as static HTML, CSS, and JavaScript.

Mandatory rules:
1. Use write_file to write complete files. Write only project files.
2. The generated application must be frontend-only. Do not create a backend,
   FastAPI app, API endpoints, database, database schema, migrations, Docker,
   Docker Compose, or backend requirements.
3. Required files are index.html, style.css, script.js, README.md, and .gitignore.
4. Use local browser behavior for interactions. Use localStorage only when
   persistence in this browser is useful. Clearly label simulated/demo data.
5. Do not require remote APIs, external credentials, or paid services. Prefer
   locally implemented/demo behavior. Remote image URLs are optional; use CSS
   or inline SVG when practical.
6. index.html must link style.css and script.js using relative paths.
7. Make the UI responsive, accessible, and visually polished. Implement working
   navigation, filters, forms, buttons, dialogs, and state changes appropriate
   to the user's request, not just a static screenshot.
8. Do not write .env files or secrets. The platform creates .gitignore.
9. README.md should explain the generated UI and how to run it with
   `python -m http.server 8080` from the generated project directory.
10. If repairing, use the tester/reviewer failure details and modify the
    relevant existing frontend files. Preserve project-specific features.
""".strip()


# --------------------------------------------------------------------------
# Paths and files
# --------------------------------------------------------------------------

def get_project_dir(project_id: str) -> Path:
    if not isinstance(project_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", project_id
    ):
        raise ValueError("Invalid project ID.")

    root = GENERATED_DIR.resolve()
    project_dir = (root / project_id).resolve()

    if not project_dir.is_relative_to(root):
        raise ValueError("Project path escapes generated_projects.")

    return project_dir


def normalize_relative(relative_path: str) -> str:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("A relative file path is required.")
    text = relative_path.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def safe_path(project_dir: Path, relative_path: str) -> Path:
    text = normalize_relative(relative_path)
    path = Path(text)

    if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", text):
        raise ValueError("Invalid relative file path.")

    root = project_dir.resolve()
    target = (root / path).resolve()

    if not target.is_relative_to(root):
        raise ValueError("Target path escapes the project directory.")

    return target


def write_file(project_dir: Path, relative_path: str, content: str) -> str:
    if not isinstance(content, str):
        raise ValueError("File content must be a string.")

    target = safe_path(project_dir, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")

    normalized = normalize_relative(relative_path)
    print(f"[Coder] Wrote: {normalized}")
    return normalized


def get_existing_files(project_dir: Path) -> list[str]:
    ignored = {"__pycache__", ".pytest_cache", ".git", "node_modules", ".venv", "venv"}

    if not project_dir.exists():
        return []

    return sorted(
        path.relative_to(project_dir).as_posix()
        for path in project_dir.rglob("*")
        if path.is_file()
        and not any(part in ignored for part in path.relative_to(project_dir).parts)
        and not path.name.endswith(".log")
    )


def get_missing_files(project_dir: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (project_dir / name).is_file()]


def create_infrastructure_files(project_dir: Path, user_request: str) -> list[str]:
    """Create deterministic support files for a static frontend project."""
    files = {
        ".gitignore": "__pycache__/\n*.py[cod]\n.env\n.venv/\nvenv/\n.pytest_cache/\nnode_modules/\n*.log\n",
        "README.md": (
            "# Generated Frontend Application\n\n"
            f"## Request\n{user_request}\n\n"
            "## Stack\n- HTML\n- CSS\n- JavaScript\n\n"
            "## Run locally\nFrom this directory, run:\n\n"
            "```bash\npython -m http.server 8080\n```\n\n"
            "Then open http://127.0.0.1:8080 in your browser.\n"
            "This generated prototype does not require a separate API backend or database.\n"
        ),
    }
    written = []
    for relative_path, content in files.items():
        target = safe_path(project_dir, relative_path)
        if target.exists():
            continue
        write_file(project_dir, relative_path, content)
        written.append(relative_path)
    return written


# --------------------------------------------------------------------------
# Prompt construction
# --------------------------------------------------------------------------

def _text(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _clip(text: str, limit: int, tail: int = 0) -> str:
    """Shorten text, keeping the head and (optionally) a tail."""
    text = text.strip()
    if len(text) <= limit:
        return text
    if tail:
        head = max(limit - tail, 0)
        return text[:head] + "\n...[truncated]...\n" + text[-tail:]
    return text[:limit] + "\n...[truncated]..."


def context_files_block(project_dir: Path) -> str:
    """Current contents of the key project files, within a size budget."""
    blocks = []
    budget = CONTEXT_FILES_LIMIT

    for name in CONTEXT_FILES:
        path = project_dir / name
        if not path.is_file() or budget <= 0:
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        content = _clip(content, min(budget, 14_000))
        budget -= len(content)
        blocks.append(f"--- FILE: {name} ---\n{content}\n--- END FILE ---")

    return "\n\n".join(blocks) if blocks else "(no files written yet)"


def build_prompt(
    project_id: str, user_request: str, context: dict | None = None
) -> tuple[str, bool]:
    """Return (prompt, repair_mode)."""
    project_dir = get_project_dir(project_id)
    context = context or {}

    existing = get_existing_files(project_dir)
    missing = get_missing_files(project_dir)
    failure_details = _text(context.get("failure_details")).strip()

    # All required files present + failure details => tests/review failed.
    repair_mode = bool(failure_details) and not missing

    spec = _text(context.get("developer_output") or context.get("developer_result"))
    plan = _text(context.get("plan") or context.get("planner_output"))
    research = _text(
        context.get("research_output") or context.get("research_result")
        or context.get("research")
    )

    sections = [
        f"Project ID: {project_id}",
        f"USER REQUEST:\n{user_request}",
    ]

    project_context = _text(context.get("project_context")).strip()
    if project_context:
        sections.append(f"PROJECT CONTEXT:\n{project_context}")

    if spec.strip():
        sections.append(
            "IMPLEMENTATION SPECIFICATION (from the Developer agent; follow it "
            "unless it conflicts with the rules above):\n" + _clip(spec, SPEC_LIMIT)
        )
    else:
        # Developer output unavailable: fall back to the earlier stages.
        if plan.strip():
            sections.append("PLAN:\n" + _clip(plan, PLAN_LIMIT))
        if research.strip():
            sections.append("RESEARCH BRIEF:\n" + _clip(research, RESEARCH_LIMIT))

    if repair_mode:
        sections.append(
            "REPAIR MODE\n"
            "All required files exist but the application failed verification.\n"
            "Fix the actual cause, preserve working features, and write complete "
            "corrected files.\n\n"
            "FAILURE DETAILS:\n" + _clip(failure_details, FAILURE_LIMIT, tail=6_000)
        )
        sections.append("CURRENT FILES:\n" + context_files_block(project_dir))
    else:
        note = "GENERATION MODE\nImplement the requested application."
        if failure_details:
            note += (
                "\nA previous attempt stopped early: "
                + _clip(failure_details, 1_500)
            )
        sections.append(note)
        if existing and any(name in CONTEXT_FILES for name in existing):
            sections.append(
                "FILES ALREADY WRITTEN (keep them consistent):\n"
                + context_files_block(project_dir)
            )

    sections.append(
        "Required files still missing:\n"
        + ("\n".join(f"- {m}" for m in missing) if missing else "(none)")
    )
    sections.append(
        "Existing project files:\n"
        + ("\n".join(f"- {f}" for f in existing) if existing else "(none)")
    )
    sections.append(
        "Use write_file now. Write complete files. Do not claim testing succeeded."
    )

    return "\n\n".join(sections), repair_mode


def make_prompt(
    project_id: str, user_request: str, context: dict | None = None
) -> str:
    return build_prompt(project_id, user_request, context)[0]


# --------------------------------------------------------------------------
# Tool-calling cycle
# --------------------------------------------------------------------------

def assistant_record(message) -> dict:
    """Serialize the assistant turn for the next request.

    ``model_dump`` keeps provider-specific fields on tool calls (Gemini 3 puts
    its thought signature in ``tool_calls[].extra_content``), which the API
    requires to be sent back unchanged.
    """
    record = message.model_dump(exclude_none=True)
    record["role"] = "assistant"
    for output_only in ("annotations", "refusal", "audio", "function_call"):
        record.pop(output_only, None)
    if not record.get("tool_calls"):
        record["content"] = message.content or ""
    return record


def validate_and_write(
    project_dir: Path,
    relative_path: str,
    content,
    write_counts: dict[str, int],
) -> str:
    path = normalize_relative(relative_path)

    if path in PLATFORM_MANAGED:
        raise ValueError(
            f"{path} is managed by the platform and already exists. Do not write it."
        )
    if Path(path).name.startswith(".env"):
        raise ValueError("Never write .env files; read secrets from the environment.")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"Content for {path} is empty. Provide the complete file.")
    if write_counts.get(path, 0) >= MAX_REWRITES:
        raise ValueError(
            f"{path} was already written {MAX_REWRITES} times in this attempt."
        )

    if path.endswith(".py"):
        try:
            ast.parse(content)
        except SyntaxError as exc:
            raise ValueError(
                f"Python syntax error in {path} at line {exc.lineno}: {exc.msg}. "
                "Fix it and write the complete file again."
            ) from exc

    written = write_file(project_dir, path, content)
    write_counts[path] = write_counts.get(path, 0) + 1
    return written


def execute_tool_call(project_dir: Path, tool_call, write_counts: dict[str, int]) -> dict:
    """Run one tool call and return the JSON-serializable result."""
    name = tool_call.function.name

    if name != "write_file":
        return {"ok": False, "error": f"Unknown tool '{name}'. Only write_file exists."}

    raw = tool_call.function.arguments
    try:
        arguments = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "ok": False,
            "error": (
                f"Tool arguments were not valid JSON ({exc}). The reply may have "
                "been cut off. Send a smaller file or write fewer files per reply."
            ),
        }

    if not isinstance(arguments, dict):
        return {"ok": False, "error": "Tool arguments must be a JSON object."}

    try:
        written = validate_and_write(
            project_dir, arguments.get("path"), arguments.get("content"), write_counts
        )
        return {"ok": True, "path": written}
    except Exception as exc:  # noqa: BLE001 - reported back to the model
        return {"ok": False, "error": str(exc)}


def _result(status: str, project_dir: Path, written: list[str], **extra) -> dict:
    return {
        "coder_status": status,
        "coder_missing_files": get_missing_files(project_dir),
        "coder_written_files": sorted(set(written)),
        **extra,
    }


def run_model_loop(project_dir: Path, messages: list[dict], repair_mode: bool) -> dict:
    """Drive the write_file cycle. Returns loop facts; raises LLMError."""
    written: list[str] = []
    write_counts: dict[str, int] = {}
    nudges = 0
    rounds_used = 0
    stop_reason = "rounds_exhausted"

    for round_number in range(1, MAX_ROUNDS + 1):
        rounds_used = round_number
        print(f"[Coder] Model round {round_number}/{MAX_ROUNDS}")

        response = llm.chat("coder", messages, tools=TOOLS)
        choice = response.choices[0]
        message = choice.message
        tool_calls = list(message.tool_calls or [])
        truncated = choice.finish_reason == "length"

        messages.append(assistant_record(message))

        if not tool_calls:
            missing = get_missing_files(project_dir)

            if truncated:
                note = (
                    "Your last reply was cut off by the output limit before any "
                    "tool call completed. Call write_file for ONE file now and keep "
                    "it concise."
                )
            elif repair_mode and written:
                stop_reason = "model_done"
                break
            elif not repair_mode and not missing:
                stop_reason = "model_done"
                break
            else:
                target = missing[0] if missing else "the file that needs fixing"
                note = (
                    "You did not call write_file. Do not just describe code - use "
                    f"the tool now. Next file to write: {target}"
                )

            nudges += 1
            if nudges > MAX_NUDGES:
                stop_reason = "no_tool_calls"
                break
            print(f"[Coder] No tool call; nudging model ({nudges}/{MAX_NUDGES}).")
            messages.append({"role": "user", "content": note})
            continue

        for tool_call in tool_calls:
            outcome = execute_tool_call(project_dir, tool_call, write_counts)
            if outcome.get("ok"):
                written.append(outcome["path"])
            else:
                print(f"[Coder] Tool error: {outcome.get('error')}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": json.dumps(outcome),
                }
            )

        if truncated:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your last reply hit the output limit, so the final file "
                        "may not have been written. Continue with any file that "
                        "is still missing, one file per reply."
                    ),
                }
            )

        if not repair_mode and not get_missing_files(project_dir):
            stop_reason = "all_required_files_present"
            break

    return {"written": written, "rounds": rounds_used, "stop_reason": stop_reason}


# --------------------------------------------------------------------------
# Agent entry point
# --------------------------------------------------------------------------

def coder_agent(state: dict) -> dict:
    """
    LangGraph Coder node.

    Reads: project_id, user_request, developer_output (preferred) or
    plan/research_output, project_context, failure_details (repair).

    Returns a compact dict (not the whole state):
      coder_status          COMPLETED | FAILED
      coder_error           message (empty on success)
      coder_error_code      LLMError code, NO_TOOL_CALLS, INCOMPLETE, NO_CHANGES...
      coder_retryable       whether another attempt can plausibly help
      coder_written_files   files written/created in THIS attempt
      coder_missing_files   required files still absent
    """
    project_id = state.get("project_id")
    user_request = state.get("user_request")

    if not project_id or not user_request:
        return {
            "coder_status": "FAILED",
            "coder_error": "Missing project_id or user_request.",
            "coder_error_code": "BAD_INPUT",
            "coder_retryable": False,
            "coder_written_files": [],
            "coder_missing_files": list(REQUIRED_FILES),
        }

    written: list[str] = []
    project_dir = None
    repair_mode = False

    try:
        project_dir = get_project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        infrastructure_written = create_infrastructure_files(project_dir, user_request)
        written.extend(infrastructure_written)

        prompt, repair_mode = build_prompt(project_id, user_request, state)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        loop = run_model_loop(project_dir, messages, repair_mode)
        written.extend(loop["written"])

    except LLMError as exc:
        message = explain(exc)
        print(f"[Coder] FAILED: {message}")
        return _result(
            "FAILED", project_dir or Path("."), written,
            coder_error=message,
            coder_error_code=exc.code,
            coder_retryable=not exc.fatal,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced, never hidden
        message = f"{type(exc).__name__}: {exc}"
        print(f"[Coder] FAILED (internal): {message}")
        return {
            "coder_status": "FAILED",
            "coder_error": message,
            "coder_error_code": "INTERNAL",
            "coder_retryable": False,
            "coder_written_files": sorted(set(written)),
            "coder_missing_files": [],
        }

    missing = get_missing_files(project_dir)
    model_files = sorted(set(loop["written"]))

    if missing:
        reason = {
            "no_tool_calls": "The model stopped calling write_file.",
            "rounds_exhausted": f"Reached the {MAX_ROUNDS}-request limit.",
        }.get(loop["stop_reason"], "Generation ended early.")
        return _result(
            "FAILED", project_dir, written,
            coder_error=(
                f"Coder did not create all required files. {reason} "
                f"The model wrote {len(model_files)} file(s) this attempt. "
                "Missing: " + ", ".join(missing)
            ),
            coder_error_code="INCOMPLETE",
            coder_retryable=True,
            coder_rounds=loop["rounds"],
        )

    if repair_mode and not model_files:
        return _result(
            "FAILED", project_dir, written,
            coder_error=(
                "Repair attempt made no changes: the model wrote no files, so the "
                "reported failure is unchanged."
            ),
            coder_error_code="NO_CHANGES",
            coder_retryable=True,
            coder_rounds=loop["rounds"],
        )

    # Completion means the required files exist, not that they work.
    print("[Coder] Required files exist. Tester must verify them.")
    return _result(
        "COMPLETED", project_dir, written,
        coder_error="",
        coder_error_code="",
        coder_retryable=False,
        coder_rounds=loop["rounds"],
        coder_stop_reason=loop["stop_reason"],
    )


# Compatibility alias for workflows that use a different node name.
coder = coder_agent

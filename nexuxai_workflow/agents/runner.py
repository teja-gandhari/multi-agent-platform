
"""Launch and stop a generated static frontend; no generated backend."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = BASE_DIR / "generated_projects"

HOST = "127.0.0.1"
DEFAULT_PORT = 8080
STATE_FILE_NAME = ".nexus_running.json"

_CHILDREN: dict[int, subprocess.Popen] = {}


def get_project_dir(project_id: str) -> Path:
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("A valid project_id is required.")

    root = GENERATED_DIR.resolve()
    project_dir = (root / project_id).resolve()

    if not project_dir.is_relative_to(root):
        raise ValueError("Invalid project directory.")

    return project_dir


def _state_path() -> Path:
    return GENERATED_DIR / STATE_FILE_NAME


def port_is_available(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
    except OSError:
        return False


def _find_port(start: int = DEFAULT_PORT, attempts: int = 50) -> int:
    for port in range(start, start + attempts):
        if port_is_available(HOST, port):
            return port

    raise RuntimeError(
        f"No free port found in range {start}-{start + attempts - 1}."
    )


def _alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return f'"{pid}"' in result.stdout
        except (OSError, subprocess.TimeoutExpired):
            return False

    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _terminate_pid(pid: int) -> bool:
    """Stop a recorded process and its descendants where supported."""
    process = _CHILDREN.get(pid)

    try:
        if process is not None:
            if process.poll() is None:
                process.terminate()

                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)

            return True

        if not _alive(pid):
            return False

        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            return result.returncode == 0

        os.kill(pid, 15)
        return True

    except (OSError, subprocess.TimeoutExpired):
        return False

    finally:
        _CHILDREN.pop(pid, None)


def stop_application(project_id: str | None = None) -> dict:
    """Stop the application recorded in the state file."""
    state_path = _state_path()

    if not state_path.is_file():
        return {
            "stopped": [],
            "message": "No running application is recorded.",
        }

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state_path.unlink(missing_ok=True)
        return {
            "stopped": [],
            "message": "Ignored a corrupt state file.",
        }

    recorded_project = state.get("project_id")

    if project_id and recorded_project != project_id:
        return {
            "stopped": [],
            "message": "Recorded application is a different project.",
        }

    stopped = []

    for pid in state.get("pids", []):
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue

        if _terminate_pid(pid):
            stopped.append(pid)

    state_path.unlink(missing_ok=True)

    return {
        "stopped": stopped,
        "project_id": recorded_project,
        "message": f"Stopped {len(stopped)} process(es).",
    }


def runner(
    project_id: str,
    backend_port: int | None = None,
    frontend_port: int | None = None,
) -> dict:
    """
    Start a static HTTP server for a generated frontend.

    backend_port is accepted for compatibility with older callers.
    No backend server is started.
    """
    del backend_port

    try:
        project_dir = get_project_dir(project_id)
    except (ValueError, OSError) as exc:
        return {
            "status": "FAILED",
            "project_id": project_id,
            "frontend_url": None,
            "application_url": None,
            "backend_url": None,
            "errors": str(exc),
        }

    if not project_dir.is_dir():
        return {
            "status": "FAILED",
            "project_id": project_id,
            "frontend_url": None,
            "application_url": None,
            "backend_url": None,
            "errors": f"Project directory does not exist: {project_dir}",
        }

    index_path = project_dir / "index.html"

    if not index_path.is_file():
        return {
            "status": "FAILED",
            "project_id": project_id,
            "frontend_url": None,
            "application_url": None,
            "backend_url": None,
            "errors": f"Missing generated UI: {index_path}",
        }

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    # Release the previous NexusAI run before starting another.
    stop_application()

    if frontend_port is not None:
        if not 1 <= frontend_port <= 65535:
            return {
                "status": "FAILED",
                "project_id": project_id,
                "frontend_url": None,
                "application_url": None,
                "backend_url": None,
                "errors": f"Invalid frontend port: {frontend_port}",
            }

        if not port_is_available(HOST, frontend_port):
            return {
                "status": "FAILED",
                "project_id": project_id,
                "frontend_url": None,
                "application_url": None,
                "backend_url": None,
                "errors": f"Frontend port {frontend_port} is in use.",
            }

        port = frontend_port
    else:
        try:
            port = _find_port()
        except RuntimeError as exc:
            return {
                "status": "FAILED",
                "project_id": project_id,
                "frontend_url": None,
                "application_url": None,
                "backend_url": None,
                "errors": str(exc),
            }

    log_path = project_dir / "frontend_runner.log"

    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "http.server",
                    str(port),
                    "--bind",
                    HOST,
                ],
                cwd=str(project_dir),
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
    except OSError as exc:
        return {
            "status": "FAILED",
            "project_id": project_id,
            "frontend_url": None,
            "application_url": None,
            "backend_url": None,
            "errors": f"Could not start frontend server: {exc}",
        }

    _CHILDREN[process.pid] = process

    # No trailing slash, for consistent API responses.
    url = f"http://{HOST}:{port}"
    deadline = time.monotonic() + 8
    last_error = "Server did not respond."

    while time.monotonic() < deadline:
        if process.poll() is not None:
            last_error = (
                f"Static server exited. Check its log: {log_path}"
            )
            break

        try:
            with urllib.request.urlopen(url + "/", timeout=0.5) as response:
                if response.status == 200:
                    state = {
                        "project_id": project_id,
                        "pids": [process.pid],
                        "frontend_port": port,
                    }

                    try:
                        _state_path().write_text(
                            json.dumps(state, indent=2),
                            encoding="utf-8",
                        )
                    except OSError as exc:
                        _terminate_pid(process.pid)
                        return {
                            "status": "FAILED",
                            "project_id": project_id,
                            "frontend_url": None,
                            "application_url": None,
                            "backend_url": None,
                            "errors": f"Could not save runner state: {exc}",
                        }

                    return {
                        "status": "RUNNING",
                        "project_id": project_id,
                        "frontend_url": url,
                        "application_url": url,
                        "backend_url": None,
                        "frontend_pid": process.pid,
                        "errors": "",
                    }

                last_error = f"Unexpected HTTP status: {response.status}"

        except Exception as exc:
            last_error = str(exc)

        time.sleep(0.2)

    _terminate_pid(process.pid)

    return {
        "status": "FAILED",
        "project_id": project_id,
        "frontend_url": None,
        "application_url": None,
        "backend_url": None,
        "errors": f"Frontend did not respond: {last_error}",
    }


run_application = runner

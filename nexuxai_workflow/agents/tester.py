
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = BASE_DIR / "generated_projects"

REQUIRED_FILES = [
    "index.html",
    "style.css",
    "script.js",
    "README.md",
    ".gitignore",
]


def get_project_dir(project_id: str) -> Path:
    """Resolve a project directory safely."""
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("A valid project_id is required.")

    root = GENERATED_DIR.resolve()
    project_dir = (root / project_id).resolve()

    if not project_dir.is_relative_to(root):
        raise ValueError("Invalid project directory.")

    return project_dir


def _read(path: Path) -> str:
    """Read a text file safely."""
    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def check_frontend(project_dir: Path) -> list[str]:
    """Validate generated HTML, CSS, JavaScript and local assets."""
    errors: list[str] = []

    html_path = project_dir / "index.html"
    css_path = project_dir / "style.css"
    js_path = project_dir / "script.js"

    # Required frontend files must exist before checking their contents.
    for path in (html_path, css_path, js_path):
        if not path.is_file():
            errors.append(f"Missing required file: {path.name}")

    if errors:
        return errors

    html = _read(html_path)
    css = _read(css_path)
    js = _read(js_path)

    # Validate HTML structure.
    if not re.search(r"<html\b", html, re.IGNORECASE):
        errors.append("index.html has no html root element.")

    if not re.search(
        r"""<script\b[^>]*\bsrc\s*=\s*["'](?:\./)?script\.js(?:[?#][^"']*)?["']""",
        html,
        re.IGNORECASE,
    ):
        errors.append("index.html must load script.js.")

    if not re.search(
        r"""<link\b[^>]*\bhref\s*=\s*["'](?:\./)?style\.css(?:[?#][^"']*)?["']""",
        html,
        re.IGNORECASE,
    ):
        errors.append("index.html must load style.css.")

    if not css.strip():
        errors.append("style.css is empty.")

    if not js.strip():
        errors.append("script.js is empty.")

    # Check local assets referenced by src and href.
    references = re.finditer(
        r"""(?:src|href)\s*=\s*["']([^"']+)["']""",
        html,
        re.IGNORECASE,
    )

    ignored_prefixes = (
        "http://",
        "https://",
        "//",
        "#",
        "mailto:",
        "tel:",
        "data:",
        "javascript:",
    )

    for match in references:
        value = match.group(1).strip()

        if not value or value.startswith(ignored_prefixes):
            continue

        if value in {
            "script.js",
            "./script.js",
            "style.css",
            "./style.css",
        }:
            continue

        relative_path = value.split("?", 1)[0].split("#", 1)[0]
        asset_path = (project_dir / relative_path).resolve()

        # Do not allow references to escape the project directory.
        if not asset_path.is_relative_to(project_dir.resolve()):
            errors.append(f"Invalid local asset path: {value}")
            continue

        if not asset_path.is_file():
            errors.append(f"Referenced local asset is missing: {value}")

    # Generated applications should not rely on a separate local API.
    if re.search(
        r"localhost\s*:\s*(8000|5000)"
        r"|127\.0\.0\.1\s*:\s*(8000|5000)"
        r"|/api/",
        js,
        re.IGNORECASE,
    ):
        errors.append(
            "script.js appears to call a separate local API; "
            "frontend-only output is required."
        )

    # JavaScript syntax validation is optional when Node.js is installed.
    node_path = shutil.which("node")

    if node_path:
        try:
            result = subprocess.run(
                [node_path, "--check", str(js_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )

            if result.returncode != 0:
                details = (result.stderr or result.stdout).strip()
                errors.append(
                    "JavaScript syntax error: " + details[:1500]
                )

        except subprocess.TimeoutExpired:
            errors.append("JavaScript syntax check timed out.")
        except OSError as exc:
            errors.append(f"Could not check JavaScript syntax: {exc}")

    return errors


def tester(project_id: str) -> dict:
    """Run the static checks for a generated frontend project."""
    try:
        project_dir = get_project_dir(project_id)
    except (ValueError, OSError) as exc:
        message = str(exc)

        return {
            "status": "FAILED",
            "errors": message,
            "checks": {
                "required_files": {
                    "status": "FAILED",
                    "error": message,
                },
                "frontend": {
                    "status": "SKIPPED",
                    "error": "Project path is invalid.",
                },
            },
            "repairable": False,
            "project_id": project_id,
        }

    if not project_dir.is_dir():
        message = f"Project directory does not exist: {project_id}"

        return {
            "status": "FAILED",
            "errors": message,
            "checks": {
                "required_files": {
                    "status": "FAILED",
                    "error": message,
                },
                "frontend": {
                    "status": "SKIPPED",
                    "error": "Project directory does not exist.",
                },
            },
            "repairable": False,
            "project_id": project_id,
        }

    missing = [
        filename
        for filename in REQUIRED_FILES
        if not (project_dir / filename).is_file()
    ]

    checks = {
        "required_files": {
            "status": "PASSED" if not missing else "FAILED",
            "error": ", ".join(missing),
        }
    }

    errors: list[str] = []

    if missing:
        errors.append(
            "Missing required files: " + ", ".join(missing)
        )

        checks["frontend"] = {
            "status": "SKIPPED",
            "error": "Required files are missing.",
        }

    else:
        frontend_errors = check_frontend(project_dir)

        checks["frontend"] = {
            "status": "PASSED" if not frontend_errors else "FAILED",
            "error": "\n".join(frontend_errors),
        }

        errors.extend(frontend_errors)

    passed = not errors

    return {
        "status": "PASSED" if passed else "FAILED",
        "errors": "\n".join(errors),
        "checks": checks,
        "repairable": True,
        "project_id": project_id,
    }

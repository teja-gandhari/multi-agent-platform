from typing import Any

REQUIRED_CHECKS = ("required_files", "frontend")


def _normalise_status(result: Any, *keys: str) -> str:
    """Read a status consistently from agent results."""
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if value is not None and str(value).strip():
                return str(value).strip().upper()
        return "UNKNOWN"

    if result is None:
        return "UNKNOWN"

    return str(result).strip().upper()


def reviewer_agent(
    user_request="",
    project_context="",
    plan="",
    research="",
    developer_output="",
    coder_output=None,
    test_result=None,
    project_id=None,
) -> dict:
    """Approve only projects that completed generation and passed testing."""

    coder_output = coder_output or {}
    test_result = test_result or {}

    coder_status = _normalise_status(coder_output, "status")

    if coder_status != "COMPLETED":
        message = (
            coder_output.get("message", "Coder did not complete generation.")
            if isinstance(coder_output, dict)
            else str(coder_output)
        )
        return {
            "decision": "NEEDS_REVISION",
            "status": "NEEDS_REVISION",
            "explanation": "The Coder has not completed project generation.",
            "problems": [str(message)],
        }

    test_status = _normalise_status(test_result, "status", "overall")
    checks = test_result.get("checks", {}) if isinstance(test_result, dict) else {}

    def check_status(name: str) -> str:
        check = checks.get(name) if isinstance(checks, dict) else None
        if isinstance(check, dict):
            return str(check.get("status", "UNKNOWN")).upper()
        if check is True:
            return "PASSED"
        if check is False:
            return "FAILED"
        return "NOT_RUN"

    problems = []

    if test_status != "PASSED":
        raw = test_result.get("errors") if isinstance(test_result, dict) else None
        if isinstance(raw, str):
            raw = [raw] if raw.strip() else []
        problems = [str(item) for item in (raw or [])]

        if not problems and isinstance(test_result, dict) and test_result.get("error"):
            problems = [str(test_result["error"])]

        for name in (checks if isinstance(checks, dict) else {}):
            if check_status(name) == "FAILED":
                detail = checks[name].get("error", "") if isinstance(checks[name], dict) else ""
                problems.append(f"{name}: {detail or 'check failed'}")

        return {
            "decision": "NEEDS_REVISION",
            "status": "NEEDS_REVISION",
            "explanation": "Testing failed or did not report PASSED.",
            "problems": problems or ["Automated testing has not passed."],
        }

    # A PASSED status is only trusted if the key checks actually ran.
    not_passed = [
        f"{name}: {check_status(name)}"
        for name in REQUIRED_CHECKS
        if check_status(name) != "PASSED"
    ]
    if not_passed:
        return {
            "decision": "NEEDS_REVISION",
            "status": "NEEDS_REVISION",
            "explanation": "Tester reported PASSED but required checks did not all pass.",
            "problems": not_passed,
        }

    return {
        "decision": "APPROVED",
        "status": "APPROVED",
        "explanation": (
            "The Coder completed generation and the frontend-only Tester reported "
            "PASSED. The static UI is approved for launch."
        ),
        "problems": [],
    }

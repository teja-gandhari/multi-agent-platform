
from services import llm
from services.llm import LLMError, explain

SYSTEM_PROMPT = """
You are the Developer Agent in NexusAI, a multi-agent FRONTEND-ONLY application generation platform.
Convert the Planner's plan and Researcher's brief into an actionable specification for the Coder.
Responsibilities:
1. Preserve the user's actual requirements; do not replace them with a generic demo.
2. Specify static index.html, style.css, and script.js responsibilities.
3. Define screens, responsive layout, navigation, reusable components, and interactions.
4. Define client-side state, validation, empty/error states, accessibility, and optional localStorage.
5. Specify meaningful frontend checks and edge cases.
6. Use HTML, CSS, and JavaScript only for the generated application.
7. Do not specify a generated-app backend, API endpoints, database, migrations, or Docker.
8. Do not require external API credentials or paid services. Label simulated data clearly.
9. Never invent credentials or claim code/tests already exist.
Return a clear implementation specification the Coder can follow.
""".strip()


def get_user_request(state: dict) -> str:
    request = state.get("user_request")

    if not isinstance(request, str) or not request.strip():
        raise ValueError(
            "Developer requires a non-empty user_request in workflow state."
        )

    return request.strip()


def build_development_prompt(state: dict, user_request: str) -> str:
    plan = (
        state.get("plan")
        or state.get("planner_output")
        or state.get("planning_result")
        or ""
    )

    research = (
        state.get("research_output")
        or state.get("research_result")
        or state.get("research_notes")
        or ""
    )

    if isinstance(plan, dict):
        plan = str(plan)

    if isinstance(research, dict):
        research = str(research)

    return (
        "Create an actionable frontend-only implementation specification. Do not specify a generated-app backend, API, or database.\n\n"
        f"USER REQUEST:\n{user_request}\n\n"
        f"PLANNER'S PLAN:\n{plan or 'No planner output was provided.'}\n\n"
        f"RESEARCHER'S BRIEF:\n"
        f"{research or 'No research brief was provided.'}\n\n"
        "Use these sections:\n"
        "1. Application objective and architecture\n"
        "2. Frontend files and responsibilities: index.html, style.css, script.js\n"
        "3. Screens, components, navigation, and responsive layout\n"
        "4. Client-side interactions, validation, and state\n"
        "5. Accessibility and empty/error states\n"
        "6. Browser-local persistence, only if useful\n"
        "7. Test cases and edge cases\n"
        "8. Static-file launch instructions\n"
        "9. Ordered implementation instructions for the Coder\n\n"
        "Resolve contradictions in favor of the user's explicit requirements. "
        "Do not add unnecessary services or dependencies. "
        "Do not write the complete source code."
    )


def create_development_specification(
    state: dict,
    user_request: str,
) -> str:
    prompt = build_development_prompt(state, user_request)
    return llm.chat_text("developer", SYSTEM_PROMPT, prompt)

def developer_agent(state: dict) -> dict:
    """
    LangGraph Developer node.

    Reads:
        user_request
        plan / planner_output
        research_output / research_result

    Writes:
        developer_output
        developer_result
        developer_status
        developer_error
    """
    try:
        user_request = get_user_request(state)

        specification = create_development_specification(
            state,
            user_request,
        )

        print("[Developer] Implementation specification created.")

        return {
            **state,
            "developer_output": specification,
            "developer_result": specification,
            "developer_status": "COMPLETED",
            "developer_error": None,
        }

    except Exception as exc:
        error_message = explain(exc) if isinstance(exc, LLMError) else str(exc)
        error_code = exc.code if isinstance(exc, LLMError) else "INTERNAL"

        print(f"[Developer] FAILED: {error_message}")

        return {
            **state,
            "developer_output": "",
            "developer_result": "",
            "developer_status": "FAILED",
            "developer_error": error_message,
            "developer_error_code": error_code,
        }


# Compatibility aliases for different workflow import names.
developer = developer_agent
development_agent = developer_agent

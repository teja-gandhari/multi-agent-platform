
from services import llm
from services.llm import LLMError, explain

SYSTEM_PROMPT = """
You are the Researcher Agent in NexusAI, a multi-agent FRONTEND-ONLY application generation platform.
Research the user's requested UI and prepare actionable guidance for the Developer.
Rules:
1. Preserve the requested app purpose and features.
2. Identify screens, navigation, reusable components, visual style, and interactions.
3. Recommend static HTML, CSS, and JavaScript only for the generated application.
4. Do not design a generated-app backend, API, database, or server-side dependency.
5. Use browser state and optional localStorage where appropriate.
6. Do not require external APIs, credentials, or paid services; use clearly labeled demo data if needed.
7. Include responsive design, accessibility, validation, empty/error states, and test edge cases.
8. Do not claim code has been written or tested and do not invent credentials.
Return a practical research brief with concise, actionable recommendations.
""".strip()


def get_user_request(state: dict) -> str:
    request = state.get("user_request")

    if not isinstance(request, str) or not request.strip():
        raise ValueError(
            "Researcher requires a non-empty user_request in workflow state."
        )

    return request.strip()


def build_research_prompt(state: dict, user_request: str) -> str:
    plan = (
        state.get("plan")
        or state.get("planner_output")
        or state.get("planning_result")
        or ""
    )

    if isinstance(plan, dict):
        plan = str(plan)

    return (
        "Research the following application requirements.\n\n"
        f"USER REQUEST:\n{user_request}\n\n"
        f"PLANNER OUTPUT:\n{plan or 'No planner output was provided.'}\n\n"
        "Produce a frontend research brief containing:\n"
        "1. Requirements and core features\n"
        "2. Screens and recommended UI architecture\n"
        "3. Components, navigation, and interactions\n"
        "4. Client-side state and optional localStorage\n"
        "5. Responsive and accessible behavior\n"
        "6. Validation, empty/error states, and edge cases\n"
        "7. Static launch requirements and assumptions\n\n"
        "Do not write the complete application code. "
        "Give the Developer Agent enough detail to implement it."
    )


def research_application(state: dict) -> str:
    user_request = get_user_request(state)
    prompt = build_research_prompt(state, user_request)
    return llm.chat_text("researcher", SYSTEM_PROMPT, prompt)

def researcher_agent(state: dict) -> dict:
    """
    LangGraph Researcher node.

    Reads user_request and optional planner output from state.
    Returns research notes and explicit status fields.
    """
    try:
        research_output = research_application(state)

        print("[Researcher] Research completed.")

        return {
            **state,
            "research_status": "COMPLETED",
            "research_output": research_output,
            "research_result": research_output,
            "research_error": None,
        }

    except Exception as exc:
        error_message = explain(exc) if isinstance(exc, LLMError) else str(exc)
        error_code = exc.code if isinstance(exc, LLMError) else "INTERNAL"

        print(f"[Researcher] FAILED: {error_message}")

        return {
            **state,
            "research_status": "FAILED",
            "research_output": "",
            "research_result": "",
            "research_error": error_message,
            "research_error_code": error_code,
        }


# Compatibility aliases for different workflow import names.
researcher = researcher_agent
research_agent = researcher_agent

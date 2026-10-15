
from services import llm
from services.llm import LLMError, explain

SYSTEM_PROMPT = """
You are the Planner Agent in NexusAI, a multi-agent FRONTEND-ONLY application
generation platform.

Your responsibility is to turn the user's natural-language request
into a clear implementation plan.

Rules:
1. Preserve the user's actual requirements. Do not replace their idea
   with a different application.
2. Identify the application's purpose and target users.
3. Break the application into practical implementation tasks.
4. Plan frontend screens, reusable UI components, client-side state, and interactions.
5. Do not plan a generated-app backend, API endpoints, or database.
6. Use localStorage only when browser-local persistence is useful.
7. Include important edge cases and failure scenarios.
8. Keep the plan proportional to the application's complexity.
9. Use static HTML, CSS, and JavaScript for the generated application.
10. Keep all prototype interactions in the browser; no generated-app database.
11. Do not invent API keys or claim that code has already been written.
12. Do not write the complete application source code.
13. Make assumptions explicit when the request is ambiguous.
14. The generated application must run locally as static files with no separate API or database.
15. Do not require external APIs, API keys, or paid services. Simulate unavailable live data clearly.

Return a practical plan that downstream Researcher, Developer,
Coder, Tester, and Reviewer agents can use.
Use clear headings and numbered implementation tasks.
""".strip()


def get_user_request(state: dict) -> str:
    request = state.get("user_request")

    if not isinstance(request, str) or not request.strip():
        raise ValueError(
            "Planner requires a non-empty user_request in workflow state."
        )

    return request.strip()


def build_planning_prompt(user_request: str, previous_plan: str = "", feedback: str = "") -> str:
    revision_context = ""
    if feedback.strip():
        revision_context = (
            "\n\nPLAN REVISION REQUEST\n"
            "The user reviewed the previous plan and requested these changes:\n"
            f"{feedback.strip()}\n\n"
            "Previous plan (revise it rather than ignoring it):\n"
            f"{previous_plan.strip()}\n\n"
            "Produce a complete revised plan incorporating the requested changes.\n"
        )
    return (
        "Create a frontend-only implementation plan for this application request. No generated backend, API, or database.\n\n"
        f"USER REQUEST:\n{user_request}\n\n"
        f"{revision_context}"
        "Structure your response using these sections:\n"
        "1. Application objective\n"
        "2. Core features and screens\n"
        "3. Frontend components and layout\n"
        "4. Client-side interactions and state\n"
        "5. Accessibility and responsive behavior\n"
        "6. Browser-local persistence if useful\n"
        "7. Testing strategy and edge cases\n"
        "8. Static-file launch instructions\n"
        "9. Ordered implementation steps\n\n"
        "Only include technologies that are actually needed. "
        "Keep the plan clear, specific, and actionable."
    )


def create_plan(user_request: str, previous_plan: str = "", feedback: str = "") -> str:
    """Raises LLMError (typed, already retried per policy) on failure."""
    return llm.chat_text(
        "planner", SYSTEM_PROMPT,
        build_planning_prompt(user_request, previous_plan, feedback)
    )

def planner_agent(state: dict) -> dict:
    """
    LangGraph Planner node.

    Reads:
        user_request

    Writes:
        plan
        planner_output
        planner_status
        planner_error
    """
    try:
        user_request = get_user_request(state)
        plan = create_plan(
            user_request,
            previous_plan=str(state.get("plan", "") or ""),
            feedback=str(state.get("planner_feedback", "") or ""),
        )

        print("[Planner] Implementation plan created.")

        return {
            **state,
            "plan": plan,
            "planner_output": plan,
            "planner_status": "COMPLETED",
            "planner_error": None,
        }

    except Exception as exc:
        error_message = explain(exc) if isinstance(exc, LLMError) else str(exc)
        error_code = exc.code if isinstance(exc, LLMError) else "INTERNAL"

        print(f"[Planner] FAILED: {error_message}")

        return {
            **state,
            "plan": "",
            "planner_output": "",
            "planner_status": "FAILED",
            "planner_error": error_message,
            "planner_error_code": error_code,
        }


# Compatibility aliases for different workflow import names.
planner = planner_agent
plan_agent = planner_agent

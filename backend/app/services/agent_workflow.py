
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class AgentState(TypedDict):
    task: str
    plan: str


def planner_node(state: AgentState) -> AgentState:
    """Create a basic plan from the user's task."""
    task = state["task"].strip()

    return {
        **state,
        "plan": (
            f"Task received: {task}\n"
            "1. Analyze the requirements.\n"
            "2. Break the task into smaller steps.\n"
            "3. Execute and review the steps."
        ),
    }


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", END)

    return graph.compile()


agent_graph = build_agent_graph()

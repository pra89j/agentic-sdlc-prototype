from langgraph.graph import END, START, StateGraph
from agent_engine.nodes import (
    SDLCState,
    analyst_node,
    approval_node,
    critic_node,
    executor_node,
    planner_node,
    reasoner_node,
    validator_node,
    approval_route,
)

MAX_RETRIES = 3


def should_retry(state: SDLCState) -> str:
    if state["validation_passed"]:
        return "critic"
    if state["retry_count"] < MAX_RETRIES:
        print(f"      -> Retrying synthesis to fix validation errors ({state['retry_count']}/{MAX_RETRIES})...")
        return "executor"
    print("      -> Max retries reached. Proceeding to Critic report with failure details.")
    return "critic"


def build_sdlc_graph():
    graph = StateGraph(SDLCState)

    graph.add_node("analyst", analyst_node)
    graph.add_node("reasoner", reasoner_node)
    graph.add_node("planner", planner_node)
    graph.add_node("approval", approval_node)
    graph.add_node("executor", executor_node)
    graph.add_node("validator", validator_node)
    graph.add_node("critic", critic_node)

    graph.add_edge(START, "analyst")
    graph.add_edge("analyst", "reasoner")
    graph.add_edge("reasoner", "planner")
    graph.add_edge("planner", "approval")
    graph.add_conditional_edges(
        "approval", approval_route, {"execute": "executor", "stop": END}
    )
    graph.add_edge("executor", "validator")
    graph.add_conditional_edges("validator", should_retry, {"executor": "executor", "critic": "critic"})
    graph.add_edge("critic", END)

    return graph.compile()
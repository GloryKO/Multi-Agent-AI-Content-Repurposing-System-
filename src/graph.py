"""
Wires the supervisor + specialist agents into a LangGraph StateGraph.

Every specialist node reports back to the supervisor unconditionally;
the supervisor is the only node with conditional edges, and it decides
the next hop purely from what's present in state. This keeps the graph
topology simple (a star, not a web) even though the underlying logic
supports loops (the critique -> writer cycle) and skips (no image
found, short content skips summarization).
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agents.assembler_agent import assembler_node
from src.agents.brief_agent import brief_node
from src.agents.critic_agent import critic_node
from src.agents.image_agent import image_node
from src.agents.repurposer_agent import repurposer_node
from src.agents.scraper_agent import scrape_node
from src.agents.seo_research_agent import seo_research_node
from src.agents.summarizer_agent import summarize_node
from src.agents.writer_agent import writer_node
from src.state import PipelineState
from src.supervisor import supervisor_node


SPECIALIST_NODES = {
    "scrape": scrape_node,
    "summarize": summarize_node,
    "seo_research": seo_research_node,
    "brief": brief_node,
    "writer": writer_node,
    "critic": critic_node,
    "repurposer": repurposer_node,
    "image": image_node,
    "assembler": assembler_node,
}


def route_from_supervisor(state: PipelineState) -> str:
    """
    LangGraph calls this after the supervisor node runs.
    The supervisor already decided the next hop and stored it in
    state["next"] — we just read that string and hand it back so
    LangGraph can follow the matching edge.
    """
    return state["next"]


# Map each possible supervisor decision to a graph destination.
# "END" is special: it stops the graph instead of calling another node.
DESTINATIONS = {name: name for name in SPECIALIST_NODES}
DESTINATIONS["END"] = END


def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("supervisor", supervisor_node)
    for name, fn in SPECIALIST_NODES.items():
        graph.add_node(name, fn)

    graph.set_entry_point("supervisor")

    # Supervisor picks the next specialist (or END) via state["next"].
    graph.add_conditional_edges("supervisor", route_from_supervisor, DESTINATIONS)

    for name in SPECIALIST_NODES:
        if name != "assembler":
            graph.add_edge(name, "supervisor")
    graph.add_edge("assembler", END)

    return graph.compile()


compiled_graph = build_graph()

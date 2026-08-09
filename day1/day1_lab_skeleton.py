# ============================================================
# DAY 1 LAB — SKELETON: Build the Research Agent Yourself
# ============================================================
# Fill in every TODO. Each step tells you exactly WHERE in the
# LangGraph docs to look. Don't copy from the solution file
# (day1_lab_solution.py) until you've tried each step —
# the point of Day 1 is learning to THINK in state graphs.
#
# The system you're building:
#
#   START → collect → store_memory → analyze → evaluate
#              ↑                                  │
#              └── quality < 7 (max 3 tries) ─────┤
#                                                 └ quality >= 7
#                                                       ↓
#                                          report → audit → END
#
# Recommended reading order BEFORE you start (30 min total):
#   1. "Thinking in LangGraph" (the mental model):
#      https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph
#   2. Graph API concepts (State, Nodes, Edges):
#      https://docs.langchain.com/oss/python/langgraph/graph-api
#   3. Using the Graph API (code patterns you'll copy):
#      https://docs.langchain.com/oss/python/langgraph/use-graph-api
#
# API reference (exact signatures when docs aren't enough):
#   https://reference.langchain.com/python/langgraph/
#
# Setup: `uv sync`, then create .env (or set USE_FAKE=1 — see README.md).
# ============================================================

import os
import operator
from datetime import datetime
from typing import Annotated, List, Dict
from typing_extensions import TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv()


# ============================================================
# STEP 1 — THE STATE  (the "digital clipboard" from the slides)
# ============================================================
# Define a TypedDict with everything the workflow needs to remember:
#   topic (str), search_query (str), collected_data (List[Dict]),
#   analyzed_data (List[Dict]), quality_score (int),
#   iteration_count (int), final_report (str), execution_logs
#
# KEY IDEA: execution_logs should use a REDUCER so every node can
# APPEND log lines instead of overwriting the list:
#     execution_logs: Annotated[List[str], operator.add]
#
# WHERE TO LOOK: Graph API docs → "State" section → "Reducers".
#   https://docs.langchain.com/oss/python/langgraph/graph-api
# ASK YOURSELF: what happens to a plain (non-reducer) key when two
# nodes write it? What happens with operator.add?

class AgentState(TypedDict):
    topic: str
    search_query: str
    collected_data: List[Dict]
    analyzed_data: List[Dict]
    quality_score: int
    iteration_count: int
    final_report: str
    execution_logs: Annotated[List[str], operator.add]

# ============================================================
# STEP 2 — MODEL, SEARCH TOOL, EMBEDDINGS
# ============================================================
# Create:
#   llm          = ChatOpenAI(model="gpt-4o-mini", temperature=0)
#   search_tool  = TavilySearch(max_results=5)   # langchain_tavily!
#   vector_store = a Chroma or InMemoryVectorStore with embeddings
#
# ------------------------------------------------------------
# USING OPENROUTER (free models — recommended for this course)
# ------------------------------------------------------------
# OpenRouter is OpenAI-compatible, so ChatOpenAI works as-is —
# you only change the key, the base_url, and the model name.
#
# 1. Get a key at https://openrouter.ai/keys  (starts with sk-or-)
# 2. Put in your .env:
#        OPENAI_API_KEY=sk-or-...
# 3. Create the model like this:
#
#    llm = ChatOpenAI(
#        model="nvidia/nemotron-3-super-120b-a12b:free",
#        temperature=0,
#        base_url="https://openrouter.ai/api/v1",
#    )
#
# Free NVIDIA Nemotron models (the ":free" suffix is REQUIRED —
# without it you'll be billed):
#   nvidia/nemotron-3-super-120b-a12b:free   <- use this one
#   nvidia/nemotron-3-nano-30b-a3b:free      <- fallback if rate-limited
#   nvidia/nemotron-3-ultra-550b-a55b:free   <- biggest, often congested
# Full list: https://openrouter.ai/collections/free-models
#
# KNOW THE LIMITS: free models are rate-limited (~20 req/min and a
# small daily cap). This lab makes ~5-10 LLM calls per run, so you
# have plenty — but don't run it in a tight loop, and if you get
# HTTP 429, wait a minute or switch to the nano model.
#
# CAVEAT for Step 3: with_structured_output() needs tool/function
# calling. Nemotron supports it, but if a free model ever returns
# an error there, either (a) try another :free model, or (b) pass
# method="json_schema" to with_structured_output.
#
# NOTE: OpenRouter has NO embeddings endpoint. For the vector store
# use InMemoryVectorStore + local HuggingFaceEmbeddings
# (uv sync --group embeddings), or DeterministicFakeEmbedding —
# embeddings only power the memory-retrieval bonus, not the core graph.
# ------------------------------------------------------------
#
# GOTCHA: the old imports you'll find in 2023-24 tutorials
# (langchain.vectorstores, langchain_community.tools.tavily_search)
# are DEAD. Current homes:
#   - TavilySearch:      https://docs.langchain.com/oss/python/integrations/providers/tavily
#   - Chat models:       https://docs.langchain.com/oss/python/langchain/models
#   - InMemoryVectorStore: langchain_core.vectorstores
#
# NOTE: TavilySearch.invoke({"query": q}) returns a DICT — the
# actual sources are under the "results" key. print() it once to see.

from langchain_openai import ChatOpenAI
from langchain_community.tools import TavilySearchResults
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.embeddings import FakeEmbeddings

llm = ChatOpenAI(
    model="nvidia/nemotron-3-super-120b-a12b:free",
    temperature=0,
    base_url="https://openrouter.ai/api/v1",
)

search_tool = TavilySearchResults(max_results=5)

embeddings = FakeEmbeddings(size=1536)
vector_store = InMemoryVectorStore(embeddings)


# ============================================================
# STEP 3 — STRUCTURED OUTPUT for the quality score
# ============================================================
# Never parse int(response.content) out of free text. Define a
# Pydantic schema and use llm.with_structured_output(...) so the
# model is FORCED to return valid data.
#
# WHERE TO LOOK: https://docs.langchain.com/oss/python/langchain/structured-output
# ASK YOURSELF: what does with_structured_output return — a string,
# a dict, or a QualityScore object?

def collect_node(state: AgentState):
    """Search the web. On retries, change the search query."""
    iteration = state.get("iteration_count", 0) + 1
    topic = state["topic"]
    
    if iteration == 1:
        query = f"Research on {topic}"
    elif iteration == 2:
        query = f"Detailed analysis and technical details about {topic}"
    else:
        query = f"Future outlook and advanced application of {topic}"
        
    raw_response = search_tool.invoke({"query": query})
    results = raw_response.get("results", []) if isinstance(raw_response, dict) else raw_response
    
    return {
        "search_query": query,
        "collected_data": results,
        "iteration_count": iteration,
        "execution_logs": [f"Collect Node: Found {len(results)} items using query '{query}' (Attempt #{iteration})"]
    }


def store_memory_node(state: AgentState):
    """Save source contents into the vector store."""
    collected = state.get("collected_data", [])
    texts_to_store = [item.get("content", "") for item in collected if item.get("content")]
    
    if texts_to_store:
        vector_store.add_texts(texts_to_store)
        
    return {
        "execution_logs": [f"Store Memory Node: Stored {len(texts_to_store)} snippets in vector store"]
    }


def analyze_node(state: AgentState):
    """LLM-analyze each source with vector store context."""
    collected = state.get("collected_data", [])
    analyzed_data = []
    
    for item in collected:
        content = item.get("content", "")
        related_docs = vector_store.similarity_search(content, k=1) if content else []
        related_text = related_docs[0].page_content if related_docs else "No prior context"
        
        prompt = f"Analyze this content for {state['topic']}:\n{content}\n\nRelated Context: {related_text}"
        analysis_res = llm.invoke(prompt)
        
        analyzed_data.append({
            "url": item.get("url", ""),
            "summary": analysis_res.content
        })
        
    return {
        "analyzed_data": analyzed_data,
        "execution_logs": [f"Analyze Node: Analyzed {len(analyzed_data)} sources"]
    }


def evaluate_node(state: AgentState):
    """Score the research with the structured evaluator."""
    analyzed = state.get("analyzed_data", [])
    combined_summary = "\n".join([item["summary"] for item in analyzed])
    
    prompt = f"Evaluate the completeness of research for topic '{state['topic']}':\n{combined_summary}"
    result = evaluator.invoke(prompt)
    
    return {
        "quality_score": result.score,
        "execution_logs": [f"Evaluate Node: Assigned quality score {result.score}/10 (Reason: {result.reasoning})"]
    }


def report_node(state: AgentState):
    """Generate the final research report."""
    analyzed = state.get("analyzed_data", [])
    combined = "\n".join([f"- {item['summary']}" for item in analyzed])
    
    prompt = f"Generate a detailed final report on '{state['topic']}' using these research insights:\n{combined}"
    response = llm.invoke(prompt)
    
    return {
        "final_report": response.content,
        "execution_logs": ["Report Node: Generated final research report"]
    }


def audit_node(state: AgentState):
    """Log completion stats."""
    return {
        "execution_logs": [f"Audit Node: Research complete in {state.get('iteration_count', 0)} iteration(s)"]
    }

# ============================================================
# STEP 5 — THE CONDITIONAL EDGE (the heart of this lab)
# ============================================================
# Write a router function: takes state, RETURNS THE NAME of the
# next node as a string.
#
# CRITICAL — loops must terminate. Two rules:
#   a) every retry must change something (your query, Step 4.2),
#   b) hard-cap the retries with iteration_count.
# Without both, same search → same score → infinite loop → LangGraph
# kills the run at recursion limit 25 with GraphRecursionError.
#
# WHERE TO LOOK (read BOTH):
#   - "Conditional branching":
#     https://docs.langchain.com/oss/python/langgraph/use-graph-api#conditional-branching
#   - "Create and control loops":
#     https://docs.langchain.com/oss/python/langgraph/use-graph-api#create-and-control-loops
#
# EXPERIMENT: comment out the iteration cap, force low scores, run,
# and read the GraphRecursionError message. Now you understand why
# the docs insist on termination conditions.

def quality_router(state: AgentState) -> str:
    """Route to report if quality is high or max retries reached; else collect again."""
    score = state.get("quality_score", 0)
    iterations = state.get("iteration_count", 0)
    
    if score >= 7 or iterations >= 3:
        return "report"
    return "collect"

# ============================================================
# STEP 6 — WIRE THE GRAPH
# ============================================================
# 1. workflow = StateGraph(AgentState)
# 2. add_node(...) for all six nodes
# 3. add_edge(START, "collect")        <- START, not set_entry_point
# 4. linear edges: collect → store_memory → analyze → evaluate
# 5. add_conditional_edges("evaluate", quality_router,
#        {"collect": "collect", "report": "report"})
#    (the dict maps router RETURN VALUES to NODE NAMES)
# 6. report → audit → END
#
# WHERE TO LOOK: Graph API docs → "Edges".

# 1. Initialize the workflow graph
workflow = StateGraph(AgentState)

# 2. Add all six nodes to the graph
workflow.add_node("collect", collect_node)
workflow.add_node("store_memory", store_memory_node)
workflow.add_node("analyze", analyze_node)
workflow.add_node("evaluate", evaluate_node)
workflow.add_node("report", report_node)
workflow.add_node("audit", audit_node)

# 3. Add the entry point from START to "collect"
workflow.add_edge(START, "collect")

# 4. Add sequential linear edges
workflow.add_edge("collect", "store_memory")
workflow.add_edge("store_memory", "analyze")
workflow.add_edge("analyze", "evaluate")

# 5. Add conditional edge from "evaluate" based on quality_router
workflow.add_conditional_edges(
    "evaluate",
    quality_router,
    {"collect": "collect", "report": "report"}
)

# 6. Add remaining edges leading to END
workflow.add_edge("report", "audit")
workflow.add_edge("audit", END)


# ============================================================
# STEP 7 — COMPILE with a checkpointer, VISUALIZE, RUN
# ============================================================
# 1. app = workflow.compile(checkpointer=InMemorySaver())
#    A checkpointer saves state after every node → enables resume,
#    time-travel debugging, and human-in-the-loop.
#    WHERE TO LOOK: https://docs.langchain.com/oss/python/langgraph/persistence
#
# 2. Visualize what you built:
#       print(app.get_graph().draw_mermaid())
#    → paste the output into https://mermaid.live
#    Does the picture match the diagram at the top of this file?
#
# 3. Run with STREAMING so you watch state evolve node by node:
#       config = {"configurable": {"thread_id": "run-1"}}  # required
#       for chunk in app.stream(initial_state, config,
#                               stream_mode="values"):
#           ...
#    WHERE TO LOOK: https://docs.langchain.com/oss/python/langgraph/streaming
#
# 4. BONUS — human-in-the-loop: compile with
#       interrupt_before=["report"]
#    then inspect state and resume. WHERE TO LOOK:
#       https://docs.langchain.com/oss/python/langgraph/interrupts

if __name__ == "__main__":
    initial_state = {
        "topic": "Enterprise Agentic AI Systems",
        "search_query": "",
        "collected_data": [],
        "analyzed_data": [],
        "quality_score": 0,
        "iteration_count": 0,
        "final_report": "",
        "execution_logs": [],
    }
# 1. Compile the graph with memory checkpointer
    memory = InMemorySaver()
    app = workflow.compile(checkpointer=memory)

    # 2. Visualize the graph (prints Mermaid format diagram)
    print("--- GRAPH MERMAID DIAGRAM ---")
    try:
        print(app.get_graph().draw_mermaid())
    except Exception as e:
        print(f"Could not render diagram: {e}")
    print("-----------------------------\n")

    # 3. Configure and run with streaming mode
    config = {"configurable": {"thread_id": "run-1"}}
    
    print("Starting agent execution...\n")
    for chunk in app.stream(initial_state, config, stream_mode="values"):
        logs = chunk.get("execution_logs", [])
        if logs:
            print(f"Latest Log: {logs[-1]}")

    # Fetch final state to display the report
    final_state = app.get_state(config).values

    print("\n================ FINAL REPORT ================")
    print(final_state.get("final_report", "No report generated."))
    print("==============================================")

# ============================================================
# SELF-CHECK before you look at the solution
# ============================================================
# [ ] My nodes return partial dicts, never the whole mutated state
# [ ] execution_logs uses a reducer, and I can explain why
# [ ] My router has BOTH a quality exit AND an iteration cap
# [ ] Retried searches use a different query than the first attempt
# [ ] I saw the Mermaid diagram and it matches the intended flow
# [ ] I know what GraphRecursionError is and how to trigger it
# [ ] The quality score comes from with_structured_output, not int()
#
# Stuck? Debugging order that works:
#   1. print() the raw return of search_tool.invoke — check its shape
#   2. run app.stream(..., stream_mode="updates") — shows exactly
#      which node produced which state update
#   3. compare your edge wiring against the diagram at the top
#   4. only THEN open day1_lab_solution.py
# ============================================================

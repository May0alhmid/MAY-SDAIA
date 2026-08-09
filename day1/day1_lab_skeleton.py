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
from langchain_openai import ChatOpenAI
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.embeddings import FakeEmbeddings

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
    # TODO: add the remaining 6 keys (one uses Annotated + operator.add)
    search_query: str
    collected_data: List[Dict]
    analyzed_data: List[Dict]
    quality_score: int
    iteration_count: int
    final_report: str
    # المجمع (Reducer) لمنع مسح سجلات العقد السابقة
    execution_logs: Annotated[List[str], operator.add]


# ============================================================
# ============================================================
# STEP 2 — MODEL & SEARCH TOOL
# ============================================================
# إعداد نموذج اللغة عبر OpenRouter
llm = ChatOpenAI(
    model="nvidia/nemotron-3-super-120b-a12b:free",
    temperature=0,
    base_url="https://openrouter.ai/api/v1",
)

# ذاكرة متجهية وهمية لا تستدعي خدمات خارجية
vector_store = InMemoryVectorStore(embedding=FakeEmbeddings(size=1536))

# دالة البحث (تستخدم بيانات افتراضية إذا كان USE_FAKE=1 أو لا يوجد مفتاح)
def execute_search(query: str) -> List[Dict]:
    if os.getenv("USE_FAKE", "0") == "1" or not os.getenv("TAVILY_API_KEY"):
        return [
            {
                "title": f"Result for {query}",
                "content": f"Enterprise Agentic AI systems rely on stateful graph architectures like LangGraph for complex task decomposition.",
                "url": "https://example.com/research"
            }
        ]
    else:
        from langchain_tavily import TavilySearch
        search_tool = TavilySearch(max_results=3)
        res = search_tool.invoke({"query": query})
        return res.get("results", [])


# ============================================================
# STEP 3 — STRUCTURED OUTPUT
# ============================================================
class QualityScore(BaseModel):
    """Evaluation of research quality."""
    score: int = Field(ge=1, le=10, description="Score from 1 to 10")
    reasoning: str = Field(description="One-sentence justification")

evaluator = llm.with_structured_output(QualityScore)

class QualityScore(BaseModel):
    """Evaluation of research quality."""
    score: int = Field(ge=1, le=10)
    reasoning: str = Field(description="One-sentence justification")

# TODO: evaluator = llm.with_structured_output(QualityScore)


# ============================================================
# ============================================================
# STEP 4 — NODES
# ============================================================
def collect_node(state: AgentState) -> Dict:
    """البحث في الويب مع تنويع الاستعلام عند التكرار"""
    iteration = state.get("iteration_count", 0) + 1
    base_topic = state["topic"]
    
    # تنويع الاستعلام بناءً على محاولة التكرار
    if iteration == 1:
        query = f"{base_topic} overview and architecture"
    elif iteration == 2:
        query = f"{base_topic} implementation details and state management"
    else:
        query = f"{base_topic} best practices and security"
        
    results = execute_search(query)
    
    return {
        "search_query": query,
        "collected_data": results,
        "iteration_count": iteration,
        "execution_logs": [f"[collect] Iteration {iteration}: Queried '{query}'"]
    }


def store_memory_node(state: AgentState) -> Dict:
    """حفظ البيانات المجمعة في الذاكرة المتجهية"""
    texts = [f"Title: {item.get('title')}\nContent: {item.get('content')}" for item in state["collected_data"]]
    if texts:
        vector_store.add_texts(texts)
    return {
        "execution_logs": [f"[store_memory] Saved {len(texts)} items to memory."]
    }


def analyze_node(state: AgentState) -> Dict:
    """تحليل النتائج واسترجاع السياق المشابه (RAG)"""
    analyzed_results = []
    for item in state["collected_data"]:
        content = item.get("content", "")
        # استرجاع سياق مشابه
        similar = vector_store.similarity_search(content, k=1)
        retrieved = similar[0].page_content if similar else "No prior context."
        
        prompt = f"Topic: {state['topic']}\nSource: {content}\nContext: {retrieved}\nProvide a brief analysis."
        
        if os.getenv("USE_FAKE", "0") == "1":
            analysis_text = f"Analyzed: {content[:80]}..."
        else:
            res = llm.invoke([HumanMessage(content=prompt)])
            analysis_text = res.content

        analyzed_results.append({"title": item.get("title"), "analysis": analysis_text})

    return {
        "analyzed_data": analyzed_results,
        "execution_logs": [f"[analyze] Analyzed {len(analyzed_results)} sources."]
    }


def evaluate_node(state: AgentState) -> Dict:
    """تقييم الجودة باستخدام المخرجات المنسقة"""
    combined = "\n".join([a["analysis"] for a in state["analyzed_data"]])
    
    if os.getenv("USE_FAKE", "0") == "1":
        score = 8 if state["iteration_count"] >= 2 else 5
        reason = "Fake evaluation score"
    else:
        prompt = f"Topic: {state['topic']}\nAnalyses:\n{combined}\nRate quality from 1 to 10."
        try:
            eval_res = evaluator.invoke([HumanMessage(content=prompt)])
            score = eval_res.score
            reason = eval_res.reasoning
        except Exception:
            score = 7
            reason = "Fallback score due to parser limits"

    return {
        "quality_score": score,
        "execution_logs": [f"[evaluate] Score: {score}/10 ({reason})"]
    }


def report_node(state: AgentState) -> Dict:
    """إنشاء التقرير النهائي"""
    lines = [
        f"# Research Report: {state['topic']}",
        f"Score: {state['quality_score']}/10 | Iterations: {state['iteration_count']}\n",
    ]
    for idx, item in enumerate(state["analyzed_data"], 1):
        lines.append(f"### {idx}. {item.get('title')}\n{item.get('analysis')}\n")
        
    return {
        "final_report": "\n".join(lines),
        "execution_logs": ["[report] Report successfully generated."]
    }


def audit_node(state: AgentState) -> Dict:
    """تدقيق وسجل الخروج"""
    return {
        "execution_logs": ["[audit] Workflow finished."]
    }

# ============================================================
# ============================================================
# STEP 5 — CONDITIONAL EDGE (المسار الشرطي)
# ============================================================
def quality_router(state: AgentState) -> str:
    """إعادة البحث إذا كانت الجودة أقل من 7 ولم تتجاوز 3 محاولات"""
    quality = state.get("quality_score", 0)
    iterations = state.get("iteration_count", 0)
    
    if quality < 7 and iterations < 3:
        return "collect"
    return "report"


# ============================================================
# STEP 6 — WIRE THE GRAPH (ربط الرسم البياني)
# ============================================================
workflow = StateGraph(AgentState)

# إضافة العقد
workflow.add_node("collect", collect_node)
workflow.add_node("store_memory", store_memory_node)
workflow.add_node("analyze", analyze_node)
workflow.add_node("evaluate", evaluate_node)
workflow.add_node("report", report_node)
workflow.add_node("audit", audit_node)

# الربط
workflow.add_edge(START, "collect")
workflow.add_edge("collect", "store_memory")
workflow.add_edge("store_memory", "analyze")
workflow.add_edge("analyze", "evaluate")

# التوجيه الشرطي
workflow.add_conditional_edges(
    "evaluate",
    quality_router,
    {"collect": "collect", "report": "report"}
)

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
    checkpointer = InMemorySaver()
    app = workflow.compile(checkpointer=checkpointer)

    # 1. رسم مخطط الرسم البياني
    print("\n=== GRAPH DIAGRAM ===")
    print(app.get_graph().draw_mermaid())
    print("=====================\n")

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

    config = {"configurable": {"thread_id": "run-1"}}

    # 2. تشغيل الوكيل وتتبع الخطوات خطوة بخطوة
    print("--- Starting Agent Execution ---")
    for chunk in app.stream(initial_state, config, stream_mode="values"):
        logs = chunk.get("execution_logs", [])
        if logs:
            print(logs[-1])

    # 3. طباعة التقرير النهائي
    final_output = app.get_state(config).values
    print("\n================ FINAL REPORT ================")
    print(final_output.get("final_report"))
    print("==============================================")
    # TODO: compile, visualize, stream, print final report + logs


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

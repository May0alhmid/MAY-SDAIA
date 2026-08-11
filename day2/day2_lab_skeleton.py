# ============================================================
# DAY 2 LAB — SKELETON: Build a Multi-Agent Research Team
# ============================================================
# Fill in every TODO. Don't open the solution (day2_lab_solution.py)
# until you pass the self-check at the bottom.
#
# WHAT CHANGES FROM DAY 1 — read this table twice:
#
#   Day 1 (single agent)              Day 2 (multi-agent)
#   ─────────────────────             ─────────────────────────────
#   nodes = Python functions          nodes = LLM agents w/ personas
#   routing = your if/else            routing = supervisor LLM decides
#   one prompt for everything         one system prompt PER agent
#   tools available everywhere        tools SCOPED (only researcher
#                                       can search the web)
#   loop = quality-score retry        loop = critic sends draft back
#                                       to writer for revision
#
# What does NOT change: State + Nodes + Edges. A multi-agent system
# is STILL just a StateGraph. If you can build Day 1, you can build
# this — the new ideas are personas, the supervisor, and guardrails.
#
# The system you're building (the SUPERVISOR pattern):
#
#              ┌──────────── supervisor ─────────────┐
#              │       (LLM decides who's next)      │
#     ┌────────┼───────────┬───────────┬─────────────┤
#     ↓        ↓           ↓           ↓             ↓
#  researcher  analyst    writer     critic       FINISH
#     │        │           │           │             ↓
#     └────────┴───────────┴───────────┘            END
#          (every worker reports back to the supervisor)
#
# Recommended reading BEFORE you start (~25 min):
#   1. Multi-agent concepts (architectures, supervisor pattern):
#      https://docs.langchain.com/oss/python/langgraph/multi-agent
#   2. Refresh: conditional branching + loops (you need both again):
#      https://docs.langchain.com/oss/python/langgraph/use-graph-api#conditional-branching
#   3. Structured output (the supervisor's decision is structured!):
#      https://docs.langchain.com/oss/python/langchain/structured-output
#
# Setup: same as Day 1 — `uv sync`, keys in .env, or USE_FAKE=1.
# ============================================================

import os
import operator
from datetime import datetime
from typing import Annotated, List, Literal
from typing_extensions import TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
# ============================================================
# STEP 0 — IMPORTS
# ============================================================
import os
import operator
from datetime import datetime
from typing import Annotated, List, Literal
from typing_extensions import TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.chat_models.fake import FakeListChatModel
from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    class ChatOpenAI:  # type: ignore[reportMissingImports]
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "The 'langchain-openai' package is required for ChatOpenAI. "
                "Install it with `pip install langchain-openai`."
            )

        def with_structured_output(self, *args, **kwargs):
            raise ImportError(
                "The 'langchain-openai' package is required for structured output. "
                "Install it with `pip install langchain-openai`."
            )

# استيراد مكونات LangGraph
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

MAX_REVISIONS = 2      # الحد الأقصى لدورات التعديل بين الكاتب والناقد
MAX_TURNS = 12         # الحد الأقصى الإجمالي لقرارات المشرف
load_dotenv()

MAX_REVISIONS = 2      # cap on writer↔critic loops
MAX_TURNS = 12         # cap on total supervisor decisions

# ============================================================
# STEP 1 — SHARED STATE: السبورة المشتركة
# ============================================================
class TeamState(TypedDict):
    task: str                                      # المهمة المطلوبة
    research_notes: Annotated[List[str], operator.add] # ملاحظات البحث (تُضاف ولا تُحذف)
    analysis: str                                  # التحليل النهائي
    draft: str                                     # مسودة المقال/التقرير
    critique: str                                  # نقد وملاحظات الناقد
    revision_count: int                            # عدد التعديلات التي تمت
    turn_count: int                                # عدد الدورات الكلية
    next_agent: str                                # القرار: من الوكيل التالي؟
    execution_logs: Annotated[List[str], operator.add] # سجلات التشغيل والخطوات

# ============================================================
# ============================================================
# STEP 2 — STRUCTURED ROUTING DECISION
# ============================================================
class RouterDecision(BaseModel):
    """قرار المشرف تحديد من يعمل في الخطوة التالية"""
    next_agent: Literal["researcher", "analyst", "writer", "critic", "FINISH"]
    reason: str = Field(description="سبب إرسال المهمة لهذا الوكيل في جملة واحدة")

# ============================================================
# ============================================================
# STEP 3 — PERSONAS & TOOLS
# ============================================================
# ============================================================
# STEP 3 — PERSONAS, MODELS & TOOLS (FAKE MODE OPTIMIZED)
# ============================================================

import json

PERSONAS = {
    "researcher": (
        "You are a Senior Web Researcher. Your only job is to gather raw, factual information "
        "and concrete evidence from web search results regarding the user's request. "
        "Summarize key findings objectively. DO NOT perform deep analysis, strategy writing, or draft articles."
    ),
    "analyst": (
        "You are a Strategic AI Analyst. Your job is to analyze raw research notes, identify key trends, "
        "opportunities, risks, and synthesize structured strategic recommendations. "
        "DO NOT search the web directly or draft the final polish text."
    ),
    "writer": (
        "You are a Professional Tech Writer. Your job is to turn the strategic analysis and research "
        "into a comprehensive, engaging report or draft. If critique is provided, explicitly update "
        "and address all criticism points in the new draft. DO NOT perform external research."
    ),
    "critic": (
        "You are a Rigorous Content Editor and Quality Critic. Review the draft against research notes and analysis. "
        "If the draft needs revisions, respond with 'REVISE: <detailed instructions>'. "
        "If the draft is excellent, complete, and accurate, respond with 'APPROVED'."
    )
}

USE_FAKE = os.getenv("USE_FAKE", "0") == "1"

if USE_FAKE:
    print("⚠️ Running in FAKE mode (No API Key required)...")
    
    # 1. طابور قرارات المشرف المخصصة حصراً للهيكلة Structured Output
    supervisor_responses = [
        '{"next_agent": "researcher", "reason": "Need initial web research on multi-agent AI adoption."}',
        '{"next_agent": "analyst", "reason": "Research gathered, moving to strategic analysis."}',
        '{"next_agent": "writer", "reason": "Analysis complete, ready for writing the first report draft."}',
        '{"next_agent": "critic", "reason": "Draft created, sending to critic for quality review."}',
        '{"next_agent": "FINISH", "reason": "Draft has been reviewed, approved and finalized."}',
    ]
    
    # 2. طابور ردود الوكلاء التنفيذيين (الباحث -> المحلل -> الكاتب -> الناقد)
    worker_responses = [
        # رد الباحث
        "Key Research Findings:\n1. Multi-agent architecture improves complex enterprise workflow efficiency by 40%.\n2. Key bottlenecks include API token costs and inter-agent communication latency.",
        # رد المحلل
        "Strategic Analysis:\nAdopting multi-agent systems in 2026 offers high ROI for complex research tasks. Recommended strategy: Deploy Supervisor Pattern with hard turn caps to control costs.",
        # رد الكاتب
        "Executive Report 2026: Executive Adoption of Multi-Agent AI Systems\n\n1. Overview: Autonomous multi-agent systems represent a paradigm shift in enterprise AI...\n2. Key Benefits: 40% efficiency gain in complex tasks...\n3. Risk Mitigation: Guardrails must be enforced at supervisor level.",
        # رد الناقد
        "APPROVED"
    ]
    
    supervisor_llm_base = FakeListChatModel(responses=supervisor_responses)
    worker_llm = FakeListChatModel(responses=worker_responses)
    
    class FakeStructuredLLM:
        def __init__(self, base_llm):
            self.base_llm = base_llm

        def invoke(self, messages):
            res = self.base_llm.invoke(messages)
            content = res.content if hasattr(res, "content") else str(res)
            data = json.loads(content)
            return RouterDecision(**data)

    supervisor_llm = FakeStructuredLLM(supervisor_llm_base)
    llm = worker_llm

    @tool
    def search_tool(query: str):
        """Fake web search tool."""
        return [
            {"title": "Multi-Agent AI 2026", "url": "https://example.com/ai", "content": "Multi-agent systems boost enterprise efficiency by 40%."},
            {"title": "Adoption Risks", "url": "https://example.com/risks", "content": "Main risks: system latency and coordination costs."}
        ]

else:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    search_tool = TavilySearchResults(max_results=4)
    supervisor_llm = llm.with_structured_output(RouterDecision)


def run_persona(role: str, user_content: str) -> str:
    messages = [
        SystemMessage(content=PERSONAS[role]),
        HumanMessage(content=user_content)
    ]
    response = llm.invoke(messages)
    return response.content if hasattr(response, "content") else str(response)
# ============================================================
# ============================================================
# STEP 4 — THE SUPERVISOR NODE
# ============================================================
def supervisor_node(state: TeamState):
    turn_count = state.get("turn_count", 0) + 1
    
    # تجهيز ملخص الحالة الحالية للسبورة
    has_research = len(state.get("research_notes", [])) > 0
    has_analysis = bool(state.get("analysis", ""))
    has_draft = bool(state.get("draft", ""))
    revision_count = state.get("revision_count", 0)

    status_summary = (
        f"Task: {state['task']}\n"
        f"Status:\n"
        f"- Research Notes: {'Available' if has_research else 'Empty'}\n"
        f"- Analysis: {'Complete' if has_analysis else 'Pending'}\n"
        f"- Draft: {'Created' if has_draft else 'Pending'}\n"
        f"- Critique: '{state.get('critique', '')}'\n"
        f"- Revisions: {revision_count}/{MAX_REVISIONS}\n"
        f"- Turns: {turn_count}/{MAX_TURNS}"
    )

    prompt = (
        "You are the Supervisor of a Research & Writing team.\n"
        "Based on the status below, assign the NEXT worker to run.\n"
        "Order: researcher -> analyst -> writer -> critic -> (FINISH or retry)\n\n"
        f"{status_summary}"
    )

    decision: RouterDecision = supervisor_llm.invoke([
        SystemMessage(content="You are a strict team supervisor."),
        HumanMessage(content=prompt)
    ])

    next_agent = decision.next_agent

    # Guardrail 1: صمام الأمان لأقصى عدد دورات إجمالي
    if turn_count >= MAX_TURNS:
        next_agent = "FINISH"

    # Guardrail 2: صمام الأمان لأقصى عدد مراجعات وتعديلات
    if next_agent in ["writer", "critic"] and revision_count >= MAX_REVISIONS and has_draft:
        next_agent = "FINISH"

    log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] Supervisor selected '{next_agent}'. Reason: {decision.reason}"
    
    return {
        "next_agent": next_agent,
        "turn_count": turn_count,
        "execution_logs": [log_entry]
    }

# ============================================================
# ============================================================
# STEP 5 — WORKER AGENT NODES
# ============================================================
def researcher_node(state: TeamState):
    query = state["task"]
    results = search_tool.invoke({"query": query})
    
    # معالجة نتائج البحث
    if isinstance(results, dict) and "results" in results:
        results = results["results"]
        
    raw_results = ""
    if isinstance(results, list):
        for r in results:
            if isinstance(r, dict):
                raw_results += f"- Title: {r.get('title', '')}\n  Content: {r.get('content', '')}\n\n"
            else:
                raw_results += f"- {str(r)}\n"
    else:
        raw_results = str(results)

    notes = run_persona("researcher", f"Task: {query}\n\nSearch Results:\n{raw_results}")
    
    log = f"[{datetime.now().strftime('%H:%M:%S')}] Researcher completed search."
    return {
        "research_notes": [notes], # يرسلها داخل قائمة لأنها Append-only
        "execution_logs": [log]
    }


def analyst_node(state: TeamState):
    notes = "\n\n".join(state.get("research_notes", []))
    analysis_res = run_persona("analyst", f"Task: {state['task']}\n\nNotes:\n{notes}")
    
    log = f"[{datetime.now().strftime('%H:%M:%S')}] Analyst synthesized findings."
    return {
        "analysis": analysis_res,
        "execution_logs": [log]
    }


def writer_node(state: TeamState):
    critique = state.get("critique", "")
    is_revising = critique.startswith("REVISE")
    
    prompt = f"Task: {state['task']}\n\nAnalysis:\n{state.get('analysis', '')}"
    if is_revising:
        prompt += f"\n\nPrevious Draft:\n{state.get('draft', '')}\n\nCritique:\n{critique}"

    draft_res = run_persona("writer", prompt)
    new_rev_count = state.get("revision_count", 0) + (1 if is_revising else 0)

    log = f"[{datetime.now().strftime('%H:%M:%S')}] Writer created/updated draft (Rev #{new_rev_count})."

    return {
        "draft": draft_res,
        "critique": "",  # تصفير النقد ليعلم المشرف أن التعديل قد تم!
        "revision_count": new_rev_count,
        "execution_logs": [log]
    }


def critic_node(state: TeamState):
    prompt = f"Task: {state['task']}\n\nDraft:\n{state.get('draft', '')}\n\nNotes:\n{state.get('analysis', '')}"
    critique_res = run_persona("critic", prompt)
    
    log = f"[{datetime.now().strftime('%H:%M:%S')}] Critic completed review."
    return {
        "critique": critique_res,
        "execution_logs": [log]
    }


# ============================================================
# ============================================================
# STEP 6 — ROUTING & GRAPH WIRING
# ============================================================
def route_from_supervisor(state: TeamState) -> str:
    # تقرأ فقط القيمة التي حددها المشرف في خطوته السابقة
    return state["next_agent"]

builder = StateGraph(TeamState)

# إضافة العقد
builder.add_node("supervisor", supervisor_node)
builder.add_node("researcher", researcher_node)
builder.add_node("analyst", analyst_node)
builder.add_node("writer", writer_node)
builder.add_node("critic", critic_node)

# تحديد البداية
builder.add_edge(START, "supervisor")

# إضافة الشروط والمسارات المشروطة للمشرف
builder.add_conditional_edges(
    "supervisor",
    route_from_supervisor,
    {
        "researcher": "researcher",
        "analyst": "analyst",
        "writer": "writer",
        "critic": "critic",
        "FINISH": END
    }
)

# عودة كافة العمال إلى المشرف دائماً (نمط Hub & Spoke)
for worker in ["researcher", "analyst", "writer", "critic"]:
    builder.add_edge(worker, "supervisor")
# ============================================================
# STEP 7 — COMPILE, VISUALIZE, RUN
# ============================================================
# ============================================================
# STEP 7 — COMPILE & RUN
# ============================================================
checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    initial_state = {
        "task": "Should our company adopt multi-agent AI systems in 2026?",
        "research_notes": [],
        "analysis": "",
        "draft": "",
        "critique": "",
        "revision_count": 0,
        "turn_count": 0,
        "next_agent": "",
        "execution_logs": [],
    }

    config = {"configurable": {"thread_id": "day2_execution"}}

    print("Starting Multi-Agent Workflow Execution...\n")
    
    # البث وسحب التحديثات خطوة بخطوة
    for event in graph.stream(initial_state, config=config, stream_mode="values"):
        if event.get("execution_logs"):
            print(event["execution_logs"][-1])

    final_state = graph.get_state(config).values
    
    print("\n================ FINAL REPORT DRAFT ================\n")
    print(final_state.get("draft", "No draft produced."))
    print("\n====================================================")
    print(f"Total Turns Used: {final_state.get('turn_count')}")
    print(f"Total Revisions Made: {final_state.get('revision_count')}")

# ============================================================
# SELF-CHECK before you look at the solution
# ============================================================
# [ ] I can explain the supervisor pattern in one sentence
# [ ] My routing function reads state — the DECISION was made in a node
# [ ] research_notes appends; draft overwrites; I know why each
# [ ] The writer RESETS critique — I can explain what breaks if not
#     (hint: what does the supervisor see on the turn after a revision?)
# [ ] Only researcher_node touches search_tool
# [ ] My supervisor has BOTH guardrails, and I triggered EXPERIMENT 2
# [ ] My Mermaid diagram is a star: supervisor in the middle
# [ ] I can name one task where Day 1's single agent is the BETTER
#     design (multi-agent is not free: more calls, more latency,
#     more places to break — coordination must earn its cost)
#
# Stuck? Debugging order that works:
#   1. stream_mode="updates" — watch each supervisor decision + reason
#   2. print the status summary your supervisor_node builds — is the
#      LLM seeing an accurate picture of the blackboard?
#   3. check your conditional-edge dict covers ALL five decisions
#   4. only THEN open day2_lab_solution.py
# ============================================================

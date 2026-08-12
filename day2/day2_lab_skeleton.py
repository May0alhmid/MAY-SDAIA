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

# STEP 0 — Imports
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
load_dotenv()

MAX_REVISIONS = 2      # cap on writer↔critic loops
MAX_TURNS = 12         # cap on total supervisor decisions


# ============================================================
class TeamState(TypedDict):
    task: str
    research_notes: Annotated[List[str], operator.add]  # إضافة تراكمية دون مسح
    analysis: str
    draft: str
    critique: str
    revision_count: int
    turn_count: int
    next_agent: str                                     # قرار المشرف يكتب هنا
    execution_logs: Annotated[List[str], operator.add]  # سجل خط سير العمل

# ============================================================
# STEP 2 — STRUCTURED ROUTING DECISION
# ============================================================
class RouterDecision(BaseModel):
    """قرار التوجيه المنسق الذي يتخذه المشرف."""
    next_agent: Literal["researcher", "analyst", "writer", "critic", "FINISH"]
    reason: str = Field(description="جملة واحدة تشرح سبب اختيار هذا الوكيل")
# ============================================================
from langchain_openai import ChatOpenAI
from langchain_community.tools import TavilySearchResults

# 1. تعريف شخصيات الوكلاء والمهام الخاصة بكل منهم
# ============================================================
# STEP 3 — ONE LLM, FOUR PERSONAS (+ tools scoped per agent)
# ============================================================

USE_FAKE = os.getenv("USE_FAKE") == "1"

# 1. تعريف قاموس الشخصيات (تأكد من وجود هذا الجزء كاملاً)
PERSONAS = {
    "researcher": (
        "You are an expert researcher. Your ONLY job is to search for raw facts and evidence related to the task. "
        "Do NOT analyze or write drafts. Summarize key findings clearly with sources."
    ),
    "analyst": (
        "You are a senior data and business analyst. Your job is to take raw research notes and synthesize them "
        "into key strategic insights, risks, and implications. Do NOT search or write full articles."
    ),
    "writer": (
        "You are a tech journalist and professional writer. Your job is to draft a clean, engaging response "
        "based on the research and analysis. If a critique is provided, address EVERY point in the revision."
    ),
    "critic": (
        "You are an exacting editor. Review the draft against the research and analysis. "
        "If it is thorough, accurate, and ready, reply ONLY with 'APPROVED'. "
        "If it needs fixes, reply with 'REVISE: <list specific issues to fix>'."
    )
}

# 2. تهيئة النموذج والأدوات
if not USE_FAKE:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=api_key)
    supervisor_llm = llm.with_structured_output(RouterDecision)
    search_tool = TavilySearchResults(max_results=4, tavily_api_key=tavily_key)
else:
    llm = None
    supervisor_llm = None
    search_tool = None

# 3. دالة تشغيل الشخصيات
def run_persona(role: str, user_content: str) -> str:
    if USE_FAKE:
        if role == "researcher":
            return "Fake Notes: Multi-agent systems provide specialized division of labor and autonomy."
        elif role == "analyst":
            return "Fake Analysis: Adoption in 2026 reduces operational bottlenecks but increases latency."
        elif role == "writer":
            if "REVISE" in user_content:
                return "Fake Revised Draft: Comprehensive analysis on multi-agent systems adoption in 2026."
            return "Fake Initial Draft: Overview of multi-agent systems in 2026."
        elif role == "critic":
            if "Revised Draft" in user_content:
                return "APPROVED"
            return "REVISE: Please make the draft more detailed regarding trade-offs."
        return "Fake Response"

    messages = [
        SystemMessage(content=PERSONAS[role]),
        HumanMessage(content=user_content)
    ]
    response = llm.invoke(messages)
    return response.content

# ============================================================
# STEP 4 — THE SUPERVISOR NODE (the piece Day 1 didn't have)
# ============================================================
def supervisor_node(state: TeamState):
    turn_count = state.get("turn_count", 0) + 1
    
    if USE_FAKE:
        # تسلسل وهمي لقرار المشرف لاستعراض خط سير العمل (Choreography)
        if not state.get("research_notes"):
            next_agent, reason = "researcher", "Need research notes"
        elif not state.get("analysis"):
            next_agent, reason = "analyst", "Need analysis of research"
        elif not state.get("draft"):
            next_agent, reason = "writer", "Need initial draft"
        elif state.get("critique") == "APPROVED":
            next_agent, reason = "FINISH", "Draft approved"
        elif state.get("critique", "").startswith("REVISE"):
            next_agent, reason = "writer", "Need draft revision based on critique"
        else:
            next_agent, reason = "critic", "Need critique of the current draft"
    else:
        status_summary = (
            f"Task: {state['task']}\n"
            f"Research done? {'YES' if state.get('research_notes') else 'NO'}\n"
            f"Analysis done? {'YES' if state.get('analysis') else 'NO'}\n"
            f"Draft present? {'YES' if state.get('draft') else 'NO'}\n"
            f"Critique: {state.get('critique', 'None')}\n"
            f"Revision count: {state.get('revision_count', 0)}/{MAX_REVISIONS}\n"
            f"Turn count: {turn_count}/{MAX_TURNS}"
        )
        prompt = f"Given the team's current status, who should act next?\n\n{status_summary}"
        decision: RouterDecision = supervisor_llm.invoke([HumanMessage(content=prompt)])
        next_agent, reason = decision.next_agent, decision.reason

    # Guardrails
    if turn_count > MAX_TURNS:
        next_agent = "FINISH"
    elif state.get("revision_count", 0) >= MAX_REVISIONS and state.get("draft"):
        if next_agent in ["writer", "critic"]:
            next_agent = "FINISH"

    log_entry = f"Supervisor (Turn {turn_count}): Selected {next_agent}. Reason: {reason}"
    
    return {
        "next_agent": next_agent,
        "turn_count": turn_count,
        "execution_logs": [log_entry]
    }

# ============================================================
# STEP 5 — WORKER AGENT NODES
# ============================================================
def researcher_node(state: TeamState):
    if USE_FAKE:
        raw_results = "Fake search results for multi-agent systems."
    else:
        try:
            raw_results = search_tool.invoke({"query": state["task"]})
        except Exception:
            raw_results = "No search results available."

    notes = run_persona("researcher", f"Task: {state['task']}\n\nSearch Results:\n{raw_results}")
    
    return {
        "research_notes": [notes],
        "execution_logs": ["Researcher: Completed web search and extracted notes."]
    }


def analyst_node(state: TeamState):
    """تحليل الملاحظات"""
    notes_text = "\n".join(state.get("research_notes", []))
    analysis = run_persona("analyst", f"Task: {state['task']}\n\nResearch Notes:\n{notes_text}")
    
    return {
        "analysis": analysis,
        "execution_logs": ["Analyst: Synthesized research into insights."]
    }


def writer_node(state: TeamState):
    """كتابة المسودة وتعديلها عند وجود نقد"""
    critique = state.get("critique", "")
    is_revising = critique.startswith("REVISE")

    prompt = f"Task: {state['task']}\n\nAnalysis:\n{state.get('analysis', '')}\n"
    if is_revising:
        prompt += f"\nPrevious Draft:\n{state.get('draft', '')}\n\nCritique to fix:\n{critique}"

    new_draft = run_persona("writer", prompt)
    rev_count = state.get("revision_count", 0) + (1 if is_revising else 0)

    return {
        "draft": new_draft,
        "critique": "",  # إعادة ضبط النقد حتى لا يعيد المشرف وقائع النقد السابق
        "revision_count": rev_count,
        "execution_logs": [f"Writer: {'Revised' if is_revising else 'Wrote initial'} draft."]
    }


def critic_node(state: TeamState):
    """مراجعة المسودة"""
    prompt = (
        f"Task: {state['task']}\n\n"
        f"Research Notes:\n{'\n'.join(state.get('research_notes', []))}\n\n"
        f"Draft:\n{state.get('draft', '')}"
    )
    critique = run_persona("critic", prompt)
    
    return {
        "critique": critique,
        "execution_logs": [f"Critic: Evaluated draft -> {critique[:30]}..."]
    }
# ============================================================
# STEP 6 — ROUTING FUNCTION + WIRE THE GRAPH
# ============================================================
# دالة التوجيه بناءً على قرار المشرف
def route_from_supervisor(state: TeamState) -> str:
    return state["next_agent"]

# بناء الرسم البياني
builder = StateGraph(TeamState)

# 1. إضافة العقود
builder.add_node("supervisor", supervisor_node)
builder.add_node("researcher", researcher_node)
builder.add_node("analyst", analyst_node)
builder.add_node("writer", writer_node)
builder.add_node("critic", critic_node)

# 2. النقطة الابتدائية
builder.add_edge(START, "supervisor")

# 3. مسارات التوجيه المشروطة من المشرف
builder.add_conditional_edges(
    "supervisor",
    route_from_supervisor,
    {
        "researcher": "researcher",
        "analyst": "analyst",
        "writer": "writer",
        "critic": "critic",
        "FINISH": END,
    }
)

# 4. إعادة التقرير من كل وكيل تنفيذي إلى المشرف (شكل النجمة / Hub-and-Spoke)
for worker in ["researcher", "analyst", "writer", "critic"]:
    builder.add_edge(worker, "supervisor")

# ============================================================
# STEP 7 — COMPILE, VISUALIZE, RUN
if __name__ == "__main__":
    checkpointer = InMemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

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

    config = {"configurable": {"thread_id": "day2_lab"}}

    print("--- STARTING MULTI-AGENT WORKFLOW ---")
    for event in graph.stream(initial_state, config=config, stream_mode="values"):
        logs = event.get("execution_logs", [])
        if logs:
            print(f"-> {logs[-1]}")

    final_state = graph.get_state(config).values
    print("\n================ FINAL DRAFT ================")
    print(final_state.get("draft", "No draft generated."))
    print("=============================================")
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

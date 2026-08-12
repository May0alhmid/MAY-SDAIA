"""
DAY 3 — Agent implementation.

READ FIRST:  ../01-deep-agents.md

Do not continue to api.py until:
    USE_FAKE=1 uv run python src/agent.py
prints a reply, AND (with real keys) the agent answers using its tools.

The contract this file must satisfy — the ONLY thing api.py will rely on:

    def build_agent() -> object with .ainvoke({"messages": [...]})
"""

import asyncio
import datetime
import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# ---------------------------------------------------------------------------
# 1. Tools
# ---------------------------------------------------------------------------

@tool
def calculate(expression: str) -> str:
    """Calculate a mathematical expression safely."""
    try:
        # Simple arithmetic evaluation
        allowed_names = {"abs": abs, "round": round}
        code = compile(expression, "<string>", "eval")
        for name in code.co_names:
            if name not in allowed_names:
                raise NameError(f"Use of {name} is not allowed")
        result = eval(code, {"__builtins__": None}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"


@tool
def current_time() -> str:
    """Get the current UTC date and time."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------------------
# Fake Agent for testing without API keys (USE_FAKE=1)
# ---------------------------------------------------------------------------

class FakeAgent:
    """A minimal mock agent for testing the contract without external API calls."""

    async def ainvoke(self, input_data: dict) -> dict:
        messages = input_data.get("messages", [])
        user_query = messages[-1].content if messages else "Hello"
        
        reply = (
            f"[FAKE AGENT] Received query: '{user_query}'. "
            f"Current fake time is 2026-08-12 12:00:00 UTC. "
            f"Fake calculation result: 42."
        )
        
        return {"messages": messages + [AIMessage(content=reply)]}


# ---------------------------------------------------------------------------
# 2. build_agent()
# ---------------------------------------------------------------------------

def build_agent():
    """Build and return an agent instance satisfying .ainvoke contract."""
    
    # Check if Fake Mode is requested
    if os.getenv("USE_FAKE") == "1":
        print("── Building agent in FAKE mode (USE_FAKE=1)")
        return FakeAgent()

    print("── Building real Deep Agent...")
    
    # Deep Agents frameworks import
    try:
        from deep_agents import create_deep_agent
        from deep_agents.backends import FilesystemBackend
    except ImportError:
        from deep_agents import FilesystemBackend, create_deep_agent

    # Base directory (day3 root)
    day3_dir = Path(__file__).parent.parent.resolve()

    # OpenRouter / OpenAI configuration
    model_name = os.getenv("MODEL", "openai/gpt-4o-mini")
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    system_prompt = (
        "You are a helpful AI assistant equipped with calculation and time tools. "
        "Use your tools whenever you need to calculate math or know the current time."
    )

    agent = create_deep_agent(
        model=llm,
        tools=[calculate, current_time],
        system_prompt=system_prompt,
        backend=FilesystemBackend(root_dir=str(day3_dir), virtual_mode=True),
        skills=[str(day3_dir / "skills")],
    )

    return agent


# ---------------------------------------------------------------------------
# 3. Smoke Test (__main__)
# ---------------------------------------------------------------------------

async def main():
    agent = build_agent()
    print("── Running smoke test ...")

    sample_query = "What is 25 * 4 and what is the current time?"
    test_input = {"messages": [HumanMessage(content=sample_query)]}

    response = await agent.ainvoke(test_input)
    
    messages = response.get("messages", [])
    if messages:
        last_message = messages[-1]
        print("\n── Agent replied:\n")
        print(last_message.content)
    else:
        print("\n── No messages returned in response.")


if __name__ == "__main__":
    asyncio.run(main())
"""
DAY 4 — Deep Agent with shell access.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

WORK_DIR = Path(__file__).resolve().parent.parent / "work"
WORK_DIR.mkdir(exist_ok=True)

from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="nvidia/nemotron-3-super-120b-a12b:free",
    temperature=0,
    base_url="https://openrouter.ai/api/v1",
)

SYSTEM_PROMPT = (
    "You are a coding agent with real shell access. Write files, run commands, "
    "read error output, and fix problems iteratively until the task succeeds."
)


def make_backend():
    from deepagents.backends import LocalShellBackend

    backend = LocalShellBackend(
        root_dir=str(WORK_DIR),
        virtual_mode=True,
        env={"PATH": os.environ["PATH"]},
    )
    cleanup = lambda: None  # local machine — nothing to tear down
    return backend, cleanup


if __name__ == "__main__":
    from deepagents import create_deep_agent

    backend, cleanup = make_backend()
    agent = create_deep_agent(model=llm, system_prompt=SYSTEM_PROMPT, backend=backend)

    task = (
        "1. Create calculator.py with add/sub/mul/div functions (div raises "
        "ValueError on division by zero). "
        "2. Write pytest tests for all four, including the zero-division case. "
        "3. Run them with execute: 'python -m pytest' (pip install pytest first if missing). "
        "4. Fix any failures until all tests pass (green). "
        "5. Report the final pytest output."
    )

    try:
        result = asyncio.run(agent.ainvoke({"messages": [{"role": "user", "content": task}]}))
        print(result["messages"][-1].content)
    finally:
        cleanup()
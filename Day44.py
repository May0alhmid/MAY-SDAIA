"""
DAY 4 — Deep Agent Shell Backend.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend

load_dotenv()

# تعريف SYSTEM_PROMPT ليكون قابلاً للإستيراد من الملفات الأخرى
SYSTEM_PROMPT = (
    "You are a helpful AI assistant with access to a bash shell environment. "
    "Use shell commands when needed to fulfill the user's request."
)

api_key = os.getenv("OPENROUTER_API_KEY") or "sk-or-v1-dummy-key-1234567890abcdef"

llm = ChatOpenAI(
    model=os.getenv("MODEL_NAME", "google/gemini-2.5-flash"),
    openai_api_key=api_key,
    openai_api_base="https://openrouter.ai/api/v1",
)


def make_backend(kind: str = "local"):
    if kind == "local":
        work_dir = Path(__file__).parent.parent / "work"
        work_dir.mkdir(exist_ok=True)
        backend = LocalShellBackend(
            root_dir=str(work_dir),
            virtual_mode=True,
            env={"PATH": os.environ.get("PATH", "")},
        )
        return backend, lambda: None
    else:
        raise ValueError(f"Unknown backend type: {kind}")


if __name__ == "__main__":
    backend, cleanup = make_backend("local")
    try:
        agent = create_deep_agent(llm, system_prompt=SYSTEM_PROMPT, backend=backend)
        task = "Write a python script that calculates 15 * 8, saves it to calc.py, runs it, and tells me the result."
        result = agent.invoke({"messages": [{"role": "user", "content": task}]})
        print(result["messages"][-1].content)
    finally:
        cleanup()
"""
DAY 3 — HTTP API.

READ FIRST:  ../03-fastapi-openresponses.md
             ../09-a2a.md   (for the agent card endpoint)

Do not continue to 04-docker.md until:
    curl http://localhost:8000/healthz            -> {"status":"ok"}
    curl -X POST http://localhost:8000/v1/responses \
         -H 'Content-Type: application/json' -d '{"input":"hi"}'
returns an OpenResponses-shaped JSON object.
"""

import os
import time
import uuid

from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agent import build_agent

# ---------------------------------------------------------------------------
# 1. App + agent — built ONCE, at startup
# ---------------------------------------------------------------------------

app = FastAPI(title="Day 3 Agent API")
agent = build_agent()


# ---------------------------------------------------------------------------
# 2. Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 3. OpenResponses-shaped endpoint
# ---------------------------------------------------------------------------

class ResponsesRequest(BaseModel):
    input: str
    model: str | None = None


@app.post("/v1/responses")
async def create_response(req: ResponsesRequest):
    result = await agent.ainvoke({"messages": [HumanMessage(content=req.input)]})

    messages = result.get("messages", [])
    reply_text = messages[-1].content if messages else ""

    return {
        "id": f"resp_{uuid.uuid4().hex}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": req.model or os.getenv("MODEL", "openai/gpt-4o-mini"),
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": reply_text}
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# 4. A2A Agent Card
# ---------------------------------------------------------------------------

@app.get("/.well-known/agent-card.json")
async def agent_card():
    student_name = os.getenv("STUDENT_NAME", "unknown-student")
    public_url = os.getenv("PUBLIC_URL", "http://localhost:8000")

    return {
        "name": student_name,
        "description": f"{student_name}'s Day 3 agent — calculation and time tools.",
        "version": "1.0.0",
        "url": f"{public_url.rstrip('/')}/v1/responses",
        "skills": [
            {"name": "calculate", "description": "Evaluate a mathematical expression safely."},
            {"name": "current_time", "description": "Get the current UTC date and time."},
        ],
    }

from fastapi import FastAPI
from src.agent import build_agent

app = FastAPI(title="AAASEC2 Day 3 Agent")
agent = build_agent()

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

from pydantic import BaseModel
from typing import Optional
import time
import uuid

class ResponseRequest(BaseModel):
    input: str
    model: Optional[str] = None

@app.post("/v1/responses")
async def create_response(req: ResponseRequest):
    result = await agent.ainvoke({"messages": [{"role": "user", "content": req.input}]})
    text = result["messages"][-1].content

    return {
        "id": f"resp_{uuid.uuid4().hex[:12]}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": req.model or "day3-agent",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }

import os

@app.get("/.well-known/agent-card.json")
def agent_card():
    student = os.getenv("STUDENT_NAME", "faisal")
    public_url = os.getenv("PUBLIC_URL", "http://localhost:8000")
    return {
        "protocolVersion": "1.0",
        "name": f"{student}-agent",
        "description": "A research and analysis agent that produces structured research briefs and Conventional Commits-style commit messages.",
        "url": f"{public_url}/v1/responses",
        "version": "0.1.0",
        "capabilities": {"streaming": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "research-brief",
                "name": "Research Brief",
                "description": "Write a one-page executive research brief on a technical topic.",
                "tags": ["research", "writing"],
            },
            {
                "id": "commit-message",
                "name": "Commit Message",
                "description": "Write a Conventional Commits-style commit message from a description of a code change.",
                "tags": ["git", "dev-tools"],
            },
        ],
    }


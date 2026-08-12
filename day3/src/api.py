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

@app.get("/.well-known/agent-card.json")
def agent_card():
    return {"todo": True}
"""
DAY 4 — Authenticated MCP server.
"""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth import StaticTokenVerifier
from fastmcp.server.auth import require_scopes
load_dotenv()

STUDENT_TOKEN = os.getenv("MCP_STUDENT_TOKEN", "student-secret-token")
ADMIN_TOKEN = os.getenv("MCP_ADMIN_TOKEN", "admin-secret-token")

verifier = StaticTokenVerifier(tokens={
    STUDENT_TOKEN: {"client_id": "student", "scopes": ["read:public"]},
    ADMIN_TOKEN:   {"client_id": "admin", "scopes": ["read:public", "read:internal"]},
})

mcp = FastMCP("Secure Tools", auth=verifier)


@mcp.tool
def get_server_time() -> str:
    """Return the current UTC time. Available to any authenticated client."""
    return datetime.now(timezone.utc).isoformat()


@mcp.tool(auth=require_scopes("read:internal"))
def get_internal_report() -> dict:
    """Return an internal report. Requires read:internal scope (admin only)."""
    return {
        "quarterly_revenue": 152000,
        "quarterly_costs": 98000,
        "confidential": True,
    }


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8002)
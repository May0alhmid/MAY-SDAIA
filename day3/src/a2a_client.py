"""
DAY 3 — A2A discovery + delegation client.

Usage:
    uv run python src/a2a_client.py http://<peer> "task for their agent"
"""

import sys

import httpx


def discover(peer_base_url: str) -> dict:
    """GET the peer's agent card, print its name + skills, return the card."""
    resp = httpx.get(f"{peer_base_url}/.well-known/agent-card.json", timeout=10)
    resp.raise_for_status()
    card = resp.json()
    print(f"Discovered: {card['name']}")
    for skill in card.get("skills", []):
        print(f"  - {skill['id']}: {skill['description']}")
    return card


def delegate(card: dict, task: str) -> str:
    """POST the task to the URL advertised in the card — never hardcode it."""
    resp = httpx.post(card["url"], json={"input": task}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["output"][0]["content"][0]["text"]


if __name__ == "__main__":
    peer_url = sys.argv[1]
    task = sys.argv[2]

    card = discover(peer_url)
    result = delegate(card, task)
    print("\n--- Result ---")
    print(result)
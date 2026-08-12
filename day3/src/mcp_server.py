"""
DAY 3 — MCP server.
"""

from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider

mcp = FastMCP("Faisal Tools")


@mcp.tool
def calculate(expression: str) -> float:
    """Evaluate a basic arithmetic expression, e.g. '2 * (3+4) ** 2'."""
    import ast
    import operator as op

    _ALLOWED = {
        ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
        ast.Div: op.truediv, ast.Pow: op.pow, ast.USub: op.neg, ast.Mod: op.mod,
    }

    def _safe_eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](_safe_eval(node.operand))
        raise ValueError("only basic arithmetic is allowed")

    return _safe_eval(ast.parse(expression, mode="eval").body)


@mcp.tool
def word_stats(text: str) -> dict:
    """Return word count, character count, and average word length for a piece of text."""
    words = text.split()
    return {
        "word_count": len(words),
        "char_count": len(text),
        "avg_word_length": round(sum(len(w) for w in words) / len(words), 2) if words else 0,
    }


# 07 — makes your skills/ folder discoverable as MCP resources (skill://...)
mcp.add_provider(SkillsDirectoryProvider(roots=Path(__file__).parent.parent / "skills"))


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001)
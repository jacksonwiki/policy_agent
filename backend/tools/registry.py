"""Tool registry — manages tool registration, risk levels, and metadata."""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from langchain_core.tools import BaseTool


class RiskLevel(str, Enum):
    LOW = "low"
    HIGH = "high"


# Tool metadata: name → {fn, description, risk, params_schema}
TOOL_REGISTRY: dict[str, dict] = {}

# Tool risk levels
TOOL_RISK: dict[str, RiskLevel] = {}


def register_tool(
    name: str,
    fn: BaseTool | Callable,
    description: str = "",
    risk: RiskLevel = RiskLevel.LOW,
) -> None:
    """Register a tool in the registry.

    Args:
        name: Unique tool name
        fn: LangChain tool or callable
        description: Human-readable description for LLM tool planning
        risk: Risk level (LOW = auto-execute, HIGH = requires HITL)
    """
    TOOL_REGISTRY[name] = {
        "fn": fn,
        "description": description,
        "risk": risk,
    }
    TOOL_RISK[name] = risk


def get_tool(name: str) -> dict | None:
    """Get tool metadata by name."""
    return TOOL_REGISTRY.get(name)


def get_all_descriptions() -> str:
    """Return formatted descriptions of all registered tools (for LLM prompts)."""
    lines = []
    for name, info in TOOL_REGISTRY.items():
        risk_tag = "[HIGH RISK] " if info["risk"] == RiskLevel.HIGH else ""
        lines.append(f"- {name}: {risk_tag}{info['description']}")
    return "\n".join(lines)


# ── Auto-import & register all tools ─────────────────────
def _auto_register() -> None:
    """Import all tool modules so they self-register."""
    from . import policy_query  # noqa: F401
    from . import claim_query  # noqa: F401
    from . import high_risk  # noqa: F401


_auto_register()

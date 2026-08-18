"""Tool sub-graph: planning → execution (with HITL for high-risk tools) → result aggregation."""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command

from ...config import get_settings
from ...llm import get_llm, TaskType
from ...tools.registry import TOOL_REGISTRY, TOOL_RISK, RiskLevel
from ...core.state import ToolCall, ToolResult, HitlReview


# ── Tool sub-graph state ─────────────────────────────────
class ToolSubState(dict):
    tool_plan: list[ToolCall]
    tool_results: list[ToolResult]
    hitl_reviews: list[HitlReview]
    iteration: int


def _plan_tools(state: ToolSubState) -> dict:
    """Node 1: LLM decides which tools to call and with what args."""
    user_query = state.get("user_query", "")
    thread_id = state.get("thread_id", "")

    llm = get_llm(TaskType.HEAVY)

    # Build tool descriptions
    tool_descriptions = "\n".join([
        f"- {name}: {info['description']}"
        for name, info in TOOL_REGISTRY.items()
    ])

    prompt = f"""根据用户问题，决定需要调用哪些保险业务工具。

用户问题：{user_query}

可用工具：
{tool_descriptions}

请以JSON数组格式输出需要调用的工具列表：
[{{"name": "工具名", "args": {{参数}}}}]

如果不需要调用任何工具，输出空数组 []"""

    from langchain_core.messages import HumanMessage, SystemMessage

    response = llm.invoke([
        SystemMessage(content="你是保险业务工具规划专家。请根据用户问题选择最合适的工具。"),
        HumanMessage(content=prompt),
    ])

    import json
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw[:-3]

    try:
        plan_data = json.loads(raw)
        if isinstance(plan_data, list):
            tool_plan = [ToolCall(**item) for item in plan_data]
        else:
            tool_plan = _rule_based_plan(user_query)
    except (json.JSONDecodeError, TypeError):
        tool_plan = _rule_based_plan(user_query)

    return {"tool_plan": tool_plan, "iteration": 0}


# ── Rule-based fallback for when LLM planning fails ───────
_TOOL_KEYWORDS = {
    "query_policies": (["我的保单", "所有保单", "保单列表", "我的保险"], {"user_id": "current_user"}),
    "query_policy_detail": (["保单详情", "保单号", "详细信息"], {"policy_no": "P20240001"}),
    "query_payment_records": (["缴费记录", "缴费历史", "缴费情况"], {"user_id": "current_user"}),
    "query_claims": (["理赔", "理赔记录", "我的理赔", "出险"], {"user_id": "current_user"}),
    "query_claim_detail": (["理赔详情", "理赔进度", "理赔状态"], {"claim_no": "C20250001"}),
    "underwrite": (["核保", "审核"], {"application_id": "APP_001"}),
    "make_payment": (["支付", "缴费", "付款"], {"policy_no": "P20240001", "amount": 1000, "payment_type": "premium"}),
    "issue_policy": (["出单", "签单", "发单"], {"application_id": "APP_001"}),
    "cancel_policy": (["退保", "解约"], {"policy_no": "P20240001"}),
}


def _rule_based_plan(user_query: str) -> list[ToolCall]:
    """Simple keyword-based tool planning as fallback."""
    plan: list[ToolCall] = []
    for tool_name, (keywords, default_args) in _TOOL_KEYWORDS.items():
        for kw in keywords:
            if kw in user_query:
                plan.append(ToolCall(name=tool_name, args=default_args))
                break
    return plan


def _execute_tools(state: ToolSubState) -> dict:
    """Node 2: execute each tool, pausing for high-risk tools via HITL."""
    tool_plan = state.get("tool_plan", [])
    existing_results = state.get("tool_results", [])
    iteration = state.get("iteration", 0)
    thread_id = state.get("thread_id", "")

    results: list[ToolResult] = list(existing_results)
    new_reviews: list[HitlReview] = []

    max_rounds = get_settings().agent_max_tool_rounds

    for call in tool_plan:
        # Check risk level
        risk = TOOL_RISK.get(call.name, RiskLevel.LOW)

        if risk == RiskLevel.HIGH:
            # HITL: pause graph and wait for human input
            review_id = str(uuid.uuid4())
            review = HitlReview(
                review_id=review_id,
                thread_id=thread_id,
                tool_name=call.name,
                tool_args=call.args,
                status="pending",
                reason="高风险操作，需人工确认",
            )
            new_reviews.append(review)

            # Interrupt — this pauses the graph execution
            # The frontend will receive this review and present an approval UI
            human_decision = interrupt({
                "type": "hitl_review",
                "review_id": review_id,
                "tool": call.name,
                "args": call.args,
                "reason": "高风险操作，请人工确认",
                "risk_level": "HIGH",
            })

            # After resume, human_decision contains the decision
            action = human_decision.get("action", "reject")

            if action == "reject":
                results.append(ToolResult(
                    name=call.name,
                    args=call.args,
                    error="用户拒绝执行",
                    tool_call_id=call.tool_call_id,
                ))
                continue
            elif action == "modify":
                call.args = human_decision.get("modified_args", call.args)

            # If approve or modify, proceed to execute

        # Execute the tool
        tool_info = TOOL_REGISTRY.get(call.name)
        if tool_info is None:
            results.append(ToolResult(
                name=call.name,
                args=call.args,
                error=f"工具 {call.name} 未注册",
                tool_call_id=call.tool_call_id,
            ))
            continue

        try:
            tool_fn = tool_info["fn"]
            result = tool_fn.invoke(call.args)
            results.append(ToolResult(
                name=call.name,
                args=call.args,
                result=result,
                tool_call_id=call.tool_call_id,
            ))
        except Exception as e:
            results.append(ToolResult(
                name=call.name,
                args=call.args,
                error=str(e),
                tool_call_id=call.tool_call_id,
            ))

    # Check if we need another round of planning
    new_iteration = iteration + 1

    return {
        "tool_results": results,
        "hitl_reviews": new_reviews,
        "iteration": new_iteration,
    }


def _should_continue(state: ToolSubState) -> str:
    """Decide whether to re-plan tools or end the tool sub-graph."""
    tool_plan = state.get("tool_plan", [])
    tool_results = state.get("tool_results", [])
    iteration = state.get("iteration", 0)

    # If no tools were planned, end
    if not tool_plan:
        return "end"

    # If we've hit max rounds, end
    max_rounds = get_settings().agent_max_tool_rounds
    if iteration >= max_rounds:
        return "end"

    # Check if any tool results indicate a need for more tools
    # (e.g., a query returned IDs that need follow-up queries)
    # For now, we end after one round — can extend to multi-round later
    return "end"


def build_tool_subgraph(checkpointer=None) -> StateGraph:
    """Construct the tool sub-graph with HITL support."""
    graph = StateGraph(ToolSubState)

    graph.add_node("plan_tools", _plan_tools)
    graph.add_node("execute_tools", _execute_tools)

    graph.set_entry_point("plan_tools")
    graph.add_edge("plan_tools", "execute_tools")
    graph.add_conditional_edges(
        "execute_tools",
        _should_continue,
        {
            "end": END,
            "continue": "plan_tools",
        },
    )

    return graph.compile(checkpointer=checkpointer)
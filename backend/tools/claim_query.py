"""Claim query tools (mock — replace with real HTTP calls later)."""
from __future__ import annotations

from langchain_core.tools import tool

from .registry import register_tool, RiskLevel


@tool
def query_claims(user_id: str, status: str | None = None) -> dict:
    """查询用户的理赔记录。

    Args:
        user_id: 用户ID
        status: 理赔状态(待处理/处理中/已赔付/已拒绝)，可选
    Returns:
        理赔记录列表
    """
    return {
        "claims": [
            {
                "claim_no": "C20250001",
                "policy_no": "P20240001",
                "type": "重疾理赔",
                "amount": 200000,
                "status": "处理中",
                "submit_date": "2025-06-01",
                "update_date": "2025-07-10",
                "handler": "王经理",
            },
            {
                "claim_no": "C20240002",
                "policy_no": "P20240002",
                "type": "医疗理赔",
                "amount": 8500,
                "status": "已赔付",
                "submit_date": "2024-08-15",
                "settle_date": "2024-09-20",
            },
        ],
        "_mock": True,
    }


@tool
def query_claim_detail(claim_no: str) -> dict:
    """查询理赔详情。

    Args:
        claim_no: 理赔号
    Returns:
        理赔详情
    """
    return {
        "claim_no": claim_no,
        "policy_no": "P20240001",
        "type": "重疾理赔",
        "amount": 200000,
        "status": "处理中",
        "progress": [
            {"date": "2025-06-01", "action": "提交理赔申请"},
            {"date": "2025-06-05", "action": "材料审核通过"},
            {"date": "2025-06-15", "action": "医疗核实完成"},
            {"date": "2025-07-10", "action": "赔付计算中"},
        ],
        "estimated_settle_date": "2025-08-15",
        "_mock": True,
    }


register_tool(
    "query_claims",
    query_claims,
    description="查询用户的理赔记录列表，可按状态筛选",
    risk=RiskLevel.LOW,
)
register_tool(
    "query_claim_detail",
    query_claim_detail,
    description="根据理赔号查询理赔详情和处理进度",
    risk=RiskLevel.LOW,
)

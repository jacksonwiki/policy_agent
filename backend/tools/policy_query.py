"""Policy query tools (mock — replace with real HTTP calls later)."""
from __future__ import annotations

from langchain_core.tools import tool

from .registry import register_tool, RiskLevel


@tool
def query_policies(user_id: str, policy_type: str | None = None) -> dict:
    """查询用户名下所有保单。

    Args:
        user_id: 用户ID
        policy_type: 保单类型(寿险/健康险/意外险)，可选
    Returns:
        保单列表
    """
    # TODO: Replace with real HTTP call
    # resp = httpx.post(f"{settings.POLICY_API}/query", json={"user_id": user_id, "policy_type": policy_type})
    # return resp.json()
    return {
        "policies": [
            {
                "policy_no": "P20240001",
                "type": "寿险",
                "status": "有效",
                "holder": user_id,
                "sum_insured": 500000,
                "premium": 3000,
                "pay_method": "年缴",
                "start_date": "2024-01-15",
                "end_date": "2054-01-14",
            },
            {
                "policy_no": "P20240002",
                "type": "健康险",
                "status": "有效",
                "holder": user_id,
                "sum_insured": 1000000,
                "premium": 2500,
                "pay_method": "月缴",
                "start_date": "2024-03-20",
                "end_date": "2027-03-19",
            },
        ],
        "_mock": True,
    }


@tool
def query_policy_detail(policy_no: str) -> dict:
    """查询保单详情。

    Args:
        policy_no: 保单号
    Returns:
        保单详情
    """
    return {
        "policy_no": policy_no,
        "type": "寿险",
        "status": "有效",
        "holder": "张三",
        "beneficiary": "李四",
        "sum_insured": 500000,
        "premium": 3000,
        " riders": [
            {"name": "重疾险附加", "sum_insured": 200000},
            {"name": "意外险附加", "sum_insured": 100000},
        ],
        "surrender_value": 15000,
        "_mock": True,
    }


@tool
def query_payment_records(user_id: str) -> dict:
    """查询缴费记录。

    Args:
        user_id: 用户ID
    Returns:
        缴费记录列表
    """
    return {
        "records": [
            {
                "policy_no": "P20240001",
                "amount": 3000,
                "date": "2025-01-15",
                "method": "银行代扣",
                "status": "成功",
            },
            {
                "policy_no": "P20240001",
                "amount": 3000,
                "date": "2024-01-15",
                "method": "银行代扣",
                "status": "成功",
            },
        ],
        "_mock": True,
    }


# Register all tools
register_tool(
    "query_policies",
    query_policies,
    description="查询用户名下所有保单列表，可按保单类型筛选",
    risk=RiskLevel.LOW,
)
register_tool(
    "query_policy_detail",
    query_policy_detail,
    description="根据保单号查询保单详细信息，包括附加险、现金价值等",
    risk=RiskLevel.LOW,
)
register_tool(
    "query_payment_records",
    query_payment_records,
    description="查询用户的缴费记录历史",
    risk=RiskLevel.LOW,
)

"""High-risk tools: underwrite, payment, issue_policy, cancel_policy.

These tools require HITL (human-in-the-loop) verification before execution.
"""
from __future__ import annotations

from langchain_core.tools import tool

from .registry import register_tool, RiskLevel


@tool
def underwrite(application_id: str, applicant_id: str = "") -> dict:
    """核保 — 审核投保申请。

    ⚠️ 高风险操作，需人工确认后执行。

    Args:
        application_id: 投保申请ID
        applicant_id: 投保人ID
    Returns:
        核保结果
    """
    # TODO: Real HTTP call
    return {
        "application_id": application_id,
        "result": "核保通过",
        "risk_level": "标准",
        "extra_premium": 0,
        "_mock": True,
    }


@tool
def make_payment(policy_no: str, amount: float, payment_type: str = "premium") -> dict:
    """支付 — 执行保费支付或退保退款。

    ⚠️ 高风险操作，需人工确认后执行。

    Args:
        policy_no: 保单号
        amount: 金额(元)
        payment_type: 支付类型(premium保费/refund退款)
    Returns:
        支付结果
    """
    # TODO: Real HTTP call
    return {
        "policy_no": policy_no,
        "amount": amount,
        "type": payment_type,
        "status": "支付成功",
        "transaction_id": f"TXN_{policy_no}_{int(amount)}",
        "_mock": True,
    }


@tool
def issue_policy(application_id: str) -> dict:
    """出单 — 正式签发保单。

    ⚠️ 高风险操作，需人工确认后执行。

    Args:
        application_id: 投保申请ID
    Returns:
        出单结果
    """
    # TODO: Real HTTP call
    return {
        "application_id": application_id,
        "policy_no": f"P{application_id}",
        "status": "已出单",
        "issue_date": "2025-01-15",
        "_mock": True,
    }


@tool
def cancel_policy(policy_no: str, reason: str = "") -> dict:
    """退保 — 解除保单合同。

    ⚠️ 高风险操作，需人工确认后执行。

    Args:
        policy_no: 保单号
        reason: 退保原因
    Returns:
        退保结果
    """
    # TODO: Real HTTP call
    return {
        "policy_no": policy_no,
        "status": "已退保",
        "surrender_amount": 15000,
        "reason": reason,
        "_mock": True,
    }


register_tool(
    "underwrite",
    underwrite,
    description="核保审核，审核投保申请是否通过。高风险操作，需人工确认",
    risk=RiskLevel.HIGH,
)
register_tool(
    "make_payment",
    make_payment,
    description="支付操作，执行保费缴纳或退保退款。高风险操作，需人工确认",
    risk=RiskLevel.HIGH,
)
register_tool(
    "issue_policy",
    issue_policy,
    description="出单操作，正式签发保单。高风险操作，需人工确认",
    risk=RiskLevel.HIGH,
)
register_tool(
    "cancel_policy",
    cancel_policy,
    description="退保操作，解除保单合同。高风险操作，需人工确认",
    risk=RiskLevel.HIGH,
)

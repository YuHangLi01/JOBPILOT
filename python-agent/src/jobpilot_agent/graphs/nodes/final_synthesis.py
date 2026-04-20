"""final_synthesis 节点：使用 LLM 生成最终结构化分析报告。

职责：
- 将 parsed_jd + classification + merged_skill_data 传递给 LLM
- 验证输出符合 JDRoutingResults 结构（宽松校验：字段缺失时填充空值）
- 写入 state["final_result"]，附带 interview_invitation 字段
- LLM 失败时降级为仅包含 jd_summary 的最小结果（基于 parsed_jd）

输入 state 字段：parsed_jd, classification, merged_skill_data, skill_outputs, errors
输出 state 字段：final_result, metadata (final_synthesis key), errors
"""

from __future__ import annotations

import time
from typing import Any

from jobpilot_agent.graphs.prompts import final_synthesis as _p
from jobpilot_agent.graphs.state import JDRoutingState
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


def _make_fallback_result(parsed_jd: dict[str, Any]) -> dict[str, Any]:
    """LLM 失败时生成最小可用结果（基于 parsed_jd）。"""
    position = parsed_jd.get("position", "该职位")
    company = parsed_jd.get("company", "")
    company_str = f"（{company}）" if company else ""
    return {
        "jd_summary": f"{position}{company_str}：由于分析服务暂时不可用，无法生成详细建议，请稍后重试。",
        "resume_advice": [],
        "interview_questions": [],
    }


def _sanitize_result(raw: dict[str, Any]) -> dict[str, Any]:
    """将 LLM 输出宽松规整为 JDRoutingResults 结构。

    字段缺失时填充空值，不抛 ValidationError。
    """
    return {
        "jd_summary": str(raw.get("jd_summary") or ""),
        "resume_advice": raw.get("resume_advice") if isinstance(raw.get("resume_advice"), list) else [],
        "interview_questions": raw.get("interview_questions") if isinstance(raw.get("interview_questions"), list) else [],
    }


def _should_invite_interview(
    classification: dict[str, Any],
    skill_outputs: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> bool:
    """纯规则判断是否邀请面试（不调用 LLM）。

    必要条件：
    1. 无致命错误
    2. 至少一个 Skill 成功执行
    3. interview_rag Skill 有结果且面经覆盖 >= 3 条
    4. job_type 不是 mgmt（高管岗模拟面试意义较小）
    """
    if errors:
        return False

    successful = [o for o in skill_outputs if o.get("success")]
    if not successful:
        return False

    rag_output = next(
        (o for o in successful if o.get("skill_name") == "interview_rag"),
        None,
    )
    if not rag_output:
        return False

    if rag_output.get("data", {}).get("retrieved_count", 0) < 3:
        return False

    if classification.get("job_type") == "mgmt":
        return False

    return True


def _build_interview_invitation(
    classification: dict[str, Any],
    parsed_jd: dict[str, Any],
) -> dict[str, Any]:
    company = parsed_jd.get("company") or "目标公司"
    position = parsed_jd.get("position") or "目标岗位"

    focus_stages = ["intro", "project_deep_dive", "tech_qa"]
    if classification.get("level") in ("senior", "lead"):
        focus_stages.append("scenario")

    return {
        "should_invite": True,
        "reason": f"已完成对 {company} · {position} 的分析，建议针对该岗位进行模拟面试",
        "suggested_company": company,
        "suggested_position": position,
        "cta_text": f"开始针对 {company} 的模拟面试",
        "session_seed": {
            "recommended_focus_stages": focus_stages,
        },
    }


async def final_synthesis(state: JDRoutingState) -> dict[str, Any]:
    """调用 LLM 生成最终求职建议报告，并附带面试邀请判断。

    Args:
        state: 当前图状态。

    Returns:
        state 增量字典：final_result + metadata + errors（仅失败时有值）。
    """
    start = time.monotonic()
    parsed_jd: dict[str, Any] = state.get("parsed_jd") or {}
    classification: dict[str, Any] = state.get("classification") or {}
    merged_skill_data: dict[str, Any] = state.get("merged_skill_data") or {}
    skill_outputs: list[dict[str, Any]] = state.get("skill_outputs") or []
    errors: list[dict[str, Any]] = state.get("errors") or []

    try:
        llm = get_llm_client()
        result, usage = await llm.chat_json(
            system=_p.SYSTEM_PROMPT,
            user=_p.build_user_prompt(parsed_jd, classification, merged_skill_data),
            schema=None,
        )
        final_result = _sanitize_result(result if isinstance(result, dict) else {})

        # 判断是否邀请面试（纯规则，不调 LLM）
        if _should_invite_interview(classification, skill_outputs, errors):
            final_result["interview_invitation"] = _build_interview_invitation(
                classification, parsed_jd
            )
        else:
            final_result["interview_invitation"] = None

        log.info(
            "final_synthesis.success",
            advice_count=len(final_result["resume_advice"]),
            question_count=len(final_result["interview_questions"]),
            has_invitation=final_result["interview_invitation"] is not None,
            tokens=usage.total_tokens,
        )
        return {
            "final_result": final_result,
            "metadata": {
                "final_synthesis": {
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "tokens": usage.total_tokens,
                }
            },
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("final_synthesis.error", error=str(exc))
        fallback = _make_fallback_result(parsed_jd)
        fallback["interview_invitation"] = None
        return {
            "final_result": fallback,
            "metadata": {
                "final_synthesis": {
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "error": str(exc),
                    "used_fallback": True,
                }
            },
            "errors": [{"node": "final_synthesis", "error": str(exc)}],
        }

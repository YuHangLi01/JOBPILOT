"""final_synthesis 节点：使用 LLM 生成最终结构化分析报告。

职责：
- 将 parsed_jd + classification + merged_skill_data 传递给 LLM
- 验证输出符合 JDRoutingResults 结构（宽松校验：字段缺失时填充空值）
- 写入 state["final_result"]
- LLM 失败时降级为仅包含 jd_summary 的最小结果（基于 parsed_jd）

输入 state 字段：parsed_jd, classification, merged_skill_data
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


async def final_synthesis(state: JDRoutingState) -> dict[str, Any]:
    """调用 LLM 生成最终求职建议报告。

    Args:
        state: 当前图状态。

    Returns:
        state 增量字典：final_result + metadata + errors（仅失败时有值）。
    """
    start = time.monotonic()
    parsed_jd: dict[str, Any] = state.get("parsed_jd") or {}
    classification: dict[str, Any] = state.get("classification") or {}
    merged_skill_data: dict[str, Any] = state.get("merged_skill_data") or {}

    try:
        llm = get_llm_client()
        result, usage = await llm.chat_json(
            system=_p.SYSTEM_PROMPT,
            user=_p.build_user_prompt(parsed_jd, classification, merged_skill_data),
            schema=None,
        )
        final_result = _sanitize_result(result if isinstance(result, dict) else {})
        log.info(
            "final_synthesis.success",
            advice_count=len(final_result["resume_advice"]),
            question_count=len(final_result["interview_questions"]),
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
        return {
            "final_result": _make_fallback_result(parsed_jd),
            "metadata": {
                "final_synthesis": {
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "error": str(exc),
                    "used_fallback": True,
                }
            },
            "errors": [{"node": "final_synthesis", "error": str(exc)}],
        }

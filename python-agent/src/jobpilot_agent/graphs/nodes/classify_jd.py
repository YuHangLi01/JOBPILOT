"""classify_jd 节点：对 JD 做 5 维分类。

职责：
- 调用 LLM，从 parsed_jd 推断 job_type / sub_type / level / locale / channel
- 写入 state["classification"] 和 state["metadata"]["classify_jd"]
- LLM 失败时使用预设默认值，并记录 error，不阻断图执行

输入 state 字段：parsed_jd, jd_text（fallback）
输出 state 字段：classification, metadata (classify_jd key), errors
"""

from __future__ import annotations

import time
from typing import Any

from jobpilot_agent.graphs.prompts import classify_jd as _p
from jobpilot_agent.graphs.state import JDRoutingState
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_CLASSIFICATION_DEFAULTS: dict[str, Any] = {
    "job_type": "tech",
    "sub_type": "software_engineer",
    "level": "middle",
    "locale": "zh",
    "channel": "social",
}

_VALID_JOB_TYPES = {"tech", "product", "design", "ops", "mgmt"}
_VALID_LEVELS = {"junior", "middle", "senior", "lead"}
_VALID_LOCALES = {"zh", "en"}
_VALID_CHANNELS = {"social", "campus"}


def _sanitize(raw: dict[str, Any]) -> dict[str, Any]:
    """将 LLM 输出的 dict 规整为合法的 JDClassification 字段。

    对不合法值回退到默认值，避免后续 Pydantic 校验失败。
    """
    return {
        "job_type": raw.get("job_type") if raw.get("job_type") in _VALID_JOB_TYPES else _CLASSIFICATION_DEFAULTS["job_type"],
        "sub_type": raw.get("sub_type") or _CLASSIFICATION_DEFAULTS["sub_type"],
        "level": raw.get("level") if raw.get("level") in _VALID_LEVELS else _CLASSIFICATION_DEFAULTS["level"],
        "locale": raw.get("locale") if raw.get("locale") in _VALID_LOCALES else _CLASSIFICATION_DEFAULTS["locale"],
        "channel": raw.get("channel") if raw.get("channel") in _VALID_CHANNELS else _CLASSIFICATION_DEFAULTS["channel"],
    }


async def classify_jd(state: JDRoutingState) -> dict[str, Any]:
    """根据 parsed_jd 对 JD 进行 5 维分类。

    优先使用 parsed_jd 结构；若 parsed_jd 为空，直接发送 jd_text。
    LLM 失败时返回默认分类并记录 error，确保后续 Skill 路由不中断。

    Args:
        state: 当前图状态（读取 parsed_jd 和 jd_text）。

    Returns:
        state 增量字典：classification + metadata + errors（仅失败时有值）。
    """
    start = time.monotonic()
    parsed_jd: dict[str, Any] = state.get("parsed_jd") or {}

    try:
        llm = get_llm_client()
        result, usage = await llm.chat_json(
            system=_p.SYSTEM_PROMPT,
            user=_p.build_user_prompt(parsed_jd),
            schema=None,
        )
        classification = _sanitize(result if isinstance(result, dict) else {})
        log.info(
            "classify_jd.success",
            job_type=classification.get("job_type"),
            level=classification.get("level"),
            tokens=usage.total_tokens,
        )
        return {
            "classification": classification,
            "metadata": {
                "classify_jd": {
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "tokens": usage.total_tokens,
                }
            },
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("classify_jd.error", error=str(exc))
        return {
            "classification": _CLASSIFICATION_DEFAULTS.copy(),
            "metadata": {
                "classify_jd": {
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "error": str(exc),
                    "used_defaults": True,
                }
            },
            "errors": [{"node": "classify_jd", "error": str(exc)}],
        }

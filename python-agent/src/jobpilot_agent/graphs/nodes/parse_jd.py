"""parse_jd 节点：将原始 JD 文本解析为结构化字段。

职责：
- 调用 LLM，将 jd_text 解析为 ParsedJD 结构
- 写入 state["parsed_jd"] 和 state["metadata"]["parse_jd"]
- LLM 失败时写入 errors，并用空 dict 继续，不阻断图执行

输入 state 字段：jd_text
输出 state 字段：parsed_jd, metadata (parse_jd key), errors
"""

from __future__ import annotations

import time
from typing import Any

from jobpilot_agent.graphs.prompts import parse_jd as _p
from jobpilot_agent.graphs.state import JDRoutingState
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


async def parse_jd(state: JDRoutingState) -> dict[str, Any]:
    """将 jd_text 解析为结构化 ParsedJD 字典。

    使用 LLMClient.chat_json 调用 LLM（JSON mode）。若 LLM 失败，
    返回空 parsed_jd 并记录 error，确保图不中断。

    Args:
        state: 当前图状态（只读 jd_text）。

    Returns:
        state 增量字典：parsed_jd + metadata + errors（仅失败时有值）。
    """
    start = time.monotonic()
    jd_text: str = state.get("jd_text", "")

    try:
        llm = get_llm_client()
        result, usage = await llm.chat_json(
            system=_p.SYSTEM_PROMPT,
            user=_p.build_user_prompt(jd_text),
            schema=None,
        )
        parsed_jd: dict[str, Any] = result if isinstance(result, dict) else {}
        log.info(
            "parse_jd.success",
            company=parsed_jd.get("company"),
            position=parsed_jd.get("position"),
            tokens=usage.total_tokens,
        )
        return {
            "parsed_jd": parsed_jd,
            "metadata": {
                "parse_jd": {
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "tokens": usage.total_tokens,
                }
            },
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("parse_jd.error", error=str(exc))
        return {
            "parsed_jd": {},
            "metadata": {
                "parse_jd": {
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "error": str(exc),
                }
            },
            "errors": [{"node": "parse_jd", "error": str(exc)}],
        }

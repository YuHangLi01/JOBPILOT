"""merge_outputs 节点：聚合所有 Skill 输出，计算汇总统计。

职责（纯聚合，无 LLM 调用）：
- 将 skill_outputs（list[SkillOutput dict]）转换为 {skill_name: data} 映射
- 仅将 success=True 的 Skill data 合入 merged_skill_data
- 计算 token 总消耗量和总延迟
- 写入 merged_skill_data 和 metadata["merge_outputs"]

输入 state 字段：skill_outputs
输出 state 字段：merged_skill_data, metadata (merge_outputs key)
"""

from __future__ import annotations

import time
from typing import Any

from jobpilot_agent.graphs.state import JDRoutingState
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


async def merge_outputs(state: JDRoutingState) -> dict[str, Any]:
    """将 skill_outputs 列表聚合为按 skill_name 索引的字典。

    设计说明：
    - 仅成功的 Skill 数据写入 merged_skill_data，失败的不传递给 final_synthesis
    - tokens_used 字段使用 int() 安全转换，避免 None 导致加法错误

    Args:
        state: 当前图状态（读取 skill_outputs）。

    Returns:
        state 增量字典：merged_skill_data + metadata。
    """
    start = time.monotonic()
    skill_outputs: list[dict[str, Any]] = state.get("skill_outputs") or []

    merged: dict[str, Any] = {}
    total_tokens = 0
    total_skill_latency = 0

    for output in skill_outputs:
        skill_name = output.get("skill_name", "unknown")
        if output.get("success"):
            merged[skill_name] = output.get("data") or {}
        total_tokens += int(output.get("tokens_used") or 0)
        total_skill_latency += int(output.get("latency_ms") or 0)

    latency = int((time.monotonic() - start) * 1000)
    log.info(
        "merge_outputs.done",
        merged_skills=list(merged.keys()),
        total_tokens=total_tokens,
    )

    return {
        "merged_skill_data": merged,
        "metadata": {
            "merge_outputs": {
                "latency_ms": latency,
                "merged_skill_count": len(merged),
                "total_skill_tokens": total_tokens,
                "total_skill_latency_ms": total_skill_latency,
            }
        },
    }

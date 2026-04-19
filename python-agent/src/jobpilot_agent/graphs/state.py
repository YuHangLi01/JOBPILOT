"""JD 路由图 State 定义。

设计约束（LangGraph 并行写安全）：
- `skill_outputs` 和 `errors` 使用 `Annotated[list, add]` reducer
  → 并行节点写入同一 key 时自动合并，不冲突
- `metadata` 使用 dict_merge reducer
  → 多节点依次写入度量数据，后写不覆盖前写
- 输入字段（request_id/user_id/jd_text/user_context）仅在初始化时赋值，后续只读
- 所有 TypedDict 字段 total=False，允许节点按序增量填充

数据流方向（单写约定）：
  parse_jd        → parsed_jd
  classify_jd     → classification
  dispatch_skills → invoked_skills, skipped_skills
  invoke_skills_parallel → skill_outputs (累积), errors (累积)
  merge_outputs   → merged_skill_data
  final_synthesis → final_result
  所有节点        → metadata (合并), errors (累积)
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict


def _dict_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """metadata reducer：将两个字典浅合并（右值覆盖同名 key）。"""
    return {**left, **right}


class ParsedJD(TypedDict, total=False):
    """parse_jd 节点的结构化输出。

    字段与 JDContext.parsed_jd 保持一致，方便后续 Skill 直接读取。

    Attributes:
        company: 公司名称。
        position: 岗位名称。
        location: 工作地点。
        publish_date: 发布日期（字符串格式）。
        responsibilities: 主要职责列表。
        requirements: 任职要求列表。
        perks: 福利待遇列表。
    """

    company: str
    position: str
    location: str
    publish_date: str
    responsibilities: list[str]
    requirements: list[str]
    perks: list[str]


class JDRoutingState(TypedDict, total=False):
    """JD 路由图的完整状态。

    字段按生命周期排列：输入字段在图启动前填充，其余字段由各节点依序填充。

    Attributes:
        request_id: 请求唯一 ID（只读输入）。
        user_id: 用户 ID（只读输入）。
        jd_text: 原始 JD 文本（只读输入）。
        user_context: 用户偏好（只读输入，dict 格式以兼容 TypedDict）。

        parsed_jd: parse_jd 节点填充的结构化 JD 字段。
        classification: classify_jd 节点填充的分类结果（dict 格式）。

        invoked_skills: dispatch_skills 决策的需调用 Skill 名称列表。
        skipped_skills: dispatch_skills 决策的需跳过 Skill 名称列表。

        skill_outputs: invoke_skills_parallel 填充的 SkillOutput 列表。
            使用 add reducer 支持并行节点安全写入。
        merged_skill_data: merge_outputs 聚合后的 {skill_name: data} 字典。
        final_result: final_synthesis 输出的最终结构化结果。

        metadata: 贯穿所有节点的度量数据（tokens / latency / llm_calls 等）。
            使用 dict_merge reducer，后写不覆盖前写（key 按节点名区分）。
        errors: 图执行过程中的错误记录（{skill/node, error} 列表）。
            使用 add reducer 支持累积。
    """

    # ── 输入（初始化时提供，各节点只读）─────────────────────────────────────
    request_id: str
    user_id: str
    jd_text: str
    user_context: dict[str, Any]

    # ── parse_jd 填充 ─────────────────────────────────────────────────────
    parsed_jd: dict[str, Any]

    # ── classify_jd 填充 ──────────────────────────────────────────────────
    classification: dict[str, Any]

    # ── dispatch_skills 填充 ─────────────────────────────────────────────
    invoked_skills: list[str]
    skipped_skills: list[str]

    # ── invoke_skills_parallel 填充（reducer 允许并行写入）────────────────
    skill_outputs: Annotated[list[dict[str, Any]], add]

    # ── merge_outputs 填充 ────────────────────────────────────────────────
    merged_skill_data: dict[str, Any]

    # ── final_synthesis 填充 ──────────────────────────────────────────────
    final_result: dict[str, Any]

    # ── 贯穿所有节点 ──────────────────────────────────────────────────────
    metadata: Annotated[dict[str, Any], _dict_merge]
    errors: Annotated[list[dict[str, Any]], add]

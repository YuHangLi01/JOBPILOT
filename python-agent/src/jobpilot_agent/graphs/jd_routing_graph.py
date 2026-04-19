"""JD 路由 LangGraph StateGraph。

图拓扑：
    START → parse_jd → classify_jd → dispatch_skills
        → [invoke_skills_parallel | merge_outputs (skip)]
        → merge_outputs → final_synthesis → END

关键设计：
- _should_invoke_any_skill：条件边，根据 invoked_skills 决定跳转目标
- get_jd_routing_graph()：进程级懒加载单例，避免重复编译
- 所有节点均为 async 函数，图通过 ainvoke() 调用
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from jobpilot_agent.graphs.nodes.classify_jd import classify_jd
from jobpilot_agent.graphs.nodes.dispatch_skills import dispatch_skills
from jobpilot_agent.graphs.nodes.final_synthesis import final_synthesis
from jobpilot_agent.graphs.nodes.invoke_skills_parallel import invoke_skills_parallel
from jobpilot_agent.graphs.nodes.merge_outputs import merge_outputs
from jobpilot_agent.graphs.nodes.parse_jd import parse_jd
from jobpilot_agent.graphs.state import JDRoutingState
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


# ── 条件边判断函数 ─────────────────────────────────────────────────────────


def _should_invoke_any_skill(state: JDRoutingState) -> str:
    """判断是否有 Skill 需要执行。

    Returns:
        "invoke"：有 Skill 需要并行执行。
        "skip"：无 Skill 被选中，直接进入 merge_outputs。
    """
    invoked = state.get("invoked_skills") or []
    return "invoke" if invoked else "skip"


# ── 图构建函数 ─────────────────────────────────────────────────────────────


def build_jd_routing_graph() -> Any:
    """构建并编译 JD 路由 StateGraph。

    图节点：
    - parse_jd：JD 文本 → 结构化字段
    - classify_jd：结构化字段 → 5 维分类
    - dispatch_skills：分类 → Skill 路由决策
    - invoke_skills_parallel：并行执行选中 Skill
    - merge_outputs：聚合 Skill 输出
    - final_synthesis：生成最终报告

    Returns:
        LangGraph CompiledGraph 实例。
    """
    builder: StateGraph = StateGraph(JDRoutingState)

    # ── 添加节点 ──────────────────────────────────────────────────────
    builder.add_node("parse_jd", parse_jd)
    builder.add_node("classify_jd", classify_jd)
    builder.add_node("dispatch_skills", dispatch_skills)
    builder.add_node("invoke_skills_parallel", invoke_skills_parallel)
    builder.add_node("merge_outputs", merge_outputs)
    builder.add_node("final_synthesis", final_synthesis)

    # ── 添加边 ────────────────────────────────────────────────────────
    builder.add_edge(START, "parse_jd")
    builder.add_edge("parse_jd", "classify_jd")
    builder.add_edge("classify_jd", "dispatch_skills")

    # 条件边：有 Skill 被选中 → invoke；无 Skill → 直接 merge
    builder.add_conditional_edges(
        "dispatch_skills",
        _should_invoke_any_skill,
        {
            "invoke": "invoke_skills_parallel",
            "skip": "merge_outputs",
        },
    )

    builder.add_edge("invoke_skills_parallel", "merge_outputs")
    builder.add_edge("merge_outputs", "final_synthesis")
    builder.add_edge("final_synthesis", END)

    compiled = builder.compile()
    log.info("jd_routing_graph.compiled")
    return compiled


# ── 进程级单例 ──────────────────────────────────────────────────────────────

_compiled_graph: Any = None


def get_jd_routing_graph() -> Any:
    """返回 JD 路由图的进程级单例（懒加载）。

    首次调用时编译图（约 < 50ms），后续直接返回缓存实例。

    Returns:
        LangGraph CompiledGraph 实例。
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_jd_routing_graph()
    return _compiled_graph

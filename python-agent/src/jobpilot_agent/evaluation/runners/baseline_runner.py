"""Baseline 运行器：强制触发所有注册 Skill，不做路由决策。

Baseline 定义：
- 与主图结构完全一致（parse_jd → classify_jd → invoke_skills_parallel → ...）
- 唯一区别：dispatch_skills 节点改为「全选」——所有注册 Skill 均被 invoke
- 目的：量化「有路由 vs 无路由」的效果与 Token 成本差异

设计约束：
- 不修改任何 Skill 代码或主图代码
- 通过替换单个节点函数来构建 baseline 图
- 与 ScenarioARunner 复用相同接口
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from jobpilot_agent.graphs.nodes.classify_jd import classify_jd
from jobpilot_agent.graphs.nodes.final_synthesis import final_synthesis
from jobpilot_agent.graphs.nodes.invoke_skills_parallel import invoke_skills_parallel
from jobpilot_agent.graphs.nodes.merge_outputs import merge_outputs
from jobpilot_agent.graphs.nodes.parse_jd import parse_jd
from jobpilot_agent.graphs.state import JDRoutingState
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.skills.registry import register_all_skills, registry

log = get_logger(__name__)


async def dispatch_all_skills(state: JDRoutingState) -> dict[str, Any]:
    """Baseline dispatch 节点：强制选中所有已注册 Skill。

    不做任何路由决策——直接将 registry 中全部 Skill 加入 invoked_skills。
    skipped_skills 为空。
    """
    import time

    start = time.monotonic()
    register_all_skills()

    all_skill_names = [s.name for s in registry.all()]  # type: ignore[union-attr]
    log.info("dispatch_all_skills.baseline", count=len(all_skill_names))

    return {
        "invoked_skills": all_skill_names,
        "skipped_skills": [],
        "metadata": {
            "dispatch_skills": {
                "latency_ms": int((time.monotonic() - start) * 1000),
                "invoked_count": len(all_skill_names),
                "skipped_count": 0,
                "mode": "baseline_all",
            }
        },
    }


def build_baseline_graph() -> Any:
    """构建 Baseline LangGraph：与主图相同，但 dispatch 节点全选所有 Skill。

    Returns:
        LangGraph CompiledGraph 实例。
    """
    builder: StateGraph = StateGraph(JDRoutingState)

    builder.add_node("parse_jd", parse_jd)
    builder.add_node("classify_jd", classify_jd)
    builder.add_node("dispatch_skills", dispatch_all_skills)  # ← 唯一不同
    builder.add_node("invoke_skills_parallel", invoke_skills_parallel)
    builder.add_node("merge_outputs", merge_outputs)
    builder.add_node("final_synthesis", final_synthesis)

    builder.add_edge(START, "parse_jd")
    builder.add_edge("parse_jd", "classify_jd")
    builder.add_edge("classify_jd", "dispatch_skills")
    builder.add_edge("dispatch_skills", "invoke_skills_parallel")  # baseline 无条件 invoke
    builder.add_edge("invoke_skills_parallel", "merge_outputs")
    builder.add_edge("merge_outputs", "final_synthesis")
    builder.add_edge("final_synthesis", END)

    compiled = builder.compile()
    log.info("baseline_graph.compiled")
    return compiled


_baseline_graph: Any = None


def get_baseline_graph() -> Any:
    """进程级 baseline 图单例（懒加载）。"""
    global _baseline_graph
    if _baseline_graph is None:
        _baseline_graph = build_baseline_graph()
    return _baseline_graph

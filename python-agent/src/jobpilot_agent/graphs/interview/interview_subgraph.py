"""面试子图组装——StateGraph + Checkpointer 编译。"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from jobpilot_agent.graphs.interview.checkpointer import get_active_checkpointer
from jobpilot_agent.graphs.interview.nodes import (
    closing_node,
    evaluate_performance_node,
    init_session_node,
    intro_node,
    judge_continue_deep_dive,
    judge_continue_scenario,
    judge_continue_tech_qa,
    project_deep_dive_node,
    reverse_node,
    scenario_node,
    tech_qa_node,
)
from jobpilot_agent.graphs.interview.state import InterviewState


def build_interview_subgraph() -> StateGraph[InterviewState]:
    """构建面试 StateGraph（未编译）。"""
    g = StateGraph(InterviewState)

    # 节点注册
    g.add_node("init_session", init_session_node)
    g.add_node("intro", intro_node)
    g.add_node("project_deep_dive", project_deep_dive_node)
    g.add_node("tech_qa", tech_qa_node)
    g.add_node("scenario", scenario_node)
    g.add_node("reverse", reverse_node)
    g.add_node("closing", closing_node)
    g.add_node("evaluate_performance", evaluate_performance_node)

    # 线性边
    g.add_edge(START, "init_session")
    g.add_edge("init_session", "intro")
    g.add_edge("intro", "project_deep_dive")

    # 循环 1：项目深挖
    g.add_conditional_edges(
        "project_deep_dive",
        judge_continue_deep_dive,
        {
            "continue": "project_deep_dive",
            "move_to_tech_qa": "tech_qa",
        },
    )

    # 循环 2：技术问答
    g.add_conditional_edges(
        "tech_qa",
        judge_continue_tech_qa,
        {
            "continue": "tech_qa",
            "move_to_scenario": "scenario",
        },
    )

    # 循环 3：情境题
    g.add_conditional_edges(
        "scenario",
        judge_continue_scenario,
        {
            "continue": "scenario",
            "move_to_reverse": "reverse",
        },
    )

    g.add_edge("reverse", "closing")
    g.add_edge("closing", "evaluate_performance")
    g.add_edge("evaluate_performance", END)

    return g


def compile_interview_subgraph() -> Any:
    """编译子图，绑定 Checkpointer。FastAPI lifespan 启动后调用一次。"""
    g = build_interview_subgraph()
    checkpointer = get_active_checkpointer()
    return g.compile(checkpointer=checkpointer)


# 进程级单例（延迟初始化）
_compiled_subgraph: Any = None


def get_interview_subgraph() -> Any:
    """返回已编译的子图单例（依赖 init_checkpointer 已被调用）。"""
    global _compiled_subgraph
    if _compiled_subgraph is None:
        _compiled_subgraph = compile_interview_subgraph()
    return _compiled_subgraph

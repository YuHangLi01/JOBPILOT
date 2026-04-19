"""面试子图包——暴露 Interrupt 助手与 Command 类型。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.types import Command, interrupt

if TYPE_CHECKING:
    from jobpilot_agent.graphs.interview.interviewer_core import InterviewerQuestion


def ask_user_interrupt(question: InterviewerQuestion) -> str:
    """面试节点调用此函数请求用户输入。

    内部用 LangGraph interrupt() 暂停图执行，返回值为
    `graph.ainvoke(Command(resume=user_text), config)` 传入的用户文字。
    """
    user_input: str = interrupt(
        {
            "type": "ask_question",
            "content": question.content,
            "intent": question.intent,
            "answer_points": question.answer_points,
        }
    )
    return user_input


__all__ = ["ask_user_interrupt", "Command", "interrupt"]

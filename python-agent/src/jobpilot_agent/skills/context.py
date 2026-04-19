"""JDContext — Skill 调用的统一上下文对象。

所有 Skill 只读该对象，不得修改。上下文由 LangGraph 各节点按序填充：
  - classify_jd 节点填充 classification
  - parse_jd 节点填充 parsed_jd
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from jobpilot_agent.api.schemas import JDClassification, UserContext


class JDContext(BaseModel):
    """Skill 调用的统一上下文。

    生命周期：随一次 JD 路由请求创建，由 LangGraph 编排器在各节点之间传递。
    Skill 的 should_invoke / invoke 方法均接收该对象，只读访问。

    Attributes:
        request_id: 来自 HTTP 请求的全局唯一 ID。
        user_id: 发起请求的用户 ID。
        jd_text: 原始 JD 文本。
        user_context: 用户偏好（语言、简历 KB 等）。
        classification: 由 classify_jd 节点填充的分类结果；
            在 classify_jd 运行前为 None，Skill 的 should_invoke 需处理此情况。
        parsed_jd: 由 parse_jd 节点填充的结构化 JD 字段。
            推荐字段：company, position, location, publish_date,
                      responsibilities, requirements, perks。
        timeout_seconds: 单个 Skill 执行超时阈值（秒）。
        llm_model: 本次请求优先使用的 LLM 模型名；None 时使用 settings 默认值。
        trace_id: 分布式链路追踪 ID，用于日志关联。

    Example:
        >>> ctx = JDContext(
        ...     request_id="req-001",
        ...     user_id="user-001",
        ...     jd_text="Python 后端工程师，5 年经验...",
        ...     user_context=UserContext(),
        ... )
        >>> assert ctx.classification is None  # 尚未分类
    """

    # ── 来自请求 ──────────────────────────────────────────────
    request_id: str
    user_id: str
    jd_text: str

    # ── 用户偏好 ──────────────────────────────────────────────
    user_context: UserContext = Field(default_factory=UserContext)

    # ── 由节点填充（初始为空）────────────────────────────────
    classification: Optional[JDClassification] = None
    parsed_jd: dict[str, Any] = Field(default_factory=dict)

    # ── 运行时配置 ────────────────────────────────────────────
    timeout_seconds: int = 15
    llm_model: Optional[str] = None

    # ── 调试 ─────────────────────────────────────────────────
    trace_id: Optional[str] = None

    model_config = {"frozen": False}  # 允许节点按顺序填充

    # ── 便捷属性（减少 Skill 里的判空样板代码）──────────────
    @property
    def job_type(self) -> str | None:
        """快捷访问 classification.job_type，无分类时返回 None。"""
        return self.classification.job_type if self.classification else None

    @property
    def level(self) -> str | None:
        """快捷访问 classification.level，无分类时返回 None。"""
        return self.classification.level if self.classification else None

    @property
    def locale(self) -> str | None:
        """快捷访问 classification.locale，无分类时返回 None。"""
        return self.classification.locale if self.classification else None

    @property
    def channel(self) -> str | None:
        """快捷访问 classification.channel，无分类时返回 None。"""
        return self.classification.channel if self.classification else None

"""Skill 层公开 API。

下游模块（graphs、routers）只需从这里导入，无需关心内部模块结构：

    from jobpilot_agent.skills import (
        Skill, SkillOutput, SkillMetadata, SkillExample,
        JDContext,
        registry, SkillDispatcher,
    )
"""

from jobpilot_agent.skills.base import Skill, SkillExample, SkillMetadata, SkillOutput
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.dispatcher import SkillDispatcher
from jobpilot_agent.skills.errors import (
    SkillError,
    SkillExternalError,
    SkillInputError,
    SkillLLMError,
    SkillTimeoutError,
)
from jobpilot_agent.skills.registry import SkillRegistry, register_all_skills, registry

__all__ = [
    # 核心基类
    "Skill",
    "SkillOutput",
    "SkillMetadata",
    "SkillExample",
    # 上下文
    "JDContext",
    # 注册与调度
    "registry",
    "SkillRegistry",
    "register_all_skills",
    "SkillDispatcher",
    # 异常
    "SkillError",
    "SkillTimeoutError",
    "SkillInputError",
    "SkillExternalError",
    "SkillLLMError",
]

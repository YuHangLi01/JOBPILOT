"""SkillDispatcher — 基于规则的 Skill 路由决策器。

职责：
- 遍历 SkillRegistry 中所有已注册的 Skill
- 调用每个 Skill 的 should_invoke(ctx) 判断是否触发
- 对选中的 Skill 按依赖关系做拓扑排序
- 返回 (invoked, skipped) 两个列表

设计原则：
- Dispatcher 本身不包含任何业务路由规则——规则全部封装在各 Skill 的 should_invoke 里
- should_invoke 抛异常时保守处理：跳过该 Skill，避免一个 Skill 的 bug 阻断整个流程
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.registry import registry

if TYPE_CHECKING:
    from jobpilot_agent.skills.base import Skill

logger = logging.getLogger(__name__)


class SkillDispatcher:
    """基于规则的 Skill 调度器。

    策略：
    1. 遍历所有已注册 Skill
    2. 逐个调用 should_invoke(ctx)（同步、轻量）
    3. 收集 invoked 列表后，做依赖拓扑排序
    4. 返回 (invoked_sorted, skipped)

    未来扩展点：
    - use_llm_fallback=True 时，在规则无法决策时启用 LLM 二次判断
    - 支持优先级权重（高优先 Skill 先执行）

    Example:
        >>> dispatcher = SkillDispatcher()
        >>> invoked, skipped = dispatcher.dispatch(ctx)
        >>> for skill in invoked:
        ...     output = await skill.invoke(ctx)
    """

    def __init__(self, use_llm_fallback: bool = False) -> None:
        """初始化调度器。

        Args:
            use_llm_fallback: 预留参数，当前版本未实现 LLM 二次决策。
        """
        self.use_llm_fallback = use_llm_fallback

    def dispatch(
        self, ctx: JDContext
    ) -> tuple[list["Skill"], list["Skill"]]:
        """对当前 JDContext 做路由决策。

        遍历所有注册 Skill，调用 should_invoke 分类后：
        - 对 invoked 列表做依赖拓扑排序（保证被依赖的 Skill 先执行）
        - should_invoke 抛异常时将该 Skill 归入 skipped，并记录 error 日志

        Args:
            ctx: 当前请求的 JD 上下文。

        Returns:
            Tuple of (invoked_sorted, skipped):
            - invoked_sorted: 按依赖顺序排列的 Skill 列表
            - skipped: 被跳过的 Skill 列表（包括 should_invoke=False 和异常情况）
        """
        invoked: list["Skill"] = []
        skipped: list["Skill"] = []

        for skill in registry.all():
            try:
                if skill.should_invoke(ctx):  # type: ignore[union-attr]
                    invoked.append(skill)  # type: ignore[arg-type]
                    logger.debug("Skill %s: will invoke", skill.name)  # type: ignore[union-attr]
                else:
                    skipped.append(skill)  # type: ignore[arg-type]
                    logger.debug("Skill %s: skipped (should_invoke=False)", skill.name)  # type: ignore[union-attr]
            except Exception as exc:
                logger.error(
                    "Skill %s: should_invoke raised exception, skipping — %s",
                    getattr(skill, "name", repr(skill)),
                    exc,
                    exc_info=True,
                )
                skipped.append(skill)  # type: ignore[arg-type]

        # 依赖拓扑排序
        invoked_names = [s.name for s in invoked]  # type: ignore[union-attr]
        try:
            sorted_names = registry.resolve_dependencies(invoked_names)
        except ValueError as exc:
            logger.error("依赖解析失败，使用原始顺序：%s", exc)
            sorted_names = invoked_names

        name_to_skill: dict[str, "Skill"] = {
            s.name: s for s in invoked  # type: ignore[union-attr]
        }
        invoked_sorted = [name_to_skill[n] for n in sorted_names if n in name_to_skill]

        logger.info(
            "SkillDispatcher: invoked=%s, skipped=%s",
            [s.name for s in invoked_sorted],  # type: ignore[union-attr]
            [s.name for s in skipped],  # type: ignore[union-attr]
        )
        return invoked_sorted, skipped

    async def dispatch_and_run(
        self, ctx: JDContext
    ) -> tuple[list[object], list["Skill"]]:
        """路由 + 串行执行所有选中 Skill，返回输出列表。

        这是最常用的顶层入口：一次调用完成"决策 + 执行"。
        Skill 按拓扑顺序串行执行（依赖项先完成）。

        Args:
            ctx: 当前请求的 JD 上下文。

        Returns:
            Tuple of (outputs, skipped):
            - outputs: 每个 invoked Skill 的 SkillOutput 列表（顺序与执行顺序一致）
            - skipped: 被跳过的 Skill 列表
        """
        invoked_sorted, skipped = self.dispatch(ctx)
        outputs = []
        for skill in invoked_sorted:
            output = await skill.invoke(ctx)  # type: ignore[union-attr]
            outputs.append(output)
            if not output.success:  # type: ignore[union-attr]
                logger.warning(
                    "Skill %s failed: %s",
                    skill.name,  # type: ignore[union-attr]
                    output.error,  # type: ignore[union-attr]
                )
        return outputs, skipped

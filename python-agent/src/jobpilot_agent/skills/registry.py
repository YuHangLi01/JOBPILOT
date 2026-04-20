"""Skill 全局注册表与批量注册入口。

设计说明：
- SkillRegistry 是进程级单例（__new__ 保证）
- 使用 Kahn 算法（BFS）做依赖拓扑排序，循环依赖时立即报错
- register_all_skills() 在 FastAPI lifespan 启动时调用，按模块 import 触发自注册
- 测试中用 registry.reset() 清除状态，避免用例间污染
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class SkillRegistry:
    """全局 Skill 注册表，单例模式。

    Example:
        >>> from jobpilot_agent.skills.registry import registry
        >>> registry.register(my_skill)
        >>> skill = registry.get("my_skill_name")
    """

    _instance: Optional["SkillRegistry"] = None
    _skills: dict[str, object]  # Skill（避免循环导入，用 object 类型注解）

    def __new__(cls) -> "SkillRegistry":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._skills = {}
            cls._instance = inst
        return cls._instance

    def register(self, skill: object) -> None:
        """注册 Skill 实例。相同 name 时覆盖并警告。

        Args:
            skill: 实现了 .metadata.name 和 .metadata.version 的 Skill 实例。
        """
        name: str = skill.metadata.name  # type: ignore[attr-defined]
        version: str = skill.metadata.version  # type: ignore[attr-defined]
        if name in self._skills:
            logger.warning("Skill %s already registered, overwriting", name)
        self._skills[name] = skill
        logger.info("Registered skill: %s v%s", name, version)

    def get(self, name: str) -> Optional[object]:
        """按名称获取 Skill 实例，不存在时返回 None。"""
        return self._skills.get(name)

    def all(self) -> list[object]:
        """返回所有已注册 Skill 的列表。"""
        return list(self._skills.values())

    def names(self) -> list[str]:
        """返回所有已注册 Skill 的名称列表。"""
        return list(self._skills.keys())

    def resolve_dependencies(self, skill_names: Iterable[str]) -> list[str]:
        """对给定的 Skill 名称集合按依赖关系做拓扑排序（Kahn 算法 BFS）。

        只考虑 skill_names 集合内部的依赖关系，外部依赖忽略。

        算法步骤：
        1. 构建 in_degree 字典（仅包含 skill_names 内部的边）
        2. 将所有入度为 0 的节点加入队列
        3. BFS 消费队列，每消费一个节点就将其后继节点的入度 -1
        4. 若最终结果数 < 输入数，则存在循环依赖，raise ValueError

        Args:
            skill_names: 需要排序的 Skill 名称集合。

        Returns:
            按依赖顺序排列的名称列表（被依赖的在前）。

        Raises:
            ValueError: 检测到循环依赖时。

        Example:
            >>> registry.resolve_dependencies(["C", "A", "B"])
            # A→B→C 时返回 ["A", "B", "C"]
        """
        names_set = set(skill_names)
        if not names_set:
            return []

        # 构建邻接表：dependency → [dependents]（反向图，用于减少入度）
        in_degree: dict[str, int] = {n: 0 for n in names_set}
        reverse_adj: dict[str, list[str]] = {n: [] for n in names_set}

        for name in names_set:
            skill = self._skills.get(name)
            if skill is None:
                continue
            deps: list[str] = skill.metadata.dependencies  # type: ignore[attr-defined]
            for dep in deps:
                if dep not in names_set:
                    continue  # 外部依赖忽略
                in_degree[name] += 1
                reverse_adj[dep].append(name)

        # Kahn BFS
        queue: deque[str] = deque(n for n in names_set if in_degree[n] == 0)
        sorted_result: list[str] = []

        while queue:
            node = queue.popleft()
            sorted_result.append(node)
            for dependent in reverse_adj[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(sorted_result) != len(names_set):
            remaining = names_set - set(sorted_result)
            raise ValueError(
                f"Skill 依赖中存在循环：{remaining}。"
                "请检查各 Skill 的 metadata.dependencies 字段。"
            )

        return sorted_result

    def reset(self) -> None:
        """清空注册表，主要供测试使用。"""
        self._skills.clear()
        logger.debug("SkillRegistry reset")


# ── 进程级全局单例 ──────────────────────────────────────────────────────────
registry = SkillRegistry()


def register_all_skills() -> None:
    """在 FastAPI 启动时调用，import 所有 Skill 模块触发自注册。

    显式 import 比自动扫描更可控：新增 Skill 时只需在此加一行 import。
    P3.1b/c 具体 Skill 写好后逐一取消注释。
    """
    # P3.1a：模板 Skill
    from jobpilot_agent.skills.skill_template import index as _template  # noqa: F401

    # P3.1b
    from jobpilot_agent.skills.tech_stack_extract import index as _tech  # noqa: F401
    from jobpilot_agent.skills.gpa_check import index as _gpa            # noqa: F401
    from jobpilot_agent.skills.en_translate import index as _trans       # noqa: F401

    # P3.1c
    from jobpilot_agent.skills.interview_rag import index as _rag        # noqa: F401
    from jobpilot_agent.skills.portfolio_check import index as _port     # noqa: F401
    from jobpilot_agent.skills.github_scan import index as _gh           # noqa: F401

    logger.info("All skills registered: %s", registry.names())

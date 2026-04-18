"""Skill 注册表（stub）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jobpilot_agent.skills.base import BaseSkill

_registry: dict[str, BaseSkill] = {}


def register(skill: BaseSkill) -> None:
    """注册一个 Skill 实例到全局注册表。"""
    _registry[skill.name] = skill


def get(name: str) -> BaseSkill:
    """按名称获取 Skill；不存在时抛 KeyError。"""
    return _registry[name]


def list_skills() -> list[str]:
    """返回所有已注册 Skill 的名称列表。"""
    return list(_registry.keys())

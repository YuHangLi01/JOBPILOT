"""Skill 基类定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseSkill(ABC):
    """所有 Skill 的抽象基类。"""

    name: str
    description: str

    @abstractmethod
    async def run(self, **kwargs: Any) -> Any:
        """执行 Skill，返回结果。子类必须实现。"""
        ...

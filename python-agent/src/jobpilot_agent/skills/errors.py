"""Skill 层专属异常定义。

所有 Skill 层的错误都继承 SkillError，携带结构化 error_code 和 retryable 标志，
方便调用方做统一的错误处理与重试策略。
"""

from __future__ import annotations


class SkillError(Exception):
    """Skill 执行基类异常。

    Args:
        message: 人类可读的错误描述。
        detail: 附加调试信息（如原始异常 repr）。
    """

    error_code: str = "SKILL_ERROR"
    retryable: bool = False

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"retryable={self.retryable})"
        )


class SkillTimeoutError(SkillError):
    """Skill 执行超时（超过 ctx.timeout_seconds）。可重试。"""

    error_code = "SKILL_TIMEOUT"
    retryable = True


class SkillInputError(SkillError):
    """输入不满足 Skill 要求（参数缺失、格式错误等）。不可重试。"""

    error_code = "SKILL_INPUT_INVALID"
    retryable = False


class SkillExternalError(SkillError):
    """外部依赖失败（API 调用失败、RAG 库不可用等）。可重试。"""

    error_code = "SKILL_EXTERNAL_FAIL"
    retryable = True


class SkillLLMError(SkillError):
    """LLM 调用失败（限流、超时、响应解析错误等）。可重试。"""

    error_code = "SKILL_LLM_FAIL"
    retryable = True

"""单元测试：Skill 基础设施（Registry / Dispatcher / Base / LangChain Tool）。

测试策略：
- 不依赖任何外部服务（LLM / Milvus / API）
- 每个测试通过 autouse fixture 在测试前后重置 SkillRegistry 单例
- 使用内联 mock Skill，避免依赖 template_skill 的自注册副作用
"""

from __future__ import annotations

import pytest

from jobpilot_agent.api.schemas import JDClassification, UserContext
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
from jobpilot_agent.skills.registry import SkillRegistry, registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_registry() -> None:
    """每个测试前后清空 SkillRegistry，防止用例间污染。"""
    registry.reset()
    yield  # type: ignore[misc]
    registry.reset()


def make_ctx(
    job_type: str = "tech",
    level: str = "middle",
    locale: str = "zh",
    channel: str = "social",
    jd_text: str = "Python 后端工程师",
) -> JDContext:
    """构造标准测试用 JDContext。"""
    return JDContext(
        request_id="test-req",
        user_id="test-user",
        jd_text=jd_text,
        user_context=UserContext(),
        classification=JDClassification(
            job_type=job_type,  # type: ignore[arg-type]
            sub_type="backend",
            level=level,  # type: ignore[arg-type]
            locale=locale,  # type: ignore[arg-type]
            channel=channel,  # type: ignore[arg-type]
        ),
    )


def make_skill(name: str, invoke_result: bool = True, should: bool = True) -> Skill:
    """工厂：创建一个简单的 mock Skill（不自动注册）。"""

    class _MockSkill(Skill):
        metadata = SkillMetadata(
            name=name,
            description=f"Mock Skill {name}",
            when_to_use="always",
            when_not_to_use="never",
        )

        def should_invoke(self, ctx: JDContext) -> bool:
            return should

        async def invoke(self, ctx: JDContext) -> SkillOutput:
            return SkillOutput(
                skill_name=self.metadata.name,
                success=invoke_result,
                data={"result": f"{name}_output"},
            )

    return _MockSkill()


def make_skill_with_deps(name: str, deps: list[str], should: bool = True) -> Skill:
    """工厂：创建带依赖关系的 mock Skill。"""

    class _DepSkill(Skill):
        metadata = SkillMetadata(
            name=name,
            description=f"Dep Skill {name}",
            when_to_use="with deps",
            when_not_to_use="circular",
            dependencies=deps,
        )

        def should_invoke(self, ctx: JDContext) -> bool:
            return should

        async def invoke(self, ctx: JDContext) -> SkillOutput:
            return SkillOutput(skill_name=name, success=True)

    return _DepSkill()


# ---------------------------------------------------------------------------
# 1. SkillRegistry 单例
# ---------------------------------------------------------------------------


def test_skill_registry_singleton() -> None:
    """多次 SkillRegistry() 应返回同一对象。"""
    r1 = SkillRegistry()
    r2 = SkillRegistry()
    assert r1 is r2
    assert registry is r1


# ---------------------------------------------------------------------------
# 2. register + get
# ---------------------------------------------------------------------------


def test_register_and_get() -> None:
    """注册后能正确取回 Skill 实例。"""
    skill = make_skill("alpha")
    registry.register(skill)

    assert registry.get("alpha") is skill
    assert "alpha" in registry.names()
    assert len(registry.all()) == 1


def test_register_overwrite_warns(caplog: pytest.LogCaptureFixture) -> None:
    """重复注册同名 Skill 时应覆盖并输出 warning。"""
    import logging

    skill1 = make_skill("dup")
    skill2 = make_skill("dup")

    with caplog.at_level(logging.WARNING, logger="jobpilot_agent.skills.registry"):
        registry.register(skill1)
        registry.register(skill2)

    assert registry.get("dup") is skill2
    assert any("already registered" in r.message for r in caplog.records)


def test_get_nonexistent_returns_none() -> None:
    """查询不存在的 Skill 返回 None，不抛异常。"""
    assert registry.get("nonexistent") is None


# ---------------------------------------------------------------------------
# 3. resolve_dependencies — 拓扑排序
# ---------------------------------------------------------------------------


def test_resolve_dependencies_linear() -> None:
    """A→B→C 的线性依赖应按顺序返回 [A, B, C]。"""
    skill_a = make_skill_with_deps("A", deps=[])
    skill_b = make_skill_with_deps("B", deps=["A"])
    skill_c = make_skill_with_deps("C", deps=["B"])

    for s in [skill_a, skill_b, skill_c]:
        registry.register(s)

    result = registry.resolve_dependencies(["C", "B", "A"])
    assert result.index("A") < result.index("B")
    assert result.index("B") < result.index("C")


def test_resolve_dependencies_parallel() -> None:
    """A、B、C 无相互依赖时，三者都应出现在结果中（顺序不限）。"""
    for name in ["X", "Y", "Z"]:
        registry.register(make_skill_with_deps(name, deps=[]))

    result = registry.resolve_dependencies(["X", "Y", "Z"])
    assert set(result) == {"X", "Y", "Z"}
    assert len(result) == 3


def test_resolve_dependencies_cycle_raises() -> None:
    """循环依赖（A→B→A）应抛出 ValueError。"""
    skill_a = make_skill_with_deps("CycA", deps=["CycB"])
    skill_b = make_skill_with_deps("CycB", deps=["CycA"])

    registry.register(skill_a)
    registry.register(skill_b)

    with pytest.raises(ValueError, match="循环"):
        registry.resolve_dependencies(["CycA", "CycB"])


def test_resolve_dependencies_empty() -> None:
    """空输入应返回空列表。"""
    assert registry.resolve_dependencies([]) == []


# ---------------------------------------------------------------------------
# 4. SkillDispatcher
# ---------------------------------------------------------------------------


def test_dispatcher_filters_correctly() -> None:
    """should_invoke=True 的进 invoked，False 的进 skipped。"""
    yes_skill = make_skill("yes_skill", should=True)
    no_skill = make_skill("no_skill", should=False)

    registry.register(yes_skill)
    registry.register(no_skill)

    dispatcher = SkillDispatcher()
    ctx = make_ctx()
    invoked, skipped = dispatcher.dispatch(ctx)

    assert any(s.name == "yes_skill" for s in invoked)
    assert any(s.name == "no_skill" for s in skipped)
    assert len(invoked) == 1
    assert len(skipped) == 1


def test_dispatcher_handles_should_invoke_exception() -> None:
    """should_invoke 抛异常时，该 Skill 应归入 skipped，不阻断流程。"""

    class _BrokenSkill(Skill):
        metadata = SkillMetadata(
            name="broken_skill",
            description="always throws",
            when_to_use="",
            when_not_to_use="",
        )

        def should_invoke(self, ctx: JDContext) -> bool:
            raise RuntimeError("should_invoke 炸了")

        async def invoke(self, ctx: JDContext) -> SkillOutput:
            return SkillOutput(skill_name="broken_skill", success=True)

    registry.register(_BrokenSkill())

    dispatcher = SkillDispatcher()
    invoked, skipped = dispatcher.dispatch(make_ctx())

    assert len(invoked) == 0
    assert len(skipped) == 1
    assert skipped[0].name == "broken_skill"


def test_dispatcher_respects_dependency_order() -> None:
    """Dispatcher 返回的 invoked 列表应按依赖拓扑顺序排列。"""
    a = make_skill_with_deps("dep_a", deps=[])
    b = make_skill_with_deps("dep_b", deps=["dep_a"])

    registry.register(b)
    registry.register(a)

    dispatcher = SkillDispatcher()
    invoked, _ = dispatcher.dispatch(make_ctx())

    names = [s.name for s in invoked]
    assert names.index("dep_a") < names.index("dep_b")


# ---------------------------------------------------------------------------
# 5. LangChain Tool 适配
# ---------------------------------------------------------------------------


def test_to_langchain_tool_returns_structured_tool() -> None:
    """to_langchain_tool 应返回 StructuredTool，description 包含 when_to_use。"""
    skill = make_skill("tool_skill", should=True)
    # 给 metadata 加 when_to_use 文本
    skill.metadata.when_to_use = "技术岗 JD 时使用"
    skill.metadata.when_not_to_use = "产品岗时跳过"

    tool = skill.to_langchain_tool()

    assert tool.name == "tool_skill"
    assert "技术岗 JD 时使用" in tool.description
    assert "产品岗时跳过" in tool.description


# ---------------------------------------------------------------------------
# 6. SkillOutput 辅助方法
# ---------------------------------------------------------------------------


def test_skill_output_make_error() -> None:
    """make_error 应正确构造 success=False 的 SkillOutput。"""
    output = SkillOutput.make_error(
        skill_name="test_skill",
        error_code="SKILL_TIMEOUT",
        message="执行超时",
        latency_ms=5000,
    )
    assert output.success is False
    assert "SKILL_TIMEOUT" in output.error
    assert "执行超时" in output.error
    assert output.latency_ms == 5000
    assert output.skill_name == "test_skill"


# ---------------------------------------------------------------------------
# 7. 错误类
# ---------------------------------------------------------------------------


def test_skill_errors_hierarchy() -> None:
    """各异常子类应正确继承 SkillError，error_code 与 retryable 符合设计。"""
    assert issubclass(SkillTimeoutError, SkillError)
    assert issubclass(SkillInputError, SkillError)
    assert issubclass(SkillExternalError, SkillError)
    assert issubclass(SkillLLMError, SkillError)

    assert SkillTimeoutError.retryable is True
    assert SkillInputError.retryable is False
    assert SkillExternalError.retryable is True
    assert SkillLLMError.retryable is True

    assert SkillTimeoutError.error_code == "SKILL_TIMEOUT"
    assert SkillInputError.error_code == "SKILL_INPUT_INVALID"
    assert SkillExternalError.error_code == "SKILL_EXTERNAL_FAIL"
    assert SkillLLMError.error_code == "SKILL_LLM_FAIL"


def test_skill_error_is_exception() -> None:
    """SkillError 应可以被 except Exception 捕获。"""
    with pytest.raises(Exception):
        raise SkillTimeoutError("超时了", detail="detail info")


# ---------------------------------------------------------------------------
# 8. JDContext 便捷属性
# ---------------------------------------------------------------------------


def test_jd_context_shortcut_properties() -> None:
    """job_type / level / locale / channel 属性应正确代理 classification 字段。"""
    ctx = make_ctx(job_type="product", level="senior", locale="en", channel="campus")

    assert ctx.job_type == "product"
    assert ctx.level == "senior"
    assert ctx.locale == "en"
    assert ctx.channel == "campus"


def test_jd_context_shortcuts_none_when_no_classification() -> None:
    """classification 为 None 时，便捷属性均应返回 None（不抛异常）。"""
    ctx = JDContext(
        request_id="r",
        user_id="u",
        jd_text="jd",
        user_context=UserContext(),
    )
    assert ctx.classification is None
    assert ctx.job_type is None
    assert ctx.level is None
    assert ctx.locale is None
    assert ctx.channel is None


# ---------------------------------------------------------------------------
# 9. TemplateSkill 集成验证
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_skill_invoke_tech_jd() -> None:
    """TemplateSkill 对 tech 岗 JD 应成功执行，返回有效 SkillOutput。"""
    from jobpilot_agent.skills.skill_template.index import TemplateSkill

    skill = TemplateSkill()
    ctx = make_ctx(job_type="tech")
    assert skill.should_invoke(ctx) is True

    output = await skill.invoke(ctx)
    assert output.success is True
    assert output.skill_name == "template_skill"
    assert "field_a" in output.data


@pytest.mark.asyncio
async def test_template_skill_skips_non_tech_jd() -> None:
    """TemplateSkill 对非 tech 岗 JD should_invoke 应返回 False。"""
    from jobpilot_agent.skills.skill_template.index import TemplateSkill

    skill = TemplateSkill()
    ctx = make_ctx(job_type="product")
    assert skill.should_invoke(ctx) is False

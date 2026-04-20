"""en_translate Skill 实现与自注册。

触发条件：locale == "en" 或 公司在外资名单中 或 用户偏好英文输出
目标：生成英文 JD 摘要、中文摘要、STAR 格式简历要点和 ATS 关键词
"""

from __future__ import annotations

from typing import ClassVar

from jobpilot_agent.integrations.llm_client import TokenUsage, get_llm_client
from jobpilot_agent.skills.base import SkillMetadata, SkillOutput
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.en_translate.prompts import SYSTEM_PROMPT, build_user_prompt
from jobpilot_agent.skills.en_translate.schemas import EnTranslateData
from jobpilot_agent.skills.llm_skill_base import LLMSkillBase
from jobpilot_agent.skills.registry import registry

# 已知使用英文工作语言的外资/跨国公司（部分常见企业）
# 在实际产品中可从配置或数据库动态加载
FOREIGN_COMPANIES: frozenset[str] = frozenset(
    {
        # 科技巨头
        "google",
        "microsoft",
        "amazon",
        "meta",
        "apple",
        "netflix",
        "uber",
        "airbnb",
        "linkedin",
        "twitter",
        "x",
        "openai",
        "anthropic",
        # 咨询/金融
        "mckinsey",
        "bain",
        "bcg",
        "goldman sachs",
        "jp morgan",
        "jpmorgan",
        "morgan stanley",
        "blackrock",
        "bloomberg",
        # 外资制造/工业
        "siemens",
        "bosch",
        "abb",
        "philips",
        "shell",
        "bp",
        # 外资互联网/SaaS
        "salesforce",
        "oracle",
        "sap",
        "ibm",
        "intel",
        "amd",
        "nvidia",
        "qualcomm",
        "arm",
        "adobe",
        "autodesk",
        "zoom",
        "slack",
        "atlassian",
        "servicenow",
        "workday",
    }
)


def _is_foreign_company(company: str | None) -> bool:
    """判断公司名称是否在外资名单中（大小写不敏感，子字符串匹配）。

    Args:
        company: 公司名称，来自 JDContext.parsed_jd.get("company")。

    Returns:
        True 表示判断为外资/英文工作环境公司。
    """
    if not company:
        return False
    company_lower = company.lower()
    return any(fc in company_lower for fc in FOREIGN_COMPANIES)


class EnTranslateSkill(LLMSkillBase):
    """英文 JD 分析与翻译 Skill。

    触发逻辑（任一满足即触发）：
    1. locale == "en"（用户/JD 语言标记为英文）
    2. 公司名在 FOREIGN_COMPANIES 外资名单中
    3. user_context.preferred_lang == "en"（用户明确偏好英文输出）
    """

    metadata: ClassVar[SkillMetadata] = SkillMetadata(
        name="en_translate",
        version="0.1.0",
        description=(
            "为英文岗位或外资公司 JD 生成双语摘要、STAR 格式英文简历要点和 ATS 关键词"
        ),
        when_to_use=(
            "当 JD 语言为英文（locale=en），或岗位来自外资/跨国公司，"
            "或用户偏好英文输出时调用。"
            "帮助用户快速理解英文 JD 并生成针对性英文简历内容。"
        ),
        when_not_to_use=(
            "纯中文岗位（locale=zh）且公司非外资且用户未设置英文偏好时，"
            "不需要调用此 Skill，避免不必要的翻译开销。"
        ),
        tags=["llm", "translation", "english", "resume"],
    )

    def should_invoke(self, ctx: JDContext) -> bool:
        """当 locale=en 或外资公司或用户偏好英文时触发。"""
        if ctx.locale == "en":
            return True

        company = ctx.parsed_jd.get("company") if ctx.parsed_jd else None
        if _is_foreign_company(company):
            return True

        preferred_lang = getattr(ctx.user_context, "preferred_lang", None)
        if preferred_lang == "en":
            return True

        return False

    async def _run_llm(self, ctx: JDContext) -> tuple[EnTranslateData, TokenUsage]:
        """调用 LLM 生成双语摘要、简历要点和关键词。"""
        client = get_llm_client()
        result, usage = await client.chat_json(
            system=SYSTEM_PROMPT,
            user=build_user_prompt(ctx.jd_text),
            schema=EnTranslateData,
            model=ctx.llm_model,
            temperature=0.2,
            max_tokens=2500,
        )
        return result, usage  # type: ignore[return-value]


# ── 自注册 ──────────────────────────────────────────────────────────────────
registry.register(EnTranslateSkill())

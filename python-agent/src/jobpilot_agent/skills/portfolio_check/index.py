"""portfolio_check Skill 实现与自注册。

触发条件：job_type in {product, design} AND user_context.portfolio_doc_ref 非空
依赖：Python 侧通过 FeishuProxyClient 代理读取飞书云文档（不直接调飞书 API）
"""

from __future__ import annotations

import asyncio
import time
from typing import ClassVar

import httpx

from jobpilot_agent.integrations.feishu_proxy import get_feishu_proxy
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.skills.base import Skill, SkillMetadata, SkillOutput
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.portfolio_check.prompts import SYSTEM_PROMPT, build_user_prompt
from jobpilot_agent.skills.portfolio_check.schemas import PortfolioCheckData
from jobpilot_agent.skills.registry import registry

log = get_logger(__name__)

_PORTFOLIO_JOB_TYPES = frozenset({"product", "design"})


class PortfolioCheckSkill(Skill):
    """产品/设计岗位作品集完整性检测 Skill。

    通过 Node.js Gateway 代理读取飞书云文档，对照 JD 要求分析作品集覆盖度。

    反模式：不直接调飞书 API，必须通过 FeishuProxyClient。
    """

    metadata: ClassVar[SkillMetadata] = SkillMetadata(
        name="portfolio_check",
        version="0.1.0",
        description=(
            "检查产品/设计岗位的作品集完整性，对照 JD 要求提供覆盖度分析和优化建议"
        ),
        when_to_use=(
            "当 job_type 为 product 或 design，且 user_context 中提供了"
            " portfolio_doc_ref（飞书云文档 token）时调用。"
        ),
        when_not_to_use=(
            "tech 岗位（走 github_scan）或无 portfolio_doc_ref 时不调用。"
        ),
        tags=["external_api", "llm"],
    )

    def should_invoke(self, ctx: JDContext) -> bool:
        """当 job_type=product/design 且 portfolio_doc_ref 非空时触发。"""
        if ctx.classification is None:
            return False
        if ctx.classification.job_type not in _PORTFOLIO_JOB_TYPES:
            return False
        portfolio_ref = getattr(ctx.user_context, "portfolio_doc_ref", None)
        return bool(portfolio_ref)

    async def invoke(self, ctx: JDContext) -> SkillOutput:
        """读取飞书作品集 → LLM 分析覆盖度。"""
        start = time.monotonic()
        portfolio_ref: str = ctx.user_context.portfolio_doc_ref  # type: ignore[union-attr]

        # Step 1: 代理读取飞书文档
        try:
            portfolio_md = await asyncio.wait_for(
                get_feishu_proxy().read_doc(portfolio_ref),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error="SKILL_EXTERNAL_FAIL: feishu proxy timeout (15s)",
                latency_ms=self._measure_ms(start),
                external_calls=1,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error=f"SKILL_EXTERNAL_FAIL: {type(exc).__name__}: {exc}",
                latency_ms=self._measure_ms(start),
                external_calls=1,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("portfolio_check.doc_fetch_error", exc_type=type(exc).__name__)
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error=f"SKILL_ERROR: {type(exc).__name__}: {exc}",
                latency_ms=self._measure_ms(start),
                external_calls=1,
            )

        log.info(
            "portfolio_check.doc_fetched",
            doc_token=portfolio_ref[:8] + "...",
            content_len=len(portfolio_md),
        )

        # Step 2: LLM 分析
        try:
            client = get_llm_client()
            result, usage = await asyncio.wait_for(
                client.chat_json(
                    system=SYSTEM_PROMPT,
                    user=build_user_prompt(ctx.jd_text, portfolio_md),
                    schema=PortfolioCheckData,
                    model=ctx.llm_model,
                    temperature=0.0,
                    max_tokens=2500,
                ),
                timeout=float(ctx.timeout_seconds),
            )

            latency_ms = self._measure_ms(start)
            log.info(
                "portfolio_check.done",
                coverage_score=result.coverage_score,  # type: ignore[union-attr]
                tokens=usage.total_tokens,
                latency_ms=latency_ms,
            )

            return SkillOutput(
                skill_name=self.name,
                success=True,
                data=result.model_dump(),  # type: ignore[union-attr]
                latency_ms=latency_ms,
                tokens_used=usage.total_tokens,
                llm_calls=usage.call_count,
                external_calls=1,
            )

        except asyncio.TimeoutError:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error=f"SKILL_TIMEOUT: exceeded {ctx.timeout_seconds}s",
                latency_ms=self._measure_ms(start),
                external_calls=1,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("portfolio_check.error", exc_type=type(exc).__name__)
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error=f"SKILL_ERROR: {type(exc).__name__}: {exc}",
                latency_ms=self._measure_ms(start),
                external_calls=1,
            )


# ── 自注册 ──────────────────────────────────────────────────────────────────
registry.register(PortfolioCheckSkill())

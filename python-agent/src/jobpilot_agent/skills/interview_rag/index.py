"""interview_rag Skill 实现与自注册。

流程：
1. 两路并发 RAG 检索（tech_qa + project_deep_dive）
2. 按 doc_id 去重合并结果
3. 若无结果，降级返回空列表 + coverage_note（不调 LLM）
4. LLM 将检索结果改写为结构化面试题

触发条件：parsed_jd 中至少有 company 或 position 字段
"""

from __future__ import annotations

import asyncio
import time
from typing import ClassVar

from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.retrieval import RetrievalResult, search_interview_kb
from jobpilot_agent.skills.base import Skill, SkillMetadata, SkillOutput
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.interview_rag.prompts import SYSTEM_PROMPT, build_user_prompt
from jobpilot_agent.skills.interview_rag.schemas import InterviewRagData
from jobpilot_agent.skills.registry import registry

log = get_logger(__name__)


def _dedup_by_doc_id(results: list[RetrievalResult]) -> list[RetrievalResult]:
    """按 doc_id 去重，保留得分最高的副本。"""
    seen: dict[str, RetrievalResult] = {}
    for r in results:
        if r.doc_id not in seen or r.score > seen[r.doc_id].score:
            seen[r.doc_id] = r
    return sorted(seen.values(), key=lambda r: r.score, reverse=True)


class InterviewRagSkill(Skill):
    """基于面经库 RAG 检索的面试准备 Skill。

    两路检索策略：
    - tech_qa（技术问答）：top 8，覆盖技术深度题
    - project_deep_dive（项目深挖）：top 5，覆盖项目实战题
    并发执行以降低延迟，结果合并去重后送入 LLM 改写。
    """

    metadata: ClassVar[SkillMetadata] = SkillMetadata(
        name="interview_rag",
        version="0.1.0",
        description=(
            "基于公司/岗位/阶段从面经库检索真实历史面试题，生成针对性准备清单"
        ),
        when_to_use=(
            "当 parsed_jd 中有 company 或 position 字段时调用。"
            "适用于所有 job_type（tech/product/design/ops/mgmt）。"
            "输出可直接用于面试备考，每题含出题意图和回答要点。"
        ),
        when_not_to_use=(
            "JD 文本过短、无法提取公司名或岗位名时跳过，"
            "避免面经库召回与岗位无关的结果。"
        ),
        tags=["rag", "retrieval"],
    )

    def should_invoke(self, ctx: JDContext) -> bool:
        """当 parsed_jd 有 company 或 position 时触发。"""
        company = ctx.parsed_jd.get("company") if ctx.parsed_jd else None
        position = ctx.parsed_jd.get("position") if ctx.parsed_jd else None
        return bool(company or position)

    async def invoke(self, ctx: JDContext) -> SkillOutput:
        """执行面经 RAG 检索 + LLM 面试题生成。

        流程：
        1. 构造检索 query
        2. 两路并发 RAG 检索
        3. 去重合并
        4. 若空 → 降级返回
        5. LLM 改写输出结构化面试题
        """
        start = time.monotonic()
        company = ctx.parsed_jd.get("company", "") if ctx.parsed_jd else ""
        position = ctx.parsed_jd.get("position", "") if ctx.parsed_jd else ""
        query = f"{company} {position} 面试".strip()

        try:
            # 两路并发 RAG 检索
            tech_results, project_results = await asyncio.gather(
                search_interview_kb(
                    query=query, top_k=8, stage="tech_qa",
                    company=company or None,
                ),
                search_interview_kb(
                    query=query, top_k=5, stage="project_deep_dive",
                    company=company or None,
                ),
            )

            all_results = _dedup_by_doc_id([*tech_results, *project_results])
            latency_ms = self._measure_ms(start)

            log.info(
                "interview_rag.retrieval.done",
                tech_hits=len(tech_results),
                project_hits=len(project_results),
                deduped=len(all_results),
                latency_ms=latency_ms,
            )

            # 降级：无检索结果
            if not all_results:
                return SkillOutput(
                    skill_name=self.name,
                    success=True,
                    data=InterviewRagData(
                        retrieved_count=0,
                        questions=[],
                        coverage_note="未命中该公司/岗位的历史面经，建议补充面经数据后重试",
                    ).model_dump(),
                    latency_ms=latency_ms,
                    external_calls=2,
                )

            # LLM 改写
            avg_score = sum(r.score for r in all_results) / len(all_results)
            llm_start = time.monotonic()

            client = get_llm_client()
            result, usage = await asyncio.wait_for(
                client.chat_json(
                    system=SYSTEM_PROMPT,
                    user=build_user_prompt(company, position, all_results),
                    schema=InterviewRagData,
                    model=ctx.llm_model,
                    temperature=0.1,
                    max_tokens=3000,
                ),
                timeout=float(ctx.timeout_seconds),
            )

            result.retrieved_count = len(all_results)
            result.retrieval_metadata = {
                "tech_qa_hits": len(tech_results),
                "project_hits": len(project_results),
                "avg_score": round(avg_score, 4),
                "llm_latency_ms": self._measure_ms(llm_start),
            }
            if result.coverage_note is None:
                result.coverage_note = f"命中 {len(all_results)} 条相关面经"

            total_latency = self._measure_ms(start)
            log.info(
                "interview_rag.invoke.done",
                questions=len(result.questions),
                tokens=usage.total_tokens,
                latency_ms=total_latency,
            )

            return SkillOutput(
                skill_name=self.name,
                success=True,
                data=result.model_dump(),
                latency_ms=total_latency,
                tokens_used=usage.total_tokens,
                llm_calls=usage.call_count,
                external_calls=2,
            )

        except asyncio.TimeoutError:
            latency_ms = self._measure_ms(start)
            log.warning("interview_rag.timeout", timeout_s=ctx.timeout_seconds)
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error=f"SKILL_TIMEOUT: exceeded {ctx.timeout_seconds}s",
                latency_ms=latency_ms,
            )

        except Exception as exc:  # noqa: BLE001
            latency_ms = self._measure_ms(start)
            log.exception("interview_rag.error", exc_type=type(exc).__name__, error=str(exc))
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error=f"SKILL_ERROR: {type(exc).__name__}: {exc}",
                latency_ms=latency_ms,
            )


# ── 自注册 ──────────────────────────────────────────────────────────────────
registry.register(InterviewRagSkill())

"""github_scan Skill 实现与自注册。

触发条件：job_type=tech AND level in {senior, lead} AND user_context.github_username 非空
依赖：tech_stack_extract（用于对照 JD 技术栈，但 fallback 到 JD 原文）

合规性约束：
- 只用公开 API，无大权限 OAuth
- github_username 从 user_context 取，不从 JD 文本正则抽取
- 无 username 时 skip，不报错
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

import httpx

from jobpilot_agent.config import get_settings
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.skills.base import Skill, SkillMetadata, SkillOutput
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.github_scan.github_client import GitHubClient, get_github_client
from jobpilot_agent.skills.github_scan.prompts import SYSTEM_PROMPT, build_user_prompt
from jobpilot_agent.skills.github_scan.schemas import GitHubRepo, GitHubScanData
from jobpilot_agent.skills.registry import registry

log = get_logger(__name__)

_SENIOR_LEVELS = frozenset({"senior", "lead"})


def _aggregate_languages(lang_list: list[dict[str, int]]) -> dict[str, float]:
    """将多个仓库的语言字节数聚合为总占比（%）。"""
    totals: dict[str, int] = {}
    for lang_map in lang_list:
        for lang, bytes_count in lang_map.items():
            totals[lang] = totals.get(lang, 0) + bytes_count
    total_bytes = sum(totals.values()) or 1
    return {lang: round(cnt / total_bytes * 100, 1) for lang, cnt in totals.items()}


class GitHubScanSkill(Skill):
    """扫描候选人 GitHub 仓库，对照 JD 技术栈生成技术匹配度分析。

    顺序：
    1. 速率限制检查（剩余 ≤ buffer 时拒绝）
    2. 并发拉用户信息 + 仓库列表
    3. 筛选候选仓库（非 fork 且有 star 或近期活跃）
    4. 并发拉语言分布
    5. 串行拉 top-3 star 仓库 README（避免一次性并发过多）
    6. LLM 生成匹配度分析
    """

    metadata: ClassVar[SkillMetadata] = SkillMetadata(
        name="github_scan",
        version="0.1.0",
        description=(
            "扫描候选人 GitHub 仓库，对照 JD 技术栈要求生成技术匹配度分析"
        ),
        when_to_use=(
            "当 job_type=tech、level 为 senior/lead，"
            "且 user_context 中提供了 github_username 时调用。"
            "结果包含语言分布、命中/缺失技术栈、亮点项目和面试谈资。"
        ),
        when_not_to_use=(
            "非 tech 岗位、junior/middle 级别、或未提供 github_username 时不调用。"
            "不要从 JD 文本中正则抽取用户名（隐私风险）。"
        ),
        dependencies=["tech_stack_extract"],
        tags=["external_api", "llm"],
    )

    def should_invoke(self, ctx: JDContext) -> bool:
        """当 tech+senior/lead 且有 github_username 时触发。"""
        if ctx.classification is None:
            return False
        if ctx.classification.job_type != "tech":
            return False
        if ctx.classification.level not in _SENIOR_LEVELS:
            return False
        gh_user = getattr(ctx.user_context, "github_username", None)
        return bool(gh_user)

    async def invoke(self, ctx: JDContext) -> SkillOutput:
        """执行 GitHub 扫描 + LLM 匹配度分析。"""
        start = time.monotonic()
        username: str = ctx.user_context.github_username  # type: ignore[union-attr]
        settings = get_settings()
        gh = get_github_client()

        try:
            # Step 1: 速率限制检查
            remaining = await gh.get_rate_limit_remaining()
            if 0 <= remaining <= settings.github_rate_limit_buffer:
                return SkillOutput(
                    skill_name=self.name,
                    success=False,
                    error=f"SKILL_EXTERNAL_FAIL: GitHub rate limit too low ({remaining} remaining)",
                    latency_ms=self._measure_ms(start),
                )

            # Step 2: 并发拉用户信息和仓库列表
            user_info, raw_repos = await asyncio.gather(
                gh.get_user(username),
                gh.list_repos(username, per_page=30),
            )

            # Step 3: 筛选候选仓库（非 fork 且有 star 或近期活跃）
            candidates = [
                r for r in raw_repos
                if not r.get("fork") and (
                    r.get("stargazers_count", 0) >= 1 or GitHubClient.is_recent(r)
                )
            ][:10]

            # Step 4: 并发拉语言分布
            lang_list: list[dict[str, int]] = await asyncio.gather(
                *[gh.get_repo_languages(username, r["name"]) for r in candidates]
            ) if candidates else []

            lang_distribution = _aggregate_languages(list(lang_list))

            # Step 5: 拉 top-3 star 仓库的 README
            top_repos = sorted(candidates, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:3]
            readmes: list[tuple[str, str | None]] = []
            for repo in top_repos:
                readme = await gh.get_readme(username, repo["name"])
                readmes.append((repo["name"], readme))

            external_calls = 3 + len(candidates)  # user + repos + rate_limit + languages

            # Step 6: 构造 JD 技术栈（从 parsed_jd 或 JD 原文）
            tech_stack: list[str] = []
            if ctx.parsed_jd:
                raw_stack = ctx.parsed_jd.get("tech_stack", [])
                if isinstance(raw_stack, list):
                    tech_stack = [
                        item.get("name", "") if isinstance(item, dict) else str(item)
                        for item in raw_stack
                    ]

            # Step 7: LLM 分析
            client = get_llm_client()
            result, usage = await asyncio.wait_for(
                client.chat_json(
                    system=SYSTEM_PROMPT,
                    user=build_user_prompt(
                        username=username,
                        user_info=user_info,
                        top_repos=candidates,
                        lang_distribution=lang_distribution,
                        readmes=readmes,
                        jd_text=ctx.jd_text,
                        tech_stack=tech_stack,
                    ),
                    schema=GitHubScanData,
                    model=ctx.llm_model,
                    temperature=0.0,
                    max_tokens=2500,
                ),
                timeout=float(ctx.timeout_seconds),
            )

            # 确保关键字段有值
            scan_data: GitHubScanData = result  # type: ignore[assignment]
            scan_data.username = username
            scan_data.public_repo_count = user_info.get("public_repos", 0)
            scan_data.total_stars = sum(r.get("stargazers_count", 0) for r in candidates)
            if not scan_data.top_repos and top_repos:
                scan_data.top_repos = [
                    GitHubRepo(
                        name=r["name"],
                        description=r.get("description"),
                        stars=r.get("stargazers_count", 0),
                        primary_language=r.get("language"),
                        recent_activity=GitHubClient.is_recent(r),
                        url=r.get("html_url", f"https://github.com/{username}/{r['name']}"),
                    )
                    for r in top_repos
                ]

            latency_ms = self._measure_ms(start)
            log.info(
                "github_scan.done",
                username=username,
                repos=len(candidates),
                matched=len(scan_data.matched_stack),
                missing=len(scan_data.missing_stack),
                tokens=usage.total_tokens,
                latency_ms=latency_ms,
            )

            return SkillOutput(
                skill_name=self.name,
                success=True,
                data=scan_data.model_dump(),
                latency_ms=latency_ms,
                tokens_used=usage.total_tokens,
                llm_calls=usage.call_count,
                external_calls=external_calls,
            )

        except httpx.HTTPStatusError as exc:
            latency_ms = self._measure_ms(start)
            if exc.response.status_code == 404:
                return SkillOutput(
                    skill_name=self.name,
                    success=False,
                    error=f"SKILL_INPUT_INVALID: GitHub user '{username}' not found",
                    latency_ms=latency_ms,
                )
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error=f"SKILL_EXTERNAL_FAIL: HTTP {exc.response.status_code}: {exc}",
                latency_ms=latency_ms,
            )

        except asyncio.TimeoutError:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error=f"SKILL_TIMEOUT: exceeded {ctx.timeout_seconds}s",
                latency_ms=self._measure_ms(start),
            )

        except Exception as exc:  # noqa: BLE001
            log.exception("github_scan.error", exc_type=type(exc).__name__)
            return SkillOutput(
                skill_name=self.name,
                success=False,
                error=f"SKILL_ERROR: {type(exc).__name__}: {exc}",
                latency_ms=self._measure_ms(start),
            )


# ── 自注册 ──────────────────────────────────────────────────────────────────
registry.register(GitHubScanSkill())

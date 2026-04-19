"""成本对比指标计算。

对比主图（有路由）与 Baseline（全选 Skill）的 Token 消耗与估算费用。

豆包定价参考（2024-2025，火山方舟官网）：
- doubao-pro-4k：输入 ¥0.0008/1K tokens，输出 ¥0.002/1K tokens
- 默认使用保守的混合估算：¥0.001/1K tokens（可通过参数覆盖）
- 如需精确计算，请分别传入 input_price / output_price

换算 CNY→USD：按 1 USD = 7.2 CNY 估算，仅供参考。
"""

from __future__ import annotations

from pydantic import BaseModel

from jobpilot_agent.evaluation.runners.scenario_a_runner import RunRecord

_CNY_TO_USD = 1 / 7.2


class RunCostStats(BaseModel):
    """单次运行的 Token 和成本统计。

    Attributes:
        total_tokens: 总 token 消耗（含所有节点和 Skill）。
        avg_tokens_per_jd: 每条 JD 平均 token 消耗。
        total_llm_calls: 总 LLM API 调用次数。
        total_external_calls: 总外部 API 调用次数（不含 LLM）。
        estimated_cost_cny: 估算费用（人民币）。
        estimated_cost_usd: 估算费用（美元，参考值）。
        evaluated_count: 参与计算的记录数。
    """

    total_tokens: int
    avg_tokens_per_jd: float
    total_llm_calls: int
    total_external_calls: int
    estimated_cost_cny: float
    estimated_cost_usd: float
    evaluated_count: int


class CostComparison(BaseModel):
    """主图 vs Baseline 成本对比。

    Attributes:
        main: 主图成本统计。
        baseline: Baseline 成本统计。
        token_reduction_pct: Token 降低比例（0~1）。正值表示主图更省。
        llm_call_reduction_pct: LLM 调用次数降低比例。
        cost_saved_pct: 费用节省比例（=token_reduction_pct）。
        token_price_per_1k_cny: 本次计算使用的定价（元/千 token）。
    """

    main: RunCostStats
    baseline: RunCostStats
    token_reduction_pct: float
    llm_call_reduction_pct: float
    cost_saved_pct: float
    token_price_per_1k_cny: float


def _compute_run_stats(
    records: list[RunRecord],
    token_price_per_1k_cny: float,
) -> RunCostStats:
    """计算单次运行的成本统计。"""
    valid = [r for r in records if r.success]
    if not valid:
        n = len(records)
        return RunCostStats(
            total_tokens=0,
            avg_tokens_per_jd=0.0,
            total_llm_calls=0,
            total_external_calls=0,
            estimated_cost_cny=0.0,
            estimated_cost_usd=0.0,
            evaluated_count=n,
        )

    total_tokens = sum(r.total_tokens for r in valid)
    total_llm_calls = sum(r.llm_calls for r in valid)
    total_external_calls = sum(r.external_calls for r in valid)
    evaluated_count = len(valid)

    estimated_cost_cny = total_tokens / 1000 * token_price_per_1k_cny
    estimated_cost_usd = estimated_cost_cny * _CNY_TO_USD

    return RunCostStats(
        total_tokens=total_tokens,
        avg_tokens_per_jd=total_tokens / evaluated_count,
        total_llm_calls=total_llm_calls,
        total_external_calls=total_external_calls,
        estimated_cost_cny=estimated_cost_cny,
        estimated_cost_usd=estimated_cost_usd,
        evaluated_count=evaluated_count,
    )


def compute_cost_comparison(
    main_records: list[RunRecord],
    baseline_records: list[RunRecord],
    token_price_per_1k_cny: float = 0.001,
) -> CostComparison:
    """计算主图与 Baseline 的成本对比。

    Args:
        main_records: 主图运行记录。
        baseline_records: Baseline 运行记录。
        token_price_per_1k_cny: 每千 token 费用（人民币）。
            doubao-pro-4k 参考值：混合估算约 ¥0.001/1K。

    Returns:
        CostComparison 实例。
    """
    main_stats = _compute_run_stats(main_records, token_price_per_1k_cny)
    baseline_stats = _compute_run_stats(baseline_records, token_price_per_1k_cny)

    if baseline_stats.total_tokens > 0:
        token_reduction_pct = (
            baseline_stats.total_tokens - main_stats.total_tokens
        ) / baseline_stats.total_tokens
    else:
        token_reduction_pct = 0.0

    if baseline_stats.total_llm_calls > 0:
        llm_call_reduction_pct = (
            baseline_stats.total_llm_calls - main_stats.total_llm_calls
        ) / baseline_stats.total_llm_calls
    else:
        llm_call_reduction_pct = 0.0

    return CostComparison(
        main=main_stats,
        baseline=baseline_stats,
        token_reduction_pct=token_reduction_pct,
        llm_call_reduction_pct=llm_call_reduction_pct,
        cost_saved_pct=token_reduction_pct,
        token_price_per_1k_cny=token_price_per_1k_cny,
    )

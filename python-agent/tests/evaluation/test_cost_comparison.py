"""test_cost_comparison.py — 成本对比指标单元测试。

验证 token reduction 公式和费用估算计算。
"""

from __future__ import annotations

from jobpilot_agent.evaluation.metrics.cost import compute_cost_comparison
from tests.evaluation.conftest import make_record


def _make_records(count: int, tokens: int, llm_calls: int = 3) -> list:
    return [
        make_record(jd_id=f"r_{i}", total_tokens=tokens, llm_calls=llm_calls)
        for i in range(count)
    ]


def test_token_reduction_pct():
    """主图 1000 tokens，baseline 2000 tokens → reduction = 50%。"""
    main_records = _make_records(10, tokens=1000)
    base_records = _make_records(10, tokens=2000)
    cost = compute_cost_comparison(main_records, base_records)
    assert abs(cost.token_reduction_pct - 0.5) < 1e-6


def test_token_reduction_zero():
    """主图与 baseline tokens 相同 → reduction = 0%。"""
    records = _make_records(10, tokens=1500)
    cost = compute_cost_comparison(records, records)
    assert abs(cost.token_reduction_pct - 0.0) < 1e-6


def test_cost_saved_equals_token_reduction():
    """cost_saved_pct == token_reduction_pct（同比例计费）。"""
    main_records = _make_records(10, tokens=1200)
    base_records = _make_records(10, tokens=2000)
    cost = compute_cost_comparison(main_records, base_records)
    assert abs(cost.cost_saved_pct - cost.token_reduction_pct) < 1e-6


def test_estimated_cost_cny():
    """10 条 × 1000 tokens = 10000 tokens；@ ¥0.001/1K = ¥0.01。"""
    main_records = _make_records(10, tokens=1000)
    base_records = _make_records(10, tokens=2000)
    cost = compute_cost_comparison(main_records, base_records, token_price_per_1k_cny=0.001)
    assert abs(cost.main.estimated_cost_cny - 0.01) < 1e-6
    assert abs(cost.baseline.estimated_cost_cny - 0.02) < 1e-6


def test_avg_tokens_per_jd():
    """平均 tokens/JD = total/count。"""
    main_records = _make_records(10, tokens=1500)
    base_records = _make_records(10, tokens=3000)
    cost = compute_cost_comparison(main_records, base_records)
    assert abs(cost.main.avg_tokens_per_jd - 1500.0) < 1e-6
    assert abs(cost.baseline.avg_tokens_per_jd - 3000.0) < 1e-6


def test_llm_call_reduction():
    """主图 3 calls/JD，baseline 6 calls/JD → 减少 50%。"""
    main_records = _make_records(10, tokens=1000, llm_calls=3)
    base_records = _make_records(10, tokens=1000, llm_calls=6)
    cost = compute_cost_comparison(main_records, base_records)
    assert abs(cost.llm_call_reduction_pct - 0.5) < 1e-6


def test_target_reduction_30pct():
    """主图 tokens < 70% baseline → 满足 ≥ 30% 降幅目标。"""
    main_records = _make_records(10, tokens=1400)
    base_records = _make_records(10, tokens=2000)
    cost = compute_cost_comparison(main_records, base_records)
    assert cost.token_reduction_pct >= 0.30, (
        f"Token reduction {cost.token_reduction_pct:.2%} < 30% target"
    )


def test_empty_baseline_records():
    """baseline 为空 → 降幅 = 0，不报错。"""
    main_records = _make_records(10, tokens=1000)
    cost = compute_cost_comparison(main_records, [])
    assert cost.token_reduction_pct == 0.0


def test_failed_records_excluded():
    """success=False 的记录不计入 token 统计。"""
    valid = _make_records(8, tokens=1000)
    failed = [make_record(jd_id=f"fail_{i}", success=False, total_tokens=99999) for i in range(2)]
    base_records = _make_records(10, tokens=2000)
    cost = compute_cost_comparison(valid + failed, base_records)
    assert cost.main.total_tokens == 8000  # 只有 8 条有效

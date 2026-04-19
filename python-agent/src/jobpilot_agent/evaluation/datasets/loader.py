"""加载并验证 JD 评估数据集。

数据集格式（JSONL，每行一个 JSON 对象）：
    {
        "jd_id": "abc123",
        "jd_text": "...",
        "labels": {"job_type": "tech", "sub_type": "backend_engineer", ...},
        "expected_skills": ["tech_stack_extract", "interview_rag"],
        "forbidden_skills": ["gpa_check", "en_translate"],
        "annotator": "llm+human_reviewed",
        "confidence": 0.8,
        ...
    }
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EvaluationExample(BaseModel):
    """单条 JD 评估样本。

    Attributes:
        jd_id: 数据集内唯一 ID。
        jd_text: 原始 JD 文本。
        labels: 五维分类 ground truth（job_type/sub_type/level/locale/channel）。
        expected_skills: 本 JD 应被触发的 Skill 名称列表。
        forbidden_skills: 本 JD 不应被触发的 Skill 名称列表。
        confidence: 标注置信度（0~1），可用于加权评估。
        annotator: 标注来源（如 llm_only / llm+human_reviewed）。
    """

    jd_id: str
    jd_text: str
    labels: dict[str, Any]
    expected_skills: list[str] = Field(default_factory=list)
    forbidden_skills: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    annotator: str = "unknown"


def load_jd_eval_dataset(
    path: str | Path = "knowledge-base/data/labeled/jd_labeled.jsonl",
    sample_size: int | None = None,
    seed: int = 42,
) -> list[EvaluationExample]:
    """加载 JD 评估数据集，可选随机抽样。

    Args:
        path: JSONL 文件路径。支持绝对路径和相对于 python-agent/ 目录的相对路径。
        sample_size: 抽样数量；None 表示全量加载。
        seed: 随机种子，保证抽样可复现。

    Returns:
        EvaluationExample 列表，按 jd_id 字母序排序（确保顺序稳定）。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ValueError: 数据格式不合法时抛出（单行错误时跳过并 warn）。
    """
    file_path = Path(path)
    if not file_path.is_absolute():
        # 尝试从 python-agent/ 目录相对路径解析
        candidates = [
            file_path,
            Path(__file__).resolve().parents[6] / path,  # workspace root
            Path(__file__).resolve().parents[5] / path,  # python-agent parent
        ]
        for candidate in candidates:
            if candidate.exists():
                file_path = candidate
                break
        else:
            raise FileNotFoundError(
                f"找不到数据集文件：{path}。"
                "请确认路径正确，或传入绝对路径。"
            )

    examples: list[EvaluationExample] = []
    skip_count = 0

    with open(file_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                example = EvaluationExample(
                    jd_id=raw["jd_id"],
                    jd_text=raw["jd_text"],
                    labels=raw.get("labels") or {},
                    expected_skills=raw.get("expected_skills") or [],
                    forbidden_skills=raw.get("forbidden_skills") or [],
                    confidence=float(raw.get("confidence") or 1.0),
                    annotator=raw.get("annotator") or "unknown",
                )
                examples.append(example)
            except (KeyError, ValueError, Exception) as exc:  # noqa: BLE001
                skip_count += 1
                if skip_count <= 5:
                    import warnings
                    warnings.warn(
                        f"第 {lineno} 行解析失败，已跳过：{exc}",
                        stacklevel=2,
                    )

    if skip_count > 0:
        import warnings
        warnings.warn(f"共跳过 {skip_count} 条无效记录", stacklevel=2)

    # 排序保证顺序稳定
    examples.sort(key=lambda e: e.jd_id)

    if sample_size is not None and sample_size < len(examples):
        rng = random.Random(seed)
        examples = rng.sample(examples, sample_size)
        examples.sort(key=lambda e: e.jd_id)  # 再次排序保证稳定性

    return examples


def get_all_skill_names(examples: list[EvaluationExample]) -> list[str]:
    """从数据集中收集所有出现过的 Skill 名称（去重排序）。

    用于初始化 routing 指标的 per-skill 统计维度。
    """
    skills: set[str] = set()
    for ex in examples:
        skills.update(ex.expected_skills)
        skills.update(ex.forbidden_skills)
    return sorted(skills)

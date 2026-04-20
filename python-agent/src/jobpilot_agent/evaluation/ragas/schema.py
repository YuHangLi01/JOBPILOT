"""RAGAS 评估数据 Schema。

RagasExample  — 单条评估样本（question / contexts / answer / ground_truth）
RagasResult   — 单条 RAGAS 评估结果（四项指标）
RagasAggregate — 100 条聚合结果
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class RagasExample(BaseModel):
    """单条 RAGAS 评估样本。

    Attributes:
        example_id: 唯一 ID（来自 jd_id）。
        jd_id: 原始 jd_labeled 中的 jd_id。
        jd_text: 原始 JD 文本。
        company: 公司名（从 JD 提取或 fallback）。
        position: 岗位名（从 JD 提取或 fallback）。
        question: 构造的评估问题。
        contexts: interview_rag 检索到的原始面经 turn 文本列表（RAGAS 输入）。
        answer: final_result.interview_questions 转成的文本（RAGAS 输入）。
        ground_truth: 期望答案（人工/LLM 辅助标注）。
        ground_truth_doc_ids: ground_truth 溯源 doc_id 列表（可选）。
        ground_truth_source: 标注来源。
    """

    example_id: str
    jd_id: str
    jd_text: str
    company: str
    position: str
    job_type: str = "unknown"
    question: str

    contexts: list[str] = Field(default_factory=list)
    answer: str = ""

    ground_truth: str = ""
    ground_truth_doc_ids: list[str] = Field(default_factory=list)
    ground_truth_source: Literal["human", "llm_assisted"] = "llm_assisted"


class RagasResult(BaseModel):
    """单条 RAGAS 评估结果。"""

    example_id: str

    context_relevancy: float = 0.0
    context_recall: float = 0.0
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0

    error: Optional[str] = None


class RagasCompanyMetric(BaseModel):
    """按公司或 job_type 分组的聚合指标。"""

    count: int
    mean_context_relevancy: float
    mean_context_recall: float
    mean_faithfulness: float
    mean_answer_relevancy: float


class RagasAggregate(BaseModel):
    """100 条评估的聚合结果。"""

    total: int
    successful: int

    mean_context_relevancy: float
    mean_context_recall: float
    mean_faithfulness: float
    mean_answer_relevancy: float

    by_company: dict[str, RagasCompanyMetric] = Field(default_factory=dict)
    by_job_type: dict[str, RagasCompanyMetric] = Field(default_factory=dict)

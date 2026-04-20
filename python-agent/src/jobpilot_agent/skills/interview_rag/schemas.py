"""interview_rag Skill 输出 Schema。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class InterviewQuestion(BaseModel):
    """基于面经 RAG 生成的单道面试题。

    Attributes:
        question: 面试题目完整文本。
        source_company: 题目所属公司（来自面经库元数据）。
        source_stage: 面试阶段。
        intent: 出题意图（具体考察哪种能力/知识点）。
        answer_points: 回答要点列表（3–5 条，可直接练习）。
        rag_source_doc_ids: 支撑该题的面经 turn doc_id 列表（防幻觉溯源）。
        rag_score: 相关度平均分。
    """

    question: str = Field(description="完整的面试题目文本")
    source_company: str = Field(description="题目来自哪家公司的面经库，如 '字节跳动'")
    source_stage: Literal["tech_qa", "project_deep_dive", "scenario", "hr", "unknown"] = Field(
        default="tech_qa",
        description="面试阶段：tech_qa=技术问答 | project_deep_dive=项目深挖 | scenario=情景题 | hr=HR 面 | unknown=未知",
    )
    intent: str = Field(
        description="出题意图，具体说明考察什么能力或知识点，如 '考察候选人对 Redis 持久化机制的理解'"
    )
    answer_points: list[str] = Field(
        description="回答要点，3–5 条，每条可直接用于准备练习",
        min_length=1,
    )
    rag_source_doc_ids: list[str] = Field(
        default_factory=list,
        description="支撑该题的面经原文 doc_id 列表，至少 1 个（用于溯源，防止 LLM 幻觉）",
    )
    rag_score: float = Field(
        default=0.0,
        description="该题在面经库中的相关度平均分（来自 RetrievalResult.score）",
    )


class InterviewRagData(BaseModel):
    """interview_rag Skill 完整输出。

    Attributes:
        retrieved_count: 实际检索到的面经 turn 数量（去重后）。
        questions: LLM 生成的结构化面试题列表。
        coverage_note: 当检索结果为空或不足时的说明文字。
        retrieval_metadata: 检索统计信息（各阶段命中数、平均分等）。
    """

    retrieved_count: int = Field(default=0, description="检索到的有效面经片段数量（去重后）")
    questions: list[InterviewQuestion] = Field(
        default_factory=list,
        description="生成的面试题列表，按重要性降序排列",
    )
    coverage_note: Optional[str] = Field(
        default=None,
        description="检索说明，如 '未命中该公司/岗位的历史面经' 或 '检索到 N 条相关面经'",
    )
    retrieval_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="检索统计：tech_qa_hits, project_hits, avg_score 等",
    )
    raw_retrieved_texts: list[str] = Field(
        default_factory=list,
        description="原始检索到的面经 turn 完整文本（RAGAS contexts 字段来源）",
    )

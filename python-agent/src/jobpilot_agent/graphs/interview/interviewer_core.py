"""InterviewerCore：面试官核心行为抽象。

纯方法类（无副作用、无状态），子图节点与 Replay 评估共同调用，
保证两处「面试官行为」语义一致。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from jobpilot_agent.graphs.interview.state import (
    CandidateProfile,
    InterviewStage,
    PerformanceSignal,
    Turn,
)
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.retrieval import RetrievalResult, search_interview_kb

log = get_logger(__name__)


# ── 数据模型 ────────────────────────────────────────────────────────────────


class InterviewerQuestion(BaseModel):
    """面试官生成的下一问"""

    content: str
    intent: str
    answer_points: list[str]
    rag_source_doc_ids: list[str] = []
    alternatives: list[str] = []


class InterviewerInput(BaseModel):
    """生成下一问时的全部输入"""

    company: str
    position: str
    stage: InterviewStage
    candidate_profile: CandidateProfile | None = None
    transcript: list[Turn] = []
    stage_round: int = 0
    max_stage_rounds: int = 5


class _MultiQuestions(BaseModel):
    questions: list[InterviewerQuestion]


class _JudgeContinue(BaseModel):
    should_continue: bool
    reason: str


class _StagePrediction(BaseModel):
    predicted_stage: str
    confidence: Literal["high", "medium", "low"]
    reasoning: str


class _EvalSignals(BaseModel):
    signals: list[PerformanceSignal]


# ── InterviewerCore ─────────────────────────────────────────────────────────


class InterviewerCore:
    """面试官核心行为——根据对话上下文出下一问、评分、判断是否继续。

    设计原则：
    - 纯方法（无副作用、无状态），state 由子图管理
    - generate_next_question()：出一问（子图节点用）
    - generate_top_k_questions()：出 K 个候选（Replay 评估用）
    - RAG 检索面经作为「出题灵感」，保证子图与评估行为一致
    """

    def __init__(self, llm_model: str | None = None) -> None:
        self.llm = get_llm_client()
        self.model = llm_model

    async def generate_next_question(
        self,
        input: InterviewerInput,
    ) -> InterviewerQuestion:
        """按 stage 生成下一问（temperature=0.7 以保持多样性）。"""
        rag_docs = await self._retrieve_rag_context(input)
        prompt_builder = self._get_prompt_builder(input.stage)
        system_prompt, user_prompt = prompt_builder(input, rag_docs)

        result, usage = await self.llm.chat_json(
            system=system_prompt,
            user=user_prompt,
            schema=InterviewerQuestion,
            model=self.model,
            temperature=0.7,
        )
        assert isinstance(result, InterviewerQuestion)
        result.rag_source_doc_ids = [d.doc_id for d in rag_docs[:3]]
        log.info(
            "interviewer_core.question_generated",
            stage=input.stage,
            round=input.stage_round,
            tokens=usage.total_tokens,
        )
        return result

    async def generate_top_k_questions(
        self,
        input: InterviewerInput,
        k: int = 5,
    ) -> list[InterviewerQuestion]:
        """一次调用生成 K 个候选问题，供 Replay 评估计算 Rank@K。"""
        rag_docs = await self._retrieve_rag_context(input)
        prompt_builder = self._get_prompt_builder(input.stage)
        system_prompt, user_prompt = prompt_builder(input, rag_docs, top_k=k)

        result, _ = await self.llm.chat_json(
            system=system_prompt,
            user=user_prompt,
            schema=_MultiQuestions,
            model=self.model,
            temperature=0.9,
            timeout=60.0,
            max_tokens=3000,
        )
        assert isinstance(result, _MultiQuestions)
        return result.questions[:k]

    async def predict_stage(self, history: list[Turn]) -> InterviewStage:
        """根据对话历史预测当前所处面试阶段（阶段推进准确率评估用）。"""
        from typing import get_args

        from jobpilot_agent.graphs.interview.transcript import format_transcript_for_llm

        transcript_text = format_transcript_for_llm(
            history, include_stage_markers=False, last_n=30
        )
        system = (
            "你是面试阶段分类专家。根据对话内容，判断当前处于哪个面试阶段。\n"
            "候选阶段：\n"
            "- intro：开场暖场、自我介绍、背景了解\n"
            "- project_deep_dive：深挖项目经历、技术实现细节、挑战与复盘\n"
            "- tech_qa：纯技术知识点（算法/数据结构/系统设计/语言特性）\n"
            "- scenario：情境题（假设你负责…你会怎么做）、STAR 结构\n"
            "- reverse：候选人向面试官反问阶段\n"
            "- closing：面试收尾、感谢告别\n\n"
            '只输出 JSON：{"predicted_stage": "tech_qa", "confidence": "high", "reasoning": "…"}'
        )
        result, _ = await self.llm.chat_json(
            system=system,
            user=transcript_text,
            schema=_StagePrediction,
            temperature=0.0,
        )
        assert isinstance(result, _StagePrediction)
        valid_stages = get_args(InterviewStage)
        if result.predicted_stage not in valid_stages:
            log.warning(
                "interviewer_core.predict_stage.invalid",
                predicted=result.predicted_stage,
            )
            return "tech_qa"
        log.debug(
            "interviewer_core.predict_stage.done",
            predicted=result.predicted_stage,
            confidence=result.confidence,
        )
        return result.predicted_stage  # type: ignore[return-value]

    async def evaluate_candidate_answer(
        self,
        question: str,
        answer: str,
        stage: InterviewStage,
        question_answer_points: list[str],
        turn_id: int,
    ) -> list[PerformanceSignal]:
        """对候选人的一轮回答进行多维度打分。"""
        from jobpilot_agent.graphs.interview.prompts.evaluate import build_evaluate_prompt

        system, user = build_evaluate_prompt(question, answer, stage, question_answer_points)

        result, _ = await self.llm.chat_json(
            system=system,
            user=user,
            schema=_EvalSignals,
            temperature=0.0,
        )
        assert isinstance(result, _EvalSignals)
        # 补充 turn_id 和 stage（评分 prompt 输出时不含这两个字段）
        signals: list[PerformanceSignal] = []
        for s in result.signals:
            signals.append(
                PerformanceSignal(
                    turn_id=turn_id,
                    stage=stage,
                    dimension=s.dimension,
                    score=s.score,
                    evidence=s.evidence,
                    improvement_hint=s.improvement_hint,
                )
            )
        return signals

    async def judge_should_continue(
        self,
        input: InterviewerInput,
    ) -> bool:
        """判断当前阶段是否应继续追问。

        规则：
        - round < 3 → 总是继续
        - round >= max_stage_rounds → 停止
        - 中间区间 → LLM 判断
        """
        if input.stage_round < 3:
            return True
        if input.stage_round >= input.max_stage_rounds:
            return False

        from jobpilot_agent.graphs.interview.prompts.evaluate import build_judge_continue_prompt
        from jobpilot_agent.graphs.interview.transcript import format_transcript_for_llm

        summary = format_transcript_for_llm(input.transcript, last_n=10)
        system, user = build_judge_continue_prompt(input.stage, input.stage_round, summary)

        result, _ = await self.llm.chat_json(
            system=system,
            user=user,
            schema=_JudgeContinue,
            temperature=0.0,
        )
        assert isinstance(result, _JudgeContinue)
        return result.should_continue

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    async def _retrieve_rag_context(
        self,
        input: InterviewerInput,
    ) -> list[RetrievalResult]:
        try:
            return await search_interview_kb(
                query=f"{input.company} {input.position} {input.stage}",
                top_k=5,
                stage=input.stage,
                company=input.company or None,
            )
        except Exception as e:
            log.warning("interviewer_core.rag_failed", error=str(e))
            return []

    def _get_prompt_builder(self, stage: InterviewStage) -> Callable[..., tuple[str, str]]:
        from jobpilot_agent.graphs.interview.prompts import (
            intro,
            project_deep_dive,
            reverse,
            scenario,
            tech_qa,
        )

        mapping = {
            "intro": intro.build_prompt,
            "project_deep_dive": project_deep_dive.build_prompt,
            "tech_qa": tech_qa.build_prompt,
            "scenario": scenario.build_prompt,
            "reverse": reverse.build_prompt,
        }
        builder = mapping.get(stage)
        if builder is None:
            raise ValueError(f"No prompt builder for stage: {stage}")
        return builder


# ── 进程级单例 ────────────────────────────────────────────────────────────────

_core_instance: InterviewerCore | None = None


def get_interviewer_core() -> InterviewerCore:
    global _core_instance
    if _core_instance is None:
        _core_instance = InterviewerCore()
    return _core_instance

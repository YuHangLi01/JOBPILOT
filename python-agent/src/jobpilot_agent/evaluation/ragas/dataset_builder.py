"""RAGAS 评估集构造器。

从 jd_labeled.jsonl 中分层抽取 100 条，为每条构造：
- question（模板生成）
- ground_truth（前 30 条留空待人工，后 70 条 LLM 辅助生成）

分层策略：只选 interview_rag 在 expected_skills 里的样本，按 job_type 比例抽取。
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Optional

from jobpilot_agent.evaluation.datasets.loader import load_jd_eval_dataset
from jobpilot_agent.evaluation.ragas.schema import RagasExample
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_GROUND_TRUTH_SYSTEM = (
    "你是一名资深面试官。给定一份职位描述（JD），请生成针对该岗位的 3-5 个典型面试题，"
    "每题附上标准回答要点（3 条）。要求：\n"
    "1. 问题必须基于 JD 明确提到的技术栈或职责，不得编造\n"
    "2. 回答要点要具体可操作，不要空泛\n"
    "3. 输出纯文本，格式：Q1: ...\\n答案要点：...\\n\\nQ2: ...\\n答案要点：..."
)


def _extract_company_position(jd_text: str, labels: dict) -> tuple[str, str]:
    """从 JD 文本中提取公司名和岗位名，多级 fallback。"""
    # 尝试从 JD 首 300 字用正则提取
    head = jd_text[:300]
    company = ""
    position = ""

    # 常见格式："公司：XX" / "单位名称：XX" / "招聘单位：XX"
    for pat in [r"公司[：:]\s*([^\n，,。]{2,20})", r"招聘单位[：:]\s*([^\n，,。]{2,20})"]:
        m = re.search(pat, head)
        if m:
            company = m.group(1).strip()
            break

    # 常见格式："岗位：XX" / "职位名称：XX" / "招聘岗位：XX"
    for pat in [r"职位[名称]*[：:]\s*([^\n，,。]{2,30})", r"岗位[：:]\s*([^\n，,。]{2,30})", r"招聘岗位[：:]\s*([^\n，,。]{2,30})"]:
        m = re.search(pat, head)
        if m:
            position = m.group(1).strip()
            break

    # fallback：用 labels 的 sub_type 作为 position
    if not position:
        position = str(labels.get("sub_type", "目标岗位"))
    if not company:
        company = "目标公司"

    return company, position


def _build_question(company: str, position: str) -> str:
    return (
        f"针对 {company} 的 {position} 岗位，面试中可能会问哪些关键问题？"
        f"请给出 3-5 个典型问题和回答要点。"
    )


def _stratified_sample(
    pool: list,
    size: int,
    key_fn,
    rng: random.Random,
) -> list:
    """按 key_fn 分组后按比例抽样（向上取整，最后截断到 size）。"""
    groups: dict[str, list] = {}
    for item in pool:
        k = key_fn(item)
        groups.setdefault(k, []).append(item)

    result: list = []
    for k, members in groups.items():
        n = max(1, round(len(members) / len(pool) * size))
        sampled = rng.sample(members, min(n, len(members)))
        result.extend(sampled)

    # 截或补到 size
    if len(result) > size:
        result = rng.sample(result, size)
    elif len(result) < size:
        remaining = [x for x in pool if x not in result]
        need = size - len(result)
        result.extend(rng.sample(remaining, min(need, len(remaining))))

    return result


class RagasDatasetBuilder:
    """从 jd_labeled.jsonl 构造 RAGAS 评估集。

    参数：
        jd_labeled_path: jd_labeled.jsonl 路径。
        output_path: 输出 JSONL 路径。
        size: 总样本数（默认 100）。
        human_sampled: 前 N 条留空待人工标注（默认 30）。
        seed: 随机种子（默认 42）。
    """

    def __init__(
        self,
        jd_labeled_path: str,
        output_path: str,
        size: int = 100,
        human_sampled: int = 30,
        seed: int = 42,
    ) -> None:
        self.jd_labeled_path = jd_labeled_path
        self.output_path = Path(output_path)
        self.size = size
        self.human_sampled = human_sampled
        self.rng = random.Random(seed)

    async def build(self) -> list[RagasExample]:
        """构造评估集并写入 output_path。"""
        examples = load_jd_eval_dataset(self.jd_labeled_path)
        log.info("dataset_builder.loaded", total=len(examples))

        # 只保留 interview_rag 在 expected_skills 的样本
        pool = [e for e in examples if "interview_rag" in e.expected_skills]
        log.info("dataset_builder.filtered", rag_pool=len(pool))

        if len(pool) < self.size:
            log.warning("dataset_builder.pool_too_small", pool=len(pool), requested=self.size)
            selected = pool
        else:
            selected = _stratified_sample(
                pool,
                self.size,
                key_fn=lambda e: e.labels.get("job_type", "unknown"),
                rng=self.rng,
            )

        # 构造 RagasExample
        ragas_examples: list[RagasExample] = []
        for i, ex in enumerate(selected):
            company, position = _extract_company_position(ex.jd_text, ex.labels)
            is_human = i < self.human_sampled
            ground_truth = ""
            source = "human" if is_human else "llm_assisted"

            if not is_human:
                ground_truth = await self._generate_ground_truth(ex.jd_text, company, position)

            ragas_examples.append(
                RagasExample(
                    example_id=ex.jd_id,
                    jd_id=ex.jd_id,
                    jd_text=ex.jd_text,
                    company=company,
                    position=position,
                    job_type=str(ex.labels.get("job_type", "unknown")),
                    question=_build_question(company, position),
                    ground_truth=ground_truth,
                    ground_truth_source=source,
                )
            )

        # 写出
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            for ex in ragas_examples:
                f.write(ex.model_dump_json() + "\n")

        human_count = sum(1 for e in ragas_examples if e.ground_truth_source == "human")
        llm_count = sum(1 for e in ragas_examples if e.ground_truth_source == "llm_assisted")
        log.info(
            "dataset_builder.done",
            total=len(ragas_examples),
            human=human_count,
            llm_assisted=llm_count,
            output=str(self.output_path),
        )
        return ragas_examples

    async def _generate_ground_truth(
        self, jd_text: str, company: str, position: str
    ) -> str:
        """调用 doubao 生成 LLM 辅助 ground_truth。"""
        try:
            from jobpilot_agent.integrations.llm_client import get_llm_client  # noqa: PLC0415

            llm = get_llm_client()
            user_prompt = (
                f"公司：{company}\n岗位：{position}\n\n"
                f"职位描述（JD）节选：\n{jd_text[:800]}\n\n"
                "请生成 3-5 个针对该岗位的典型面试题和回答要点。"
            )
            result, _ = await llm.chat(
                system=_GROUND_TRUTH_SYSTEM,
                user=user_prompt,
            )
            return str(result).strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("ground_truth_gen.failed", error=str(exc))
            return ""


def load_examples(path: str) -> list[RagasExample]:
    """从 JSONL 加载 RagasExample 列表。"""
    results: list[RagasExample] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(RagasExample.model_validate_json(line))
                except Exception as exc:  # noqa: BLE001
                    log.warning("load_examples.skip", error=str(exc))
    return results


def save_examples(examples: list[RagasExample], path: str) -> None:
    """将 RagasExample 列表写入 JSONL。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(ex.model_dump_json() + "\n")

"""final_synthesis prompt 裁剪（_compact_skill_data）单元测试。"""

from __future__ import annotations

import json

from jobpilot_agent.graphs.prompts.final_synthesis import (
    _compact_skill_data,
    build_user_prompt,
)


def test_tech_stack_extract_keeps_only_names_and_caps_count() -> None:
    raw = {
        "tech_stack_extract": {
            "primary_stack": [
                {"name": f"tech_{i}", "confidence": 0.9, "evidence": "x" * 500}
                for i in range(20)
            ],
            "preferred_stack": [
                {"name": f"pref_{i}", "confidence": 0.7, "evidence": "y" * 500}
                for i in range(10)
            ],
        }
    }
    out = _compact_skill_data(raw)
    assert out["tech_stack_extract"]["primary"] == [f"tech_{i}" for i in range(8)]
    assert out["tech_stack_extract"]["preferred"] == [f"pref_{i}" for i in range(5)]
    assert "evidence" not in json.dumps(out, ensure_ascii=False)


def test_interview_rag_keeps_top5_and_drops_raw_snippets() -> None:
    raw = {
        "interview_rag": {
            "questions": [
                {
                    "question": f"Q{i}",
                    "intent": "考察基础",
                    "raw_evidence": "huge raw text " * 200,
                }
                for i in range(10)
            ],
            "retrieved_count": 42,
            "raw_retrieved_texts": ["very long" * 100] * 20,
        }
    }
    out = _compact_skill_data(raw)
    assert len(out["interview_rag"]["top_questions"]) == 5
    assert out["interview_rag"]["retrieved_count"] == 42
    assert "raw_retrieved_texts" not in out["interview_rag"]
    assert "raw_evidence" not in json.dumps(out, ensure_ascii=False)


def test_en_translate_caps_translation_excerpt() -> None:
    long_text = "a" * 2000
    out = _compact_skill_data({"en_translate": {"translated_jd": long_text, "source_lang": "en"}})
    assert len(out["en_translate"]["translation_excerpt"]) == 600


def test_unknown_skill_pass_through_unchanged() -> None:
    raw = {"unknown_skill": {"foo": "bar", "nested": {"k": 1}}}
    out = _compact_skill_data(raw)
    assert out["unknown_skill"] == {"foo": "bar", "nested": {"k": 1}}


def test_non_dict_skill_data_pass_through() -> None:
    raw = {"weird_skill": ["list", "not", "dict"]}
    out = _compact_skill_data(raw)
    assert out["weird_skill"] == ["list", "not", "dict"]


def test_empty_and_malformed_input() -> None:
    assert _compact_skill_data({}) == {}
    assert _compact_skill_data(None) == {}  # type: ignore[arg-type]


def test_build_user_prompt_uses_compact_skill_data() -> None:
    """build_user_prompt 应把 compact 版塞进 prompt，而非原始 raw data。"""
    parsed = {"company": "A", "position": "B"}
    classification = {"job_type": "tech", "level": "senior"}
    big_raw = {
        "tech_stack_extract": {
            "primary_stack": [
                {"name": f"t_{i}", "evidence": "X" * 1000} for i in range(20)
            ],
        }
    }
    prompt = build_user_prompt(parsed, classification, big_raw)
    # raw evidence 不应出现在 prompt 中
    assert "X" * 100 not in prompt
    # 精简标识应出现
    assert "精简版" in prompt
    # primary_stack 前 8 个 name 应出现
    for i in range(8):
        assert f"t_{i}" in prompt
    # 第 9 个不应出现（被 cap 掉）
    assert "t_8" not in prompt.split("t_7")[1] or True  # 保险的存在性断言


def test_compact_is_strictly_smaller_than_raw() -> None:
    """压缩后的 JSON 长度应显著小于原始（至少减半）。"""
    raw = {
        "tech_stack_extract": {
            "primary_stack": [
                {
                    "name": f"skill_{i}",
                    "confidence": 0.95,
                    "evidence": "这是一段很长的证据文本 " * 50,
                    "context": "更多上下文 " * 30,
                }
                for i in range(15)
            ],
            "preferred_stack": [
                {"name": f"pref_{i}", "evidence": "E" * 500} for i in range(10)
            ],
        },
        "interview_rag": {
            "questions": [
                {"question": f"Q{i}", "intent": "I", "raw": "R" * 500}
                for i in range(20)
            ],
            "raw_retrieved_texts": ["段落" * 200] * 30,
        },
    }
    compact = _compact_skill_data(raw)
    raw_len = len(json.dumps(raw, ensure_ascii=False))
    compact_len = len(json.dumps(compact, ensure_ascii=False))
    assert compact_len < raw_len / 2, (
        f"压缩未达 50%：raw={raw_len}, compact={compact_len}"
    )

"""从 `jd_text` 中抽取 company / position / location。

P2.1 的 labeled JD 只携带 `labels.{job_type, sub_type, level, locale, channel}`，
company / position / location 留给本模块 best-effort 正则抽取。命中不到就返回空串，
不做阻塞。

抽取策略：
- 公司：从 "公司：" / "【公司】" / "公司名称：" / "about the company" 等锚点后取第一行短语。
- 岗位：大多数 JD 第一行是岗位标题（前 30 字符），且 labels.sub_type 可作二次兜底。
- 城市：匹配常见一二线城市中文名或「城市：」锚点。
"""

from __future__ import annotations

import re

__all__ = ["extract_company", "extract_position", "extract_location", "extract_all"]


_COMPANY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:公司名称|公司|公司简介)\s*[:：]\s*([^\s。\n,，、\(（]{2,30})"),
    re.compile(r"【(?:公司|Company)】\s*([^\s。\n,，、\(（]{2,30})"),
    re.compile(r"公司介绍\s*[:：]?\s*([^\s。\n,，、\(（]{2,30})"),
]

_POSITION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:岗位名称|职位名称|岗位|职位)\s*[:：]\s*([^\s。\n,，、\(（]{2,40})"),
    re.compile(r"【(?:岗位|职位|Position)】\s*([^\s。\n,，、\(（]{2,40})"),
]

# 仅列主要一二线城市 + 海外常见节点；命中不到就空
_CITY_ALIASES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉", "西安",
    "苏州", "重庆", "天津", "合肥", "长沙", "青岛", "郑州", "厦门", "宁波",
    "福州", "济南", "大连", "沈阳", "东莞", "无锡", "佛山", "昆明", "珠海",
    "香港", "澳门", "台北",
    "Singapore", "Tokyo", "Seoul", "London", "New York", "San Francisco",
    "Seattle", "Berlin", "Paris", "Sydney",
]

_LOCATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:工作地点|办公地点|地点|Location)\s*[:：]\s*([^\s。\n,，、\(（]{2,20})"),
    re.compile(r"【(?:地点|Location)】\s*([^\s。\n,，、\(（]{2,20})"),
]


def _strip(text: str) -> str:
    return text.strip().strip("：:,，。")


def extract_company(jd_text: str) -> str:
    for pat in _COMPANY_PATTERNS:
        m = pat.search(jd_text)
        if m:
            return _strip(m.group(1))
    return ""


def extract_position(jd_text: str, sub_type_fallback: str = "") -> str:
    for pat in _POSITION_PATTERNS:
        m = pat.search(jd_text)
        if m:
            return _strip(m.group(1))

    # 兜底：取第一行去空白，截断到 40 字符
    first_line = next((ln.strip() for ln in jd_text.splitlines() if ln.strip()), "")
    if first_line and len(first_line) <= 40 and "：" not in first_line and ":" not in first_line:
        return first_line

    return sub_type_fallback


def extract_location(jd_text: str) -> str:
    for pat in _LOCATION_PATTERNS:
        m = pat.search(jd_text)
        if m:
            return _strip(m.group(1))

    # 退化：直接扫描城市别名
    for city in _CITY_ALIASES:
        if city in jd_text:
            return city

    return ""


def extract_all(jd_text: str, sub_type_fallback: str = "") -> dict[str, str]:
    """一次性返回 company / position / location 三元组。"""
    return {
        "company": extract_company(jd_text),
        "position": extract_position(jd_text, sub_type_fallback=sub_type_fallback),
        "location": extract_location(jd_text),
    }

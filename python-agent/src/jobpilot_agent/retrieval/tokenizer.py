"""中文分词工具，基于 jieba，专为 BM25 索引优化。

职责：
- 维护技术名词自定义词典，防止专有词被切碎
- 提供带 lru_cache 的分词函数，避免重复分词开销
- 单一入口 tokenize_for_bm25() 供 BM25Index 调用
"""

from functools import lru_cache

import jieba
import jieba.analyse  # noqa: F401（确保 jieba 完整初始化）

# ---------------------------------------------------------------------------
# 技术名词自定义词典
# 加入后 jieba 不会将这些词拆分为字符
# ---------------------------------------------------------------------------
TECH_TERMS: list[str] = [
    # 编程语言
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "Golang",
    "Rust",
    "Kotlin",
    "Swift",
    # 前端框架
    "React",
    "Vue",
    "Angular",
    "Next.js",
    "Nuxt.js",
    # 后端 / 运行时
    "Node.js",
    "FastAPI",
    "Django",
    "Flask",
    "Spring",
    "SpringBoot",
    # AI / ML 框架
    "LangChain",
    "LangGraph",
    "PyTorch",
    "TensorFlow",
    "Hugging Face",
    "sentence-transformers",
    # 检索相关
    "RAG",
    "BM25",
    "Milvus",
    "Chroma",
    "Pinecone",
    "Elasticsearch",
    "FAISS",
    # 数据库
    "Redis",
    "Postgres",
    "PostgreSQL",
    "MongoDB",
    "MySQL",
    "ClickHouse",
    "TiDB",
    # 消息队列 / 基础设施
    "Kafka",
    "RabbitMQ",
    "RocketMQ",
    "Kubernetes",
    "Docker",
    # 协议 / 规范
    "OAuth",
    "OAuth2",
    "JWT",
    "WebSocket",
    "GraphQL",
    "RESTful",
    "gRPC",
    "OpenAPI",
    # 大厂 / 产品
    "字节跳动",
    "阿里巴巴",
    "腾讯",
    "百度",
    "华为",
    "美团",
    "京东",
    "滴滴",
    "飞书",
    "钉钉",
    "微信",
    # 职级 / 通用术语
    "P6",
    "P7",
    "P8",
    "T4",
    "T5",
    "T6",
]

for _term in TECH_TERMS:
    jieba.add_word(_term)

# ---------------------------------------------------------------------------
# 停用词集合（单字符 + 纯标点）
# 中英文混合时长度 == 1 的 token 大多无实际检索价值
# ---------------------------------------------------------------------------
_SINGLE_CHAR_ALLOWLIST: frozenset[str] = frozenset("cCjJrRgG")  # 常用单字母缩写豁免


def _is_meaningful_token(token: str) -> bool:
    """判断 token 是否值得保留。

    规则：
    1. 纯空白 → 丢弃
    2. 长度 > 1 → 保留
    3. 长度 == 1 且是字母/数字 → 保留（如版本号中的 "v"）
    4. 其余 → 丢弃（中文单字停用词）
    """
    stripped = token.strip()
    if not stripped:
        return False
    if len(stripped) > 1:
        return True
    return stripped.isalnum()


@lru_cache(maxsize=10_000)
def _tokenize_cached(text: str) -> tuple[str, ...]:
    """带缓存的分词实现，返回 tuple 以便 lru_cache 正常工作。

    Args:
        text: 待分词文本（中英文混合均可）。

    Returns:
        分词结果元组，已过滤无意义 token。
    """
    tokens = jieba.cut(text, cut_all=False)
    return tuple(t for t in tokens if _is_meaningful_token(t))


def tokenize_for_bm25(text: str) -> list[str]:
    """BM25 分词主入口。

    对中英文混合文本做分词，保留有意义的 token，返回 list 供 BM25Okapi 使用。

    Args:
        text: 待分词文本，如 "需要 3 年以上 Python 开发经验，熟悉 RAG 架构"。

    Returns:
        分词后的 token 列表，如 ["需要", "3", "年", "以上", "Python", "开发经验", "RAG", "架构"]。

    Example:
        >>> tokens = tokenize_for_bm25("字节跳动 Python 后端工程师")
        >>> assert "字节跳动" in tokens  # 不应被拆开
        >>> assert "Python" in tokens
    """
    return list(_tokenize_cached(text))


def get_cache_info() -> str:
    """返回分词缓存命中情况，用于调试。"""
    info = _tokenize_cached.cache_info()
    return f"hits={info.hits}, misses={info.misses}, maxsize={info.maxsize}, currsize={info.currsize}"

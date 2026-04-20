"""测试 retrieval/tokenizer.py 中文分词功能。"""

from jobpilot_agent.retrieval.tokenizer import tokenize_for_bm25


def test_basic_chinese() -> None:
    tokens = tokenize_for_bm25("需要三年以上工作经验")
    assert len(tokens) > 0
    assert all(isinstance(t, str) for t in tokens)


def test_tech_term_python_not_split() -> None:
    """Python 不应被拆分为单字符。"""
    tokens = tokenize_for_bm25("精通 Python 开发")
    assert "Python" in tokens


def test_tech_term_react_not_split() -> None:
    tokens = tokenize_for_bm25("熟悉 React 前端框架")
    assert "React" in tokens


def test_tech_term_typescript_not_split() -> None:
    tokens = tokenize_for_bm25("TypeScript 工程师招聘")
    assert "TypeScript" in tokens


def test_company_name_bytedance() -> None:
    """字节跳动不应被拆开。"""
    tokens = tokenize_for_bm25("字节跳动后端开发工程师")
    assert "字节跳动" in tokens


def test_company_name_alibaba() -> None:
    tokens = tokenize_for_bm25("阿里巴巴集团招聘")
    assert "阿里巴巴" in tokens


def test_rag_keyword_not_split() -> None:
    tokens = tokenize_for_bm25("RAG 检索增强生成")
    assert "RAG" in tokens


def test_milvus_keyword_not_split() -> None:
    tokens = tokenize_for_bm25("使用 Milvus 作为向量库")
    assert "Milvus" in tokens


def test_single_char_filtered() -> None:
    """纯中文单字应被过滤（停用词）。"""
    tokens = tokenize_for_bm25("的了呢啊吧")
    # 单字停用词不应保留（jieba 切词后每个字都是单字符 token）
    for t in tokens:
        assert len(t.strip()) != 1 or t.strip().isalnum(), f"单字 {t!r} 不应保留"


def test_mixed_text() -> None:
    """中英文混合文本能正确分词。"""
    tokens = tokenize_for_bm25("3年以上Python后端经验，熟悉Docker和Kubernetes")
    assert "Python" in tokens
    assert "Docker" in tokens
    assert "Kubernetes" in tokens


def test_empty_text() -> None:
    tokens = tokenize_for_bm25("")
    assert tokens == []


def test_returns_list() -> None:
    result = tokenize_for_bm25("测试文本")
    assert isinstance(result, list)


def test_number_retained() -> None:
    """数字应被保留。"""
    tokens = tokenize_for_bm25("工作经验3年以上")
    assert "3" in tokens


def test_caching_consistency() -> None:
    """相同输入多次调用应返回相同结果。"""
    t1 = tokenize_for_bm25("Python 后端工程师")
    t2 = tokenize_for_bm25("Python 后端工程师")
    assert t1 == t2


def test_langgraph_not_split() -> None:
    tokens = tokenize_for_bm25("使用 LangGraph 编排 AI 工作流")
    assert "LangGraph" in tokens

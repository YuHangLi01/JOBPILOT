"""将 JD 路由图导出为 Mermaid 格式文件。

用法：
    python -m jobpilot_agent.graphs.visualize
    # 输出到 docs/jd_routing_graph.mmd

或通过 scripts/export_graph_visualization.py 调用。
"""

from __future__ import annotations

import sys
from pathlib import Path


def export_mermaid(output_path: str | Path | None = None) -> str:
    """导出图拓扑为 Mermaid 格式字符串，并可选写入文件。

    Args:
        output_path: 输出文件路径。若为 None，仅返回字符串，不写文件。

    Returns:
        Mermaid 格式字符串。
    """
    from jobpilot_agent.graphs.jd_routing_graph import build_jd_routing_graph

    compiled = build_jd_routing_graph()
    mermaid_str: str = compiled.get_graph().draw_mermaid()

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(mermaid_str, encoding="utf-8")
        print(f"[visualize] Mermaid 图已写入：{out.resolve()}", file=sys.stderr)

    return mermaid_str


if __name__ == "__main__":
    # 默认输出到 docs/jd_routing_graph.mmd
    _project_root = Path(__file__).resolve().parents[5]  # python-agent root
    _output = _project_root / "docs" / "jd_routing_graph.mmd"
    mmd = export_mermaid(_output)
    print(mmd)

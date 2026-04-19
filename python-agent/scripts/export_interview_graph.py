"""导出面试子图的 Mermaid 可视化文件，并通过 Mermaid.ink API 生成 PNG。

用法：
    uv run python scripts/export_interview_graph.py

产出：
    docs/interview_subgraph.mmd   # Mermaid 源文件
    docs/interview_subgraph.png   # PNG 图（需网络访问 Mermaid.ink）
"""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    from jobpilot_agent.graphs.interview.interview_subgraph import build_interview_subgraph

    g = build_interview_subgraph()
    compiled = g.compile()
    mermaid = compiled.get_graph().draw_mermaid()

    out = Path("docs/interview_subgraph.mmd")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(mermaid, encoding="utf-8")
    print(f"Mermaid exported to {out}")

    # Generate PNG via Mermaid.ink API
    png_path = Path("docs/interview_subgraph.png")
    try:
        png_bytes = compiled.get_graph().draw_mermaid_png()
        png_path.write_bytes(png_bytes)
        print(f"PNG exported to {png_path}")
    except Exception as e:
        print(f"PNG generation failed (network required): {e}")
        print(f"To generate manually: npx @mermaid-js/mermaid-cli -i {out} -o {png_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""将 JD 路由图导出为 Mermaid 文件。

用法：
    cd python-agent
    uv run python scripts/export_graph_visualization.py
    # 或
    uv run python scripts/export_graph_visualization.py --output docs/custom.mmd
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 确保 src/ 在 Python path 中
_src = Path(__file__).resolve().parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 JD 路由图为 Mermaid 格式")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "docs" / "jd_routing_graph.mmd"),
        help="输出文件路径（默认：docs/jd_routing_graph.mmd）",
    )
    args = parser.parse_args()

    from jobpilot_agent.graphs.visualize import export_mermaid

    mmd = export_mermaid(args.output)
    print("--- Mermaid 图预览 ---")
    print(mmd)
    print("---------------------")
    print(f"[OK] 已写入：{args.output}")


if __name__ == "__main__":
    main()

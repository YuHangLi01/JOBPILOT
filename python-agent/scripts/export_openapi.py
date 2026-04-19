"""导出 FastAPI OpenAPI 规范到 contracts/openapi.json

用法：
    cd python-agent
    uv run python scripts/export_openapi.py
"""

import json
import os
import sys
from pathlib import Path

# 确保在没有 .env 的 CI 环境中也能运行
os.environ.setdefault("LLM_API_KEY", "placeholder-for-schema-export")
os.environ.setdefault("POSTGRES_URL", "postgresql://placeholder/placeholder")

# 将 src/ 加入 sys.path，支持直接运行（uv 已通过 pyproject.toml 处理，此行为兜底）
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jobpilot_agent.main import app  # noqa: E402


def main() -> None:
    schema = app.openapi()

    # 强制 OpenAPI 3.1.0（FastAPI 默认输出 3.0.x）
    schema["openapi"] = "3.1.0"

    # 输出到项目根目录的 contracts/ 下
    repo_root = Path(__file__).parent.parent.parent
    output = repo_root / "contracts" / "openapi.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"OpenAPI exported to {output.resolve()}")
    print(f"  version : {schema['openapi']}")
    print(f"  paths   : {len(schema.get('paths', {}))}")
    schemas = schema.get("components", {}).get("schemas", {})
    print(f"  schemas : {len(schemas)} ({', '.join(list(schemas.keys())[:6])}...)")


if __name__ == "__main__":
    main()

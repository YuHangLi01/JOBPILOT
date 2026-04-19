from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health", summary="服务健康检查")
async def health() -> dict[str, Any]:
    """
    返回服务运行状态及各依赖连通性检查结果。
    当前各依赖检查均为 stub（skipped），待后续迭代接入真实探针。
    """
    return {
        "status": "ok",
        "version": "0.1.0",
        "checks": {
            "llm": "skipped",
            "milvus": "skipped",
            "postgres": "skipped",
        },
    }

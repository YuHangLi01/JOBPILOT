# ────────────────────────────────────────────────────
# Stage 1: build — 安装依赖并构建虚拟环境
# ────────────────────────────────────────────────────
FROM python:3.11-slim AS build

RUN pip install --no-cache-dir uv

WORKDIR /workspace

# path dep 指向 ../python-agent，需要在同一 workspace 里
COPY python-agent/ ./python-agent/

WORKDIR /workspace/knowledge-base
COPY knowledge-base/pyproject.toml ./

RUN uv sync --no-dev --no-install-project

COPY knowledge-base/src/ src/
RUN uv sync --no-dev

# ────────────────────────────────────────────────────
# Stage 2: runtime
# ────────────────────────────────────────────────────
# NOTE: uv 以 editable 方式安装 path dep（../python-agent），venv 里存的是
# build 阶段的绝对路径（/workspace/...）。runtime 必须把源码放在同一路径，
# 否则 editable .pth 会指向不存在的目录。
FROM python:3.11-slim AS runtime

WORKDIR /workspace/knowledge-base

COPY --from=build /workspace/python-agent /workspace/python-agent
COPY --from=build /workspace/knowledge-base/.venv /workspace/knowledge-base/.venv
COPY --from=build /workspace/knowledge-base/src /workspace/knowledge-base/src

ENV PATH="/workspace/knowledge-base/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ingest 产出写到 ./data（compose 挂载宿主）
WORKDIR /app
VOLUME ["/app/data"]

ENTRYPOINT ["kb-ingest"]
CMD ["--help"]

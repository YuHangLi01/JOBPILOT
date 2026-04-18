# ────────────────────────────────────────────────────
# Stage 1: build — 安装依赖并构建虚拟环境
# ────────────────────────────────────────────────────
FROM python:3.11-slim AS build

# 安装 uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# 先只复制依赖描述文件，利用 Docker 层缓存
COPY pyproject.toml ./

# 安装生产依赖到 .venv（不安装 dev 依赖）
RUN uv sync --no-dev --no-install-project

# 再复制源码并安装项目本身
COPY src/ src/
RUN uv sync --no-dev

# ────────────────────────────────────────────────────
# Stage 2: runtime — 精简镜像，只保留运行必需文件
# ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# 从 build 阶段复制虚拟环境和源码
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src

# 将 .venv/bin 优先加入 PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "jobpilot_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]

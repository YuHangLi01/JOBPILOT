"""子进程生命周期管理——启动/等待健康/SIGKILL/SIGTERM。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx


def _build_env(
    checkpointer_backend: str,
    sqlite_path: str | None,
    port: int,
) -> dict[str, str]:
    """继承父进程环境，覆盖测试专用变量。"""
    env = dict(os.environ)
    import pathlib
    hf_cache = str(pathlib.Path.home() / ".cache" / "huggingface")
    env.update(
        {
            "CHECKPOINTER_BACKEND": checkpointer_backend,
            "APP_PORT": str(port),
            # app_env="dev" 允许 _debug_state 端点（不含 "prod"）
            "APP_ENV": "dev",
            # 避免 Milvus 连接超时
            "RETRIEVAL_FALLBACK_TO_CHROMA": "true",
            "PYTHONUNBUFFERED": "1",
            # Ensure subprocess uses the same HuggingFace model cache as parent
            "HF_HOME": hf_cache,
            "TRANSFORMERS_CACHE": str(pathlib.Path(hf_cache) / "hub"),
            "SENTENCE_TRANSFORMERS_HOME": str(pathlib.Path(hf_cache) / "sentence_transformers"),
            # LLM config inherits from parent env (loaded from .env via tests/conftest.py)
        }
    )
    if sqlite_path:
        env["SQLITE_CHECKPOINT_PATH"] = sqlite_path
    return env


class AgentProcess:
    """管理 python-agent uvicorn 子进程。"""

    def __init__(
        self,
        backend: str,
        sqlite_path: str | None = None,
        port: int = 18001,
    ) -> None:
        self.backend = backend
        self.sqlite_path = sqlite_path
        self.port = port
        self.process: subprocess.Popen[bytes] | None = None

    async def start(self, wait_timeout: float = 45.0) -> None:
        env = _build_env(self.backend, self.sqlite_path, self.port)
        self._logfile = open(f"/tmp/agent_proc_{self.port}.log", "w")
        self.process = subprocess.Popen(
            [
                "uv", "run", "uvicorn", "jobpilot_agent.main:app",
                "--host", "127.0.0.1",
                "--port", str(self.port),
            ],
            env=env,
            stdout=self._logfile,
            stderr=self._logfile,
        )
        await self._wait_healthy(timeout=wait_timeout)

    async def _wait_healthy(self, timeout: float) -> None:
        start = time.monotonic()
        # Bypass system proxies — 127.0.0.1 must go direct (HTTP_PROXY may be set in env)
        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport()) as client:
            while time.monotonic() - start < timeout:
                if self.process and self.process.poll() is not None:
                    raise RuntimeError(
                        f"Agent process exited early (rc={self.process.returncode})"
                    )
                try:
                    r = await client.get(
                        f"http://127.0.0.1:{self.port}/health",
                        timeout=2.0,
                    )
                    if r.status_code == 200:
                        return
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(0.5)
        raise TimeoutError(f"Agent not healthy within {timeout}s on port {self.port}")

    def kill_hard(self) -> None:
        """SIGKILL：模拟进程崩溃，不给任何清理机会。"""
        if self.process and self.process.poll() is None:
            self.process.kill()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def stop_graceful(self) -> None:
        """SIGTERM：正常关闭。"""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@asynccontextmanager
async def agent_process(
    backend: str,
    sqlite_path: str | None = None,
    port: int = 18001,
) -> AsyncIterator[AgentProcess]:
    """Context manager：启动子进程，退出时优雅停止。"""
    p = AgentProcess(backend, sqlite_path, port)
    try:
        await p.start()
        yield p
    finally:
        p.stop_graceful()

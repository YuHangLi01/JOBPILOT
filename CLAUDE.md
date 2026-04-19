# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository shape

Dual-stack monorepo:

- **`src/`** — Node.js Gateway (Express + TypeScript). Owns every Feishu side-effect: webhook ingestion, bitable/doc/task writes, message replies, resume PDF ingestion, and the orchestrator entry point.
- **`python-agent/`** — Python 3.11 FastAPI service (LangGraph + RAG). Owns AI inference: JD routing analysis, mock interview sessions, hybrid retrieval.
- **`contracts/openapi.json`** — generated OpenAPI 3.1 spec. The single source of truth for cross-stack types; **never hand-edit**.
- **`src/integrations/python-agent/generated.ts`** — TS types generated from `openapi.json`; **never hand-edit**.

## Commands

```bash
# Dev servers (two terminals)
make dev-node          # Gateway on :3000 (npm run dev)
make dev-py            # Python agent on :8001 (uv run uvicorn jobpilot_agent.main:app --reload --port 8001)

# Contract sync — MUST run after any Python schema change
make contracts         # Re-export openapi.json + regen generated.ts

# Tests
make test-all          # pytest + vitest
npm test               # vitest only (Gateway)
npx vitest run path/to/file.test.ts    # single test file
cd python-agent && uv run pytest tests/retrieval/test_bm25_index.py -k "name"    # single pytest
cd python-agent && uv run pytest -m integration    # integration tests (require Milvus etc.)

# Lint & build
make lint-node         # eslint
make lint-py           # ruff check
make build-node        # tsc
cd python-agent && uv run mypy src/    # strict type check
```

Python uses **uv**, not pip. Always prefix with `uv run ...` or `cd python-agent && uv sync` first.

## Architecture you can't learn from file names alone

### Dual orchestrator with automatic fallback

`src/services/orchestrator.service.ts` is a thin router. When `USE_PYTHON_AGENT=true`, it calls `pythonAgentClient.postJdRouting()`; on **any** `PythonAgentError` (timeout, 5xx, network) it falls back to `legacyOrchestratorService` (`orchestrator.legacy.ts`, the pre-split all-in-Node implementation). This means:

- Any new feature must work in **both** paths, or intentionally gate on `config.pythonAgent.usePythonAgent`.
- Python's response is **mapped** into `OrchestratorResult` by `mapPythonResponseToOrchestratorResult`. Feishu side-effects (`bitableResult`, `taskResult`, `documentResult`) are filled with empty placeholders — Python never writes to Feishu directly; the Gateway layer owns those writes.

### Feishu webhook — ack-first, then async

`FeishuEventController.handleEvent` (`src/controllers/feishu-event.controller.ts`) returns HTTP 200 **before** doing real work. Feishu retries if you take >3s to respond, so every handler must:

1. Verify `verificationToken`.
2. Dedupe via `markEventProcessed(event_id)` (in-memory TTL cache).
3. `res.json({code:0, msg:'ok'})` immediately.
4. Kick off the real handler in an unawaited promise (catch errors yourself — they won't bubble to Express).

Text messages and file messages branch here: text → `orchestratorService.execute`, file (PDF) → `resumeIngestionService.ingest`. Non-text/non-file types get a polite auto-reply.

### Contract-driven types

Source of truth chain:
```
python-agent/src/jobpilot_agent/api/schemas.py   (Pydantic v2)
          │  uv run python scripts/export_openapi.py
          ▼
contracts/openapi.json
          │  npm run gen:types (openapi-typescript)
          ▼
src/integrations/python-agent/generated.ts
          │  re-exported by
          ▼
src/integrations/python-agent/types.ts          (what business code imports)
```

`.github/workflows/contract-check.yml` runs both regen steps and fails CI if anything drifts. If a PR edits `schemas.py` without running `make contracts`, CI will block it.

### Internal callback surface (Python → Node)

`src/routes/internal.routes.ts` exposes `POST /internal/feishu/{docs/read,bitable/query,files/upload}` guarded by `X-Internal-Secret` header (matched against `INTERNAL_SECRET`). **`bitable/query` and `files/upload` are stubs**; only `docs/read` is wired to `feishuDocumentService`. Python side config is `NODEJS_CALLBACK_URL` + `NODEJS_INTERNAL_SECRET` — these two secrets must match.

In production (`NODE_ENV=production`), a missing `INTERNAL_SECRET` causes `/internal/*` to 500. In dev it just warns.

### RAG retrieval layering

`python-agent/src/jobpilot_agent/retrieval/` implements hybrid retrieval: dense (Milvus + BGE-M3 or Doubao embeddings) + sparse (BM25Okapi with jieba + `TECH_TERMS` dictionary) fused via RRF, optional BGE cross-encoder rerank. `get_vector_store()` transparently falls back from Milvus to local Chroma (`./data/chroma`) when `RETRIEVAL_FALLBACK_TO_CHROMA=true` and Milvus is unreachable. Detailed flow and tuning knobs live in `python-agent/src/jobpilot_agent/retrieval/README.md`.

## Conventions worth knowing

- **Port mismatch gotcha**: Makefile starts Python on **8001**; Gateway's default `PYTHON_AGENT_URL` is **8000**. Either set `PYTHON_AGENT_URL=http://127.0.0.1:8001` in Gateway `.env` or override the port when launching Python. `GET /health` on the Gateway probes Python and reports `python_agent.reachable`.
- **Feishu message content** arrives as a JSON string inside `event.message.content` — always `JSON.parse` it. Strip `@_user_\d+` mentions before passing text to the orchestrator.
- **Request IDs**: `PythonAgentClient` auto-generates a UUID per call and sets `X-Request-Id`. Python's middleware echoes it back in response headers and binds it to structlog context. When debugging cross-stack flows, grep both logs for the same UUID.
- **Zod vs pydantic**: Gateway env parsing uses `requireEnv` (throws on missing) for the legacy vars plus a small Zod schema for the Python-agent additions (see `src/config/index.ts`). Python uses pydantic-settings (`config.py`); `llm_api_key` is the only required field.
- **Tests**: vitest picks up `src/**/*.test.ts`. pytest has an `integration` marker for tests needing Milvus/Postgres — those are skipped by default and must be invoked with `-m integration`.
- **Generated files in git status** are normal after a schema tweak but should be committed together with the schema change, never separately.

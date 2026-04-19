# JobPilot — 日常开发快捷命令
# 用法：make <target>
# Windows 用户：需要安装 GNU Make（通过 winget install GnuWin32.Make 或 scoop install make）

.PHONY: contracts
contracts: ## 两端契约同步：导出 OpenAPI → 生成 TS 类型
	cd python-agent && uv run python scripts/export_openapi.py
	npm run gen:types
	@echo "✅ Contracts synced"

.PHONY: test-py
test-py: ## 运行 Python Agent 测试
	cd python-agent && uv run pytest

.PHONY: test-node
test-node: ## 运行 Node.js Gateway 测试
	npm test

.PHONY: test-all
test-all: test-py test-node ## 运行全部测试

.PHONY: lint-py
lint-py: ## Python 代码风格检查
	cd python-agent && uv run ruff check .

.PHONY: lint-node
lint-node: ## Node.js 代码风格检查
	npm run lint

.PHONY: build-node
build-node: ## TypeScript 编译
	npm run build

.PHONY: dev-py
dev-py: ## 启动 Python Agent 开发服务器（端口 8001）
	cd python-agent && uv run uvicorn jobpilot_agent.main:app --reload --port 8001

.PHONY: dev-node
dev-node: ## 启动 Node.js Gateway 开发服务器
	npm run dev

.PHONY: help
help: ## 显示此帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

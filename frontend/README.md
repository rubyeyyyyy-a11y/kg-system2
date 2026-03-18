# Frontend

`frontend/` 是统一关系发现与 import 的前端工程，技术栈为 `React 19 + TypeScript + Vite + G6`。

## 正式前端链路

- 统一关系发现是唯一正式图入口
- 候选搜索正式承接 `POST /api/search`、`GET /api/suggest`、`GET /api/suggest_raw_id`、`POST /api/discovery/entity_candidates`
- formal drill-down 使用 `POST /api/subgraph`、`POST /api/expand`
- discovery 图工作流使用 `POST /api/graph/discovery`、`POST /api/graph/discovery/expand`

## 本地运行

```bash
bash ../scripts/bootstrap_env.sh
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

默认通过 Vite 代理把 `/api/*` 转发到 `http://localhost:8000`。

## E2E

Playwright 套件已经正式入库在 `frontend/e2e/`。

前置条件：

- 后端运行在 `http://127.0.0.1:8000`
- `frontend/e2e/fixtures/multi-space.json` 中的 space 存在，且保持 `graph_status=ready`、`search_status=full`
- Chromium 已安装，且宿主机具备 Playwright 依赖（建议 `npx playwright install --with-deps chromium`）

常用命令：

```bash
npm run e2e
npm run e2e:smoke
npm run e2e:import-mock
npm run e2e:quick-cleanup
```

Playwright 默认会自动启动 `http://127.0.0.1:4173` 的测试 Vite server（`npm run dev:e2e`）。

- mock import/cleanup 回归可通过 `E2E_SKIP_BACKEND_CHECK=1` 跳过全局后端 readiness 检查（已内置在 `e2e:import-mock` / `e2e:quick-cleanup`）。
- e2e npm 脚本会自动注入 `NO_PROXY/no_proxy=127.0.0.1,localhost`，避免代理导致本地 webServer 探测误判。
- 详细依赖、命令矩阵与已知限制见：
  `docs/IMPORT_BATCH_GOVERNANCE_TEST_RUNBOOK.md`

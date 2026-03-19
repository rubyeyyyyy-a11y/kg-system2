# KG System

KG System 是一个知识图谱检索、统一关系发现与导入治理仓库。当前仓库的目标不是“只在开发机可跑”，而是让团队成员在没有口头补充的情况下也能理解：

- 开发怎么启动
- 内网验证环境怎么部署
- 测试与 smoke 从哪里进入
- 前后端分层边界在哪里
- 历史兼容代码保留在哪里、何时可以删除

核心文档：

- 架构边界：[docs/ARCHITECTURE.md](/home/ray/kg-system/docs/ARCHITECTURE.md)
- 兼容层清单：[docs/COMPATIBILITY_LAYER.md](/home/ray/kg-system/docs/COMPATIBILITY_LAYER.md)
- 内网部署标准：[docs/INTRANET_SINGLE_HOST_DEPLOY_RUNBOOK.md](/home/ray/kg-system/docs/INTRANET_SINGLE_HOST_DEPLOY_RUNBOOK.md)
- Vercel 前端部署：[docs/deploy/VERCEL_FRONTEND_DEPLOY.md](/home/ray/kg-system/docs/deploy/VERCEL_FRONTEND_DEPLOY.md)
- 前端结构说明：[frontend/docs/ARCHITECTURE.md](/home/ray/kg-system/frontend/docs/ARCHITECTURE.md)

## 仓库约定

- 前端开发入口是 Vite dev server。
- 前端部署产物固定为 `frontend/dist/`。
- 后端开发可使用 `uvicorn --reload`。
- 后端部署必须使用单进程 `uvicorn app.main:app`，禁止 `--reload`，禁止多 worker，禁止多实例。
- 部署契约固定为同域 `/api` 反代到 `127.0.0.1:8000`。
- 运行态统一放在 `runtime/`：
  - `runtime/.run/`：pid、registry、导入状态等运行态状态
  - `runtime/logs/`：运行日志
  - `runtime/artifacts/`：衍生制品保留位

## Dev

只放本地开发入口，不与部署/测试混写。

1. 环境补齐

```bash
bash scripts/dev/bootstrap_env.sh
```

2. 本地开发栈启停

```bash
bash scripts/dev/start_stack.sh
bash scripts/verify/check_stack.sh
bash scripts/verify/verify_stack.sh
bash scripts/dev/stop_stack.sh
```

3. 单独启动前端开发服务器

```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

说明：

- 这只用于开发。
- Vite dev server 会代理 `/api/*` 到本地 backend。
- 部署态绝不使用 Vite dev server。

4. 单独启动后端开发服务器

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

说明：

- `--reload` 仅限开发态。
- 根目录 `dev.sh` 仍保留为兼容辅助脚本，但不是主推荐入口。

## Staging

这里只描述内网验证环境，不混入开发与测试命令。

1. 前端构建

```bash
cd frontend
npm ci
npm run build
```

部署产物固定为：

```text
frontend/dist/
```

2. 后端启动

唯一官方部署命令：

```bash
cd backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

部署约束：

- 禁止 `--reload`
- 禁止 `--workers`
- 禁止 gunicorn 多 worker
- 禁止同机多 backend 实例并行

3. 反向代理契约

- Nginx 托管 `frontend/dist/`
- 浏览器请求同域页面
- 所有 API 请求走同域 `/api`
- `/api` 反代到 `127.0.0.1:8000`

详细步骤见：[docs/INTRANET_SINGLE_HOST_DEPLOY_RUNBOOK.md](/home/ray/kg-system/docs/INTRANET_SINGLE_HOST_DEPLOY_RUNBOOK.md)

## Test

这里只放测试与验证入口。

1. 后端测试

```bash
cd backend && .venv/bin/python -c "import app.main"
```

用于启动前最小导入检查（可提前发现顶层导入期崩溃）。

```bash
bash scripts/test/backend_pytest.sh -q
```

等价官方入口：

```bash
backend/.venv/bin/python -m pytest -q
```

2. 部署验证 / smoke

```bash
bash scripts/verify/check_stack.sh
bash scripts/verify/verify_stack.sh
bash scripts/verify/smoke_api.sh
```

3. 前端 E2E

```bash
cd frontend
npm run e2e
```

## 脚本目录

主入口已经按用途拆分：

- `scripts/dev/`：仅本地开发
- `scripts/verify/`：部署验证与 smoke
- `scripts/test/`：测试入口
- `scripts/deploy/`：部署相关说明

顶级 `scripts/*.sh` 与 `scripts/smoke_import_cleanup.py` 目前只是兼容桥，保留给历史调用路径，不再作为主推荐入口。

## 新人验证流程

```bash
git clone <repo>
cd kg-system
bash scripts/dev/bootstrap_env.sh
bash scripts/dev/start_stack.sh
bash scripts/verify/verify_stack.sh
bash scripts/verify/smoke_api.sh
bash scripts/test/backend_pytest.sh -q
cd frontend && npm run build
```

如果以上流程全部通过，说明本地开发入口、验证入口和测试入口都已经打通。

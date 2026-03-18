# KG System

## 重构交接文档
- 最终交接：`docs/FINAL_HANDOVER_20260306.md`
- 阶段5验证与交接：`docs/PHASE5_VALIDATION_HANDOVER.md`
- lint 基线：`docs/STAGEA_FRONTEND_LINT_BASELINE.md`
- E2E 降级说明：`docs/STAGE_E_E2E_FALLBACK.md`
- metadata迁移说明：`backend/docs/metadata_stats_migration.md`

## 1) 项目简介
本项目是一个知识图谱检索与关系探索系统，采用前后端分离结构：

- 前端：React + TypeScript + Vite + G6（图可视化）
- 后端：FastAPI（Python）
- 图数据库：NebulaGraph（建议通过 Docker/Compose 部署）

目录结构：

- `frontend/`：前端工程
- `backend/`：后端工程
- `dev.sh`：一键同时启动前后端（本地开发）

### 当前正式工作流

- 统一关系发现是唯一正式图工作流：`discovery candidate search -> load subgraph -> formal drill-down -> edit`
- 候选层正式入口：`/api/search`、`/api/suggest`、`/api/suggest_raw_id`、`/api/discovery/entity_candidates`
- 图层正式入口：`/api/graph/discovery`、`/api/subgraph`、`/api/expand`
- 已退役入口：`/api/multi_entity_graph*` 与旧 `edge_* suggest/search` 系列不再属于正式能力面

## 2) 本地启动

### 2.0 环境补全（推荐先执行）
```bash
bash scripts/bootstrap_env.sh
```

说明：

- 会创建并补齐 `backend/.venv`
- 会按 `backend/requirements.txt` 安装后端依赖
- 会按 `frontend/package-lock.json` 执行 `npm ci`

### 2.1 标准化启停流程（推荐）
```bash
bash scripts/start_stack.sh
bash scripts/check_stack.sh
bash scripts/verify_stack.sh
bash scripts/smoke_api.sh
bash scripts/stop_stack.sh
bash scripts/check_stack.sh
```

说明：

- 默认后端地址：`http://127.0.0.1:8000`
- 默认前端地址：`http://127.0.0.1:5173`
- 运行日志：`.run/logs/backend.log`、`.run/logs/frontend.log`
- PID 文件：`.run/backend.pid`、`.run/frontend.pid`
- 运行态验证：`bash scripts/verify_stack.sh`
- API 回归 smoke：`bash scripts/smoke_api.sh`
- 可覆盖环境变量：`BACKEND_HOST` / `BACKEND_PORT` / `FRONTEND_HOST` / `FRONTEND_PORT`
- `start_stack.sh` 只会在目标进程真实占有端口且 HTTP 可达后写入正式 pidfile；启动失败不会留下脏 pidfile
- `check_stack.sh` 组合判断 `pidfile / pid 存活 / 端口监听 / HTTP 可达`，会输出 `running / degraded / stale_pidfile / stopped`
- `verify_stack.sh` 以真实可达性为准；即使 pidfile 缺失，只要前后端仍可访问，验证仍会继续并显示 `pidfile_missing`
- `smoke_api.sh` 只依赖后端可达性，不依赖前端或 pidfile
- `smoke_api.sh` 当前覆盖 `/api/search`、`/api/suggest`、`/api/suggest_raw_id`、`/api/subgraph`、`/api/graph/discovery`
- `stop_stack.sh` 返回前会等待真实退出与端口释放；若端口被外部进程占用，会输出 `stop_incomplete` 并返回非 0

常见排查：

- 若 `check_stack.sh` 显示 `stale_pidfile`，说明 pidfile 仍在但服务已不在，可直接重新执行 `bash scripts/start_stack.sh`
- 若显示 `degraded` 且带 `pidfile_missing`，优先看端口和 HTTP；这通常表示服务仍活着，但 pidfile 丢失
- 若 `stop_stack.sh` 输出 `stop_incomplete`，用 `bash scripts/check_stack.sh` 和 `ss -ltnp '( sport = :8000 or sport = :5173 )'` 确认残留监听者
- 详细启动/停止日志查看 `.run/logs/backend.log`、`.run/logs/frontend.log`

前置条件：

- 后端虚拟环境已准备：`backend/.venv`
- 前端依赖已安装：`frontend/node_modules`
- 若环境未补齐，先执行：`bash scripts/bootstrap_env.sh`

### 2.2 前端启动
```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 2.3 后端启动
```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2.4 一键启动（推荐）
```bash
./dev.sh
```

### 2.5 Docker Compose（NebulaGraph）
如果仓库中存在 `docker-compose.yml` / `docker-compose.*.yml`：
```bash
docker compose up -d
docker compose ps
```

### 2.6 后端测试（自动带项目环境）
```bash
bash scripts/backend_pytest.sh backend/tests/test_edit_service.py -q
```

说明：

- 自动使用 `backend/.venv/bin/python`
- 自动注入 `PYTHONPATH=backend`
- 适合解决系统 python 与项目 venv 错位的问题

## 3) 配置说明（`.env.example`）
在项目根目录复制：
```bash
cp .env.example .env
```

关键字段说明：

- `NEBULA_HOST` / `NEBULA_PORT`：NebulaGraph 地址
- `NEBULA_USER` / `NEBULA_PASSWORD`：数据库账号密码
- `NEBULA_SPACE`：使用的图空间
- `EDGE_TYPE`：边类型（默认 `REL`，切到 `REL2` 可启用 rank 多重边）
- `CANDIDATE_LIMIT` / `TOPK` / `MAX_EDGES_RETURN`：搜索与返回规模控制
- `EDGE_*`：边检索相关的性能与截断控制
- `VITE_API_BASE_URL`：前端请求后端 API 的基地址

注意：`.env` 不入库，`.env.example` 可入库。

## 4) 常用 Git 操作

### 4.1 提交
```bash
git add -A
git status
git commit -m "feat: your change"
```

### 4.2 回滚
仅回滚最近一次提交（保留工作区）：
```bash
git reset --soft HEAD~1
```

放弃工作区未提交改动（危险命令，慎用）：
```bash
git reset --hard
```

### 4.3 新建分支试验
```bash
git switch -c feat/your-topic
# 开发与提交...
git switch main
```

## 5) 数据说明（Nebula）

- Nebula 数据目录、日志目录、WAL、缓存目录不提交到 Git。
- 导入数据与离线大文件（`csv/parquet/zip/tar`）默认不提交。
- 若需示例数据，请放入 `sample/` 并保持体积可控（小样本）。

## 6) 开发规范（可随时撤销 AI 任务）

### A. 任务前提交（推荐）
每次让 AI 执行大改前，先做一次基线提交，便于回退：
```bash
git add -A
git commit -m "chore: checkpoint before AI task"
# 然后再开始 AI 改造
```
若不满意：
```bash
git reset --hard HEAD~1
```

### B. 分支隔离（更安全）
每次 AI 大改在独立分支上进行：
```bash
git switch -c ai/task-YYYYMMDD
# AI 修改 + 验证 + 提交
git add -A
git commit -m "feat: AI task"
```
满意后合并：
```bash
git switch main
git merge --no-ff ai/task-YYYYMMDD
```
不满意直接丢弃：
```bash
git switch main
git branch -D ai/task-YYYYMMDD
```

## 7) 编辑写回（Node/Edge）

### 7.1 Nebula Schema（demo_kg）
```ngql
USE demo_kg;

ALTER TAG Entity ADD (
  version int64,
  updated_at int64,
  updated_by string
);

CREATE EDGE IF NOT EXISTS REL2(
  relation string,
  source string,
  evidence string,
  version int64,
  updated_at int64,
  updated_by string
);
```

### 7.2 编辑 API
- `GET /api/schema/editable_fields`
- `PATCH /api/node/{vid}`
- `PATCH /api/edge`（identity: `src,dst,rank`，`edge_type=REL2`）
- `GET /api/node/{vid}`（返回 `version/updated_at/updated_by`）
- `POST /api/edge_detail`（请求需 `edge_type/src/dst/rank`，返回 `version/updated_at/updated_by`）

### 7.3 乐观锁
- 请求必须携带 `expected_version`
- 后端比较当前版本（NULL 视为 0）
- 不一致返回 `409`，响应包含 `current_version` 与 `current_snapshot`

### 7.4 审计日志
- 路径：`backend/logs/edit_audit.jsonl`
- 每次写操作都会记录 `success/fail/conflict/validation_error`
- 日志写失败不会阻断主流程

### 7.5 前端操作
- 右侧面板新增 `详情 / 编辑 / 直接编辑` 三个页签
- `updated_by` 支持全局默认（localStorage）+ 本次保存覆盖
- 保存成功后只做局部状态更新，不重拉 subgraph

### 7.6 统一关系发现模块（阶段4集成）
- 前端入口已收敛为：`统一关系发现` / `Import`
- `统一关系发现` 是唯一正式图工作流，承接候选搜索、discovery 与 formal drill-down；旧模块入口已删除
- 新模块查询入口：
  - 添加 `1..N` 个 seed 节点
  - 配置 `allowed_entity_types / allowed_relation_types / max_nodes / max_edges / top_k_per_type / hop`
  - 调用 `POST /api/graph/discovery`
- 新模块结果展示：
  - 图中同时渲染 `seed -> candidate` 与受预算限制的 `candidate -> candidate`
  - 左侧支持候选搜索、facets 与结果后二次过滤
  - 候选可直接进入 formal drill-down，继续使用 `/api/subgraph`、`/api/expand`、detail、edit
  - 右侧详情 / 编辑 / 直接编辑仍可用

### 7.7 验证命令（可复制）

后端启动：
```bash
cd ~/kg-system/backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

前端启动：
```bash
cd ~/kg-system/frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Nebula Console 6 条验证命令：
```ngql
-- 1) 查看节点属性（含 version/updated_at/updated_by）
FETCH PROP ON Entity 1 YIELD properties(vertex);

-- 2) 关系遍历（注意使用管道 LIMIT）
GO FROM 1 OVER REL2 YIELD src(edge), dst(edge), rank(edge), properties(edge).relation | LIMIT 10;

-- 3) 查看边属性（按 src->dst@rank 定位）
FETCH PROP ON REL2 1->38075@0 YIELD properties(edge);

-- 4) 节点写回并验证 version 递增
UPDATE VERTEX ON Entity 1
SET Entity.description="manual update from nebula console",
    Entity.version=1,
    Entity.updated_at=1700000000,
    Entity.updated_by="console"
YIELD properties(vertex);

-- 5) 边写回并验证 version 递增
UPDATE EDGE ON REL2 1->38075@0
SET relation="associate",
    source="console",
    evidence="manual edge update",
    version=1,
    updated_at=1700000000,
    updated_by="console"
YIELD properties(edge);

-- 6) 统计
SHOW STATS;
```

### 7.7 手工验证一次节点编辑 + 一次边编辑
1. 前端打开后，先在右侧 `编辑`/`直接编辑` 区设置 `updated_by`。
2. 节点编辑：输入一个存在的 `vid` 点击“加载”，修改 `entity_name/description`，点击“保存节点”。
3. 边编辑：输入存在的 `src/dst/rank` 点击“加载”，修改 `relation/evidence`，点击“保存边”。
4. 若提示 409，点击“重新加载详情”后再保存。
5. 在 Nebula Console 执行 `FETCH PROP` 确认 `version` 递增且 `updated_at` 为秒级时间戳。

# 最终交接文档（2026-03-06）

> 本文档以当前仓库实际状态为准，用于最终交接与后续 agent 接手。
> 阶段中间文档仍保留，但若与本文冲突，以本文为准。
>
> 多空间 import + discovery/search availability 的最终收口，请同时参考：
> [docs/archive/MULTI_SPACE_DELIVERY_20260312.md](/home/ray/kg-system/docs/archive/MULTI_SPACE_DELIVERY_20260312.md)

## 1. 当前结论

当前仓库已经从“重构进行中”收敛到“可启动、可验证、可继续交接”的状态，但仍存在少量未闭环项。

当前可确认结论：

- 后端可稳定启动，`/api/health` 正常。
- 前端可稳定启动，默认地址 `http://127.0.0.1:5173`。
- 标准化启停/检查/关闭流程已落地在 `scripts/`。
- 标准化 API smoke 已落地，可在当前机器执行。
- `relation_types` 已从大列表固定返回改为 `q + limit + offset` 模式，前端改为 searchable / incremental 交互。
- 前端大 chunk warning 已收敛，`npm run build` 不再报 `>500kB` 警告。
- Playwright/E2E 已正式入库在 `frontend/e2e/`，并已覆盖 discovery candidate search -> formal drill-down -> edit 主链；运行时仍要求宿主机具备 Chromium 依赖。
- 前端全量 lint 仍未全部通过，但相关阶段性历史基线文档已在后续文档治理中删除。

## 2. 架构变更说明

### 2.1 检索链路

- 搜索主链路已切到 ES-first。
- Nebula 不再承担默认全图扫描式检索，只负责 VID 详情与受限图查询。
- 兼容入口保留在 `/api/search`、`/api/suggest`、`/api/suggest_raw_id`，后端由 v2 service 承接。
- 2026-03-16 起，`fallback_search.py` 与旧 `search_service.search/suggest/suggest_raw_id` 已删除，不再保留旧检索兜底。

关键文件：

- `backend/app/routers/search.py`
- `backend/app/routers/search_v2.py`
- `backend/app/services/search_v2/service.py`
- `backend/app/services/search_v2/budget.py`

### 2.2 metadata 与 relation_types

- `EntityTypeStat` / `RelationTypeStat` metadata 保存在数据库内，不恢复为请求期全图实时统计。
- `/api/entity_types` 读取 metadata。
- `/api/relation_types` 当前契约为：
  - `GET /api/relation_types?q=&limit=100&offset=0`
  - 返回 `items / matched_total / next_offset / has_more`
- 前端 discovery 主链继续消费 metadata；旧 relation filter 面板已删除。

关键文件：

- `backend/app/services/metadata_service.py`
- `backend/app/services/graph_service.py`
- `backend/app/schemas/graph.py`
- `frontend/src/api/kg.ts`
- `frontend/src/components/DiscoveryPanel.tsx`
- `frontend/src/app/AppShell.tsx`

### 2.3 图查询预算

- `subgraph / expand / graph/discovery` 已纳入正式预算控制。
- 旧 `multi_entity_graph*` 已删除，不再属于正式能力面。
- 返回体中包含 `truncated / dropped_* / budget_applied`，前端已对裁剪和降级信息做 notice 呈现。

关键文件：

- `backend/app/services/graph_budget.py`
- `backend/app/services/graph_service.py`
- `frontend/src/hooks/useGraphData.ts`
- `frontend/src/components/TopBar.tsx`
- `frontend/src/App.tsx`

### 2.4 前端包体与加载策略

- 图谱画布 `GraphCanvas`、右侧详情面板、关系筛选面板已改为懒加载。
- Vite 已按 `react / react-window / @antv/*` 做保守 manual chunk 切分。
- 当前 `npm run build` 不再报大 chunk warning。

关键文件：

- `frontend/src/App.tsx`
- `frontend/vite.config.ts`

## 3. 启动 / 验证 / 关闭流程

### 3.1 标准流程

```bash
bash scripts/start_stack.sh
bash scripts/check_stack.sh
bash scripts/verify_stack.sh
bash scripts/smoke_api.sh
bash scripts/stop_stack.sh
```

说明：

- `start_stack.sh` 只会在目标进程真实占有端口且 HTTP 可达后写入 `.run/backend.pid`、`.run/frontend.pid`
- `stop_stack.sh` 返回前会等待真实退出与端口释放；最终确认关闭状态时仍建议串行再执行一次 `bash scripts/check_stack.sh`

### 3.2 脚本说明

- `scripts/start_stack.sh`
  - 启动前后端
  - 写入 `.run/backend.pid`、`.run/frontend.pid`
  - 日志输出到 `.run/logs/backend.log`、`.run/logs/frontend.log`
- `scripts/check_stack.sh`
  - 组合检查 pidfile、pid、端口、HTTP
  - 输出 `running / degraded / stale_pidfile / stopped`
- `scripts/verify_stack.sh`
  - 做最小运行态验证
  - 以真实可达性为准，不会因单独 pidfile 缺失而直接失败
  - 输出后端 `/api/health` 响应和前端响应头
- `scripts/smoke_api.sh`
  - 做最小 API 回归
  - 只依赖后端服务可达性，不依赖前端或 pidfile
  - 当前覆盖：
    - `GET /api/health`
    - `GET /api/entity_types`
    - `GET /api/relation_types?limit=20&offset=0`
    - `POST /api/search`
    - `POST /api/subgraph`
- `scripts/stop_stack.sh`
  - 关闭前后端
  - 等待进程真实退出与端口释放
  - 若残留端口由外部进程占用，输出 `stop_incomplete` 并返回非 0

### 3.3 前置条件

- `backend/.venv` 已准备
- `frontend/node_modules` 已安装
- `.env` 已正确配置 Nebula / ES 相关参数
- Nebula 与 Elasticsearch 已可用

## 4. 当前验证等级说明

为便于交接，当前验证分为 3 个等级：

### L1：静态与构建级验证

覆盖内容：

- shell 脚本语法检查
- 后端 compileall
- 后端单测
- 前端 build
- lint 基线拆分

当前状态：**基本完成**

说明：

- `scripts/*.sh` 已通过 `bash -n`
- 后端 compileall / unittest 可执行
- 前端 `npm run build` 成功
- 前端全量 lint 仍未完全通过，但历史问题已单独基线化

### L2：服务与 API 级验证

覆盖内容：

- 前后端标准化启动
- 进程检查
- `/api/health`
- metadata 接口
- 搜索接口
- 子图接口
- 标准 smoke 回归

当前状态：**完成**

说明：

- `start/check/verify/stop` 已在当前机器实跑通过
- `smoke_api.sh` 已在当前机器实跑通过

### L3：浏览器交互与自动化回归

覆盖内容：

- 浏览器自动化 E2E
- 浏览器级 UI 主链路回归

当前状态：**部分完成**

说明：

- Playwright 套件已正式入库在 `frontend/e2e/`
- 已实跑通过 discovery 主链最小回归：
  - discovery candidate load subgraph enters formal drilldown without legacy fallback
  - discovery detail and edit stay reachable in unified workflow
- 若宿主机缺少 Chromium 依赖，仍需先补齐 `libnspr4`、`libnss3`、`libasound.so.2`

## 5. 当前遗留问题清单

### 5.1 前端全量 lint 仍未通过

现状：

- 全量 `eslint .` 仍受历史遗留问题影响。
- 历史基线文档已在后续文档治理中删除；本节仅保留结论说明。

影响：

- 不阻塞当前系统运行与交接
- 但会阻碍后续把 lint 作为 CI 强门禁

建议：

- 后续按 baseline 增量清理
- 优先处理：
  - `frontend/App.tsx`
  - `frontend/src/components/GraphCanvas.tsx`
  - `frontend/src/components/RelationFilter/RelationFilterPanel.tsx`
  - `frontend/src/hooks/useRelationFilter.ts`

### 5.2 浏览器级 E2E 依赖仍需显式准备

现状：

- Playwright/E2E 套件已入库
- 不同机器上是否能直接运行，取决于 Chromium 依赖是否齐备

影响：

- 若依赖不齐，浏览器级自动化回归会在浏览器启动阶段失败
- 一旦依赖齐备，可直接执行仓库内现成 E2E

建议：

- 先补系统依赖
- 再按 `frontend/README.md` 中的命令执行 `npm run e2e` / `npm run e2e:smoke`

### 5.3 根目录 `frontend/App.tsx` 仍是 lint 历史负担

现状：

- 根目录 `frontend/App.tsx` 会被 `eslint .` 纳入扫描
- 该文件不是当前主入口 `frontend/src/App.tsx`
- 但仍是历史 lint 大头之一

影响：

- 会放大全量 lint 噪音

建议：

- 后续确认是否仍需保留
- 若确认为历史残留，可在单独提交中删除或在 lint 配置中显式排除

### 5.4 worker 产物仍较大，但已低于 warning 阈值

现状：

- 当前构建不再有大 chunk warning
- 但 `worker-*.js` 仍约 300kB

影响：

- 当前不构成构建阻塞
- 但若后续继续做性能优化，可再分析来源

建议：

- 仅在后续专项性能优化时处理，不建议在本阶段继续扩散

## 6. 恢复完整 E2E 的步骤

### 6.1 环境层恢复

Ubuntu 24.04 当前建议先安装：

```bash
sudo apt-get update
sudo apt-get install -y libnspr4 libnss3
```

若后续启用 Playwright/Chromium，建议补齐常见浏览器依赖：

```bash
sudo apt-get update
sudo apt-get install -y \
  libnspr4 \
  libnss3 \
  libasound2t64 \
  libatk1.0-0 \
  libcups2t64 \
  libdbus-1-3 \
  libdrm2 \
  libgbm1 \
  libglib2.0-0 \
  libgtk-3-0 \
  libx11-xcb1 \
  libxcb1 \
  libxcomposite1 \
  libxdamage1 \
  libxext6 \
  libxfixes3 \
  libxkbcommon0 \
  libxrandr2 \
  libxrender1 \
  libxshmfence1 \
  libcairo2 \
  libpango-1.0-0 \
  fonts-liberation
```

### 6.2 测试套件恢复

当前仓库还需要正式补齐：

1. `playwright.config.*`
2. `tests/e2e/` 或等价目录
3. 基础 smoke 用例
4. `package.json` 中的 E2E 脚本
5. CI 或具备浏览器依赖的 runner

若采用 Playwright，最小恢复路径建议为：

```bash
cd frontend
npm install -D @playwright/test
npx playwright install chromium
```

如需自动补系统依赖：

```bash
sudo npx playwright install-deps chromium
```

### 6.3 第一批建议回归用例

仅覆盖高价值主链路：

1. 首页打开
2. 搜索节点
3. 加载子图
4. 打开关系筛选并搜索关系类型
5. 点击节点查看详情

## 7. 最终提交前建议验证

建议按以下顺序执行：

```bash
bash -n scripts/common.sh scripts/start_stack.sh scripts/check_stack.sh scripts/verify_stack.sh scripts/smoke_api.sh scripts/stop_stack.sh

cd backend
.venv/bin/python -m compileall app/services app/schemas app/routers
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'

cd ../frontend
npm run build
npx eslint src/App.tsx src/api/http.ts src/api/kg.ts src/components/EditWritebackPanel.tsx src/components/LeftSearchPanel.tsx src/components/RelationFilter/RelationFilterPanel.tsx src/components/TopBar.tsx src/constants/kg.ts src/hooks/useEntityTypeOptions.ts src/hooks/useGraphData.ts src/hooks/useRelationFilter.ts src/types/kg.ts src/utils/httpError.ts vite.config.ts

cd ..
bash scripts/start_stack.sh
bash scripts/verify_stack.sh
bash scripts/smoke_api.sh
bash scripts/stop_stack.sh
```

若要看历史 lint 债务，请单独执行：

```bash
cd frontend
npx eslint .
```

### 7.1 本次实际执行结果（2026-03-06）

已实际执行并通过：

- `bash -n scripts/common.sh scripts/start_stack.sh scripts/check_stack.sh scripts/verify_stack.sh scripts/smoke_api.sh scripts/stop_stack.sh`
- `cd backend && .venv/bin/python -m compileall app/services app/schemas app/routers`
- `cd backend && .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
  - 结果：`Ran 7 tests, OK`
- `cd frontend && npm run build`
  - 结果：成功，且无大 chunk warning
- `cd frontend && npx eslint src/App.tsx src/api/http.ts src/api/kg.ts src/components/EditWritebackPanel.tsx src/components/LeftSearchPanel.tsx src/components/RelationFilter/RelationFilterPanel.tsx src/components/TopBar.tsx src/constants/kg.ts src/hooks/useEntityTypeOptions.ts src/hooks/useGraphData.ts src/hooks/useRelationFilter.ts src/types/kg.ts vite.config.ts`
  - 结果：通过
- `bash scripts/start_stack.sh`
- `bash scripts/verify_stack.sh`
  - 结果：后端 `/api/health` 正常，前端首页返回 `HTTP/1.1 200 OK`
- `bash scripts/smoke_api.sh`
  - 结果：
    - `GET /api/health` -> `ok hosts_rows=1`
    - `GET /api/entity_types` -> `ok items=13`
    - `GET /api/relation_types?limit=20&offset=0` -> `ok items=20 matched_total=200564 has_more=True`
    - `POST /api/search` -> `ok nodes=0 edges=0 total_candidates=0`
    - `POST /api/subgraph` -> `ok root_vid=1 nodes=120 edges=120 truncated=True`
- `bash scripts/stop_stack.sh`
- 串行再次执行 `bash scripts/check_stack.sh`
  - 结果：`backend: stopped`、`frontend: stopped`

已知未完成：

- `cd frontend && npx eslint .` 仍会因为历史基线问题失败
- 浏览器级 E2E 仍依赖宿主机 Chromium 运行库完整

## 8. 相关文档索引

- 阶段性验证 / lint 基线 / E2E 降级文档已在后续文档治理中按规则删除。

## 9. 诚实结论

- 当前仓库**适合进入提交与交接阶段**，前提是接受“L2 完成、L3 已恢复最小主链但未做全量套件”的现状。
- 当前仓库**不适合宣称为完整回归闭环**，因为前端全量 lint 仍有历史遗留，且浏览器 E2E 仍受宿主机依赖约束。
- 若本次目标是“可交接、风险明确、后续可继续优化”，当前状态已经满足。

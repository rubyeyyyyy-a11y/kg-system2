# Phase 5 验证、回归与交接（2026-03-06）

## 1. 本次目标与结论

目标：验证阶段0~4重构后系统可启动、可验证、可交接，并补全文档。

结论（基于本次实际运行）：
- 后端可启动，`/api/health` 与核心接口可用。
- 前端可启动；标准脚本使用 `5173` 且启用了 `--strictPort`，端口冲突时会明确失败，不再静默切换端口。
- 搜索已是 ES-first，`/api/search` 默认 nodes-first，不默认联带边。
- 图扩展接口预算生效，返回 `stats.truncated/dropped_*/budget_applied`。
- metadata 接口（`/api/entity_types`、`/api/relation_types`）可用，来自 Nebula metadata tags，而非请求期全图聚合。
- 当前脚本体系已补齐 `start/check/verify/smoke/stop` 闭环：状态判断不再只依赖 pidfile，`stop` 返回前会等待真实退出。
- 存在未闭环项：前端 lint 未通过、浏览器自动化烟测受系统依赖限制、`/api/relation_types` 返回量偏大。

## 2. 新架构说明（贴合当前仓库）

核心文件：
- `backend/app/services/search_v2/service.py`
- `backend/app/services/search_v2/budget.py`
- `backend/app/services/graph_service.py`
- `backend/app/services/graph_budget.py`
- `backend/app/services/metadata_service.py`
- `frontend/src/App.tsx`
- `frontend/src/hooks/useGraphData.ts`
- `frontend/src/hooks/useEntityTypeOptions.ts`
- `frontend/src/components/LeftSearchPanel.tsx`
- `frontend/src/components/TopBar.tsx`

设计要点：
- 检索：ES 主检索，Nebula 仅做 VID 定位详情与受限图查询。
- metadata：`EntityTypeStat` / `RelationTypeStat` 存在 Nebula 内，接口读取 metadata，不做请求期全图统计。
- 图查询预算：统一在 `graph_budget.py` 控制 subgraph/expand/multi_entity_graph。
- 前端交互：搜索后先展示节点，边/子图由用户显式触发加载。

## 3. 搜索链路说明

入口：
- 兼容旧接口：`POST /api/search`、`GET /api/suggest`、`GET /api/suggest_raw_id`
- 新接口：`/api/v2/search|suggest|suggest_raw_id`

链路：
1. 前端调用 `frontend/src/api/kg.ts`。
2. 后端 `routers/search.py` 旧接口路由到 v2 实现。
3. `search_v2/service.py` 先做 ES 健康和 ES 查询，再按 VID 到 Nebula 拉节点属性。
4. 默认 `include_edges=false`；若传 `include_edges=true`，仅受限兼容并返回 legacy note。

## 4. metadata 方案说明

结构与命名：
- Tag: `EntityTypeStat(entity_type, entity_type_norm, count, updated_at, updated_by)`
- Tag: `RelationTypeStat(relation_type, relation_type_norm, count, updated_at, updated_by)`

读路径：
- `/api/entity_types` -> `search_service.entity_types()` -> `metadata_service.list_entity_types()`
- `/api/relation_types` -> `graph_service.relation_types()` -> `metadata_service.list_relation_types()`

写/刷新路径：
- 全量刷新：`data-import/scripts/04_refresh_metadata.py --mode rebuild`
- 导入后自动：`data-import/run.sh` Step 7/8
- 增量维护：`edit_service.py` 在实体类型/关系类型修改后调用 `metadata_service.sync_*_change()`

## 5. 启动顺序（建议）

标准脚本（当前推荐）：
- `bash scripts/start_stack.sh`
- `bash scripts/check_stack.sh`
- `bash scripts/verify_stack.sh`
- `bash scripts/smoke_api.sh`
- `bash scripts/stop_stack.sh`
- `bash scripts/check_stack.sh`

脚本约定：
- 默认后端：`127.0.0.1:8000`
- 默认前端：`127.0.0.1:5173`
- 日志目录：`.run/logs/`
- PID 文件：`.run/backend.pid`、`.run/frontend.pid`
- `start_stack.sh` 启动前会尝试停止当前仓库同端口的旧 `uvicorn/vite` 进程，避免 split-brain
- `start_stack.sh` 先写 `.run/*.pid.starting`，只在目标进程真实占有端口且 HTTP 可达后才落正式 pidfile
- `check_stack.sh` 组合判断 pidfile、pid、端口、HTTP，输出 `running / degraded / stale_pidfile / stopped`
- `verify_stack.sh` 以真实可达性为准，不会因单独 pidfile 缺失而直接失败
- `smoke_api.sh` 只依赖后端服务可达性，逐项输出各 API 的结果
- `stop_stack.sh` 会等待进程真实退出和端口释放；若端口仍被外部进程占用，会输出 `stop_incomplete` 并返回非 0
- 若依赖未准备好会直接失败并给出明确提示，不会自动安装

前置条件：
- `backend/.venv` 已存在且依赖已安装
- `frontend/node_modules` 已存在

手工顺序（兼容保留）：

1. 启动 NebulaGraph 与 Elasticsearch。
2. （首次或重建）执行数据导入/迁移（见第6节）。
3. 启动后端：
   - `cd backend && ./scripts/run_backend_single.sh`
4. 启动前端：
   - `cd frontend && npm run dev -- --host 127.0.0.1 --port 5173`
5. 打开前端地址（默认 `http://127.0.0.1:5173`；若占用看终端输出端口）。

## 6. 迁移脚本执行顺序

### 6.1 全量导入（推荐）

命令：
- `cd data-import && bash run.sh`

当前 `run.sh` 顺序（8步）：
1. env_check
2. reset space + schema
3. prepare_vertices
4. import_vertices
5. prepare_edges
6. import_edges
7. refresh_metadata（`04_refresh_metadata.py --mode rebuild`）
8. verify（含 `03_verify_after_import.sh` + `05_verify_metadata.sh`）

### 6.2 存量图最小迁移（不重导原图）

命令：
- `bash data-import/scripts/10_migrate_metadata.sh`
- `bash data-import/scripts/05_verify_metadata.sh`

### 6.3 ES 索引构建/刷新

命令：
- `cd backend && .venv/bin/python scripts/build_es_index.py --batch-size 500`

## 7. 新增配置项说明

已更新 `.env.example`，新增主要项：
- `FALLBACK_ENABLE_SCAN=0`
- `SEARCH_V2_*`（query min len、topk、include_edges 兼容预算、ES 超时/健康缓存）
- `GRAPH_*`（subgraph/expand/multi_entity_graph 的统一预算）

重点建议：
- 生产保持 `FALLBACK_ENABLE_SCAN=0`。
- 按图规模调 `GRAPH_*_MAX_NODES_CAP` / `GRAPH_*_MAX_EDGES_CAP` / `*_PER_ROOT_NEIGHBOR_CAP`。

## 8. 本次实际验证记录（已执行）

### 8.1 启动验证

后端启动成功：
- 命令：`cd backend && ./scripts/run_backend_single.sh`
- 关键输出：`Uvicorn running on http://127.0.0.1:8000`

前端启动成功：
- 命令：`bash scripts/start_stack.sh`
- 本次脚本行为：前端固定使用 `http://127.0.0.1:5173`，端口冲突时启动明确失败，不再自动切到 `5174`
- 验证命令：`bash scripts/check_stack.sh`、`bash scripts/verify_stack.sh`

### 8.2 API 验证（你要求的接口）

执行日志：
- `backend/logs/phase5_api_validation_20260306_131732.log`
- `backend/logs/phase5_api_summary_20260306_132149.json`

结果摘要：
- `GET /api/health` -> `200`
- `POST /api/search` -> `200`（默认 `nodes=[] edges=[]`，`meta.strategy=ES_V2`，`include_edges_applied=false`）
- `GET /api/suggest?q=ca&limit=5` -> `200`（返回2条）
- `GET /api/suggest_raw_id?q=ens&limit=5` -> `200`（返回0条）
- `GET /api/entity_types` -> `200`（返回13类）
- `GET /api/relation_types` -> `200`（当前 limit=5000）
- `POST /api/subgraph`（`root_vid=1`）-> `200`（`truncated=true`, `dropped_neighbors=679`）
- `POST /api/graph/discovery`（`seed_vids=[1]`）-> `200`（`seed_count=1`, `candidate_count=26`, `node_count=27`, `edge_count=37`, `truncated=true`）

补充验证：
- `POST /api/search` with `include_edges=true` -> `meta.include_edges_legacy_note` 存在，兼容提示生效。
- `POST /api/expand`、`POST /api/multi_entity_graph` 返回 `stats.dropped_*` 与 `truncated`。
- 高风险请求期聚合路径检查：`rg -n 'COUNT\\(|DISTINCT' backend/app/services/search_service.py backend/app/services/graph_service.py backend/app/routers -S` 返回空（未发现实时全图聚合字样）。
- `scripts/smoke_api.sh` 已补 discovery 校验，后续标准 smoke 会覆盖新接口。

### 8.3 关键前端交互验证

已完成：
- 前端服务可访问（5173/5174）。
- 构建成功：`cd frontend && npm run build`。
- 代码路径核验：
  - 搜索结果区存在 `加载选中节点子图` / 单卡片 `加载子图`（`LeftSearchPanel.tsx`）
  - 顶栏存在 `加载更多边` 和裁剪提示（`TopBar.tsx`）
  - 错误/降级/裁剪有统一 notice（`App.tsx` + `useGraphData.ts`）
  - `entity_types` 延迟/按需加载、`relation_types` 非首屏阻塞加载（`useEntityTypeOptions.ts` / `App.tsx`）

未完全自动化：
- Playwright 自动化烟测失败（环境缺少 `libnspr4`，且 `install-deps` 需 sudo）。
- 失败记录见终端错误：`chrome-headless-shell: error while loading shared libraries: libnspr4.so`。

### 8.4 回归构建/测试

- 后端编译：`cd backend && .venv/bin/python -m compileall app/services app/schemas app/routers` -> 成功
- 后端单测：`cd backend && .venv/bin/python -m unittest tests.test_graph_discovery_service tests.test_edit_service tests.test_relation_types_service tests.test_metadata_ids tests.test_raw_id_normalization` -> `Ran 16 tests, OK`
- 前端构建：`cd frontend && npm run build` -> 成功
- 前端 lint：本阶段未重新全量执行；已验证 `src/App.tsx`、`src/hooks/useGraphData.ts` 局部 eslint 通过

### 8.5 统一关系发现与编辑写回专项回归（2026-03-06 17:45 CST）

本次实际执行：
- `bash scripts/start_stack.sh` -> 成功
- `bash scripts/check_stack.sh` -> `backend/frontend status=running`
- `bash scripts/verify_stack.sh` -> 成功
- `bash scripts/smoke_api.sh` -> 成功，已包含 `/api/graph/discovery`

discovery 最小联调：
- 请求：`seed_vids=[1]`, `max_nodes=80`, `max_edges=200`, `top_k_per_type=10`, `hop=1`
- 返回：`seed_count=1`, `candidate_count=26`, `node_count=27`, `edge_count=37`, `truncated=true`
- 预算信息：`recall_candidate_count=119`, `kept_candidate_count=26`, `dropped_nodes=93`, `dropped_neighbors=1350`

编辑写回往返验证：
- 节点：`GET /api/node/1` -> `PATCH /api/node/1`（description 追加阶段标记）-> `GET /api/node/1` -> 回滚恢复原 description
- 边：`POST /api/edge_detail`(`REL2`, `1 -> 35076`, rank=`0`) -> `PATCH /api/edge`（evidence 追加阶段标记）-> 再次查询 -> 回滚恢复原 evidence
- 验证结果：
  - node version: `8 -> 9 -> 10`
  - edge version: `8 -> 9 -> 10`
  - 两条链路都能正确写入、返回新版本，并恢复原值

前端统一关系发现手工验证步骤：
1. 执行 `bash scripts/start_stack.sh`
2. 打开 `http://127.0.0.1:5173`
3. 左侧切换到 `统一关系发现`
4. 通过名称或 raw id 添加 1 个或多个 seed 节点
5. 保持默认 `hop=1`，设置合适的 `max_nodes / max_edges / top_k_per_type`
6. 点击运行 discovery，确认画布出现 `seed + candidates + candidate-candidate edges`
7. 在左侧 runtime facets 勾选/取消 `entity types` 与 `relation types`，确认图即时重绘
8. 点击节点，确认右侧详情正常加载；切到 `编辑 / 直接编辑` 页签，保存一个可回退字段后再恢复
9. 点击边，确认边详情和边编辑写回正常
10. 切回 `旧模块`，确认 legacy 搜索/子图/多实体入口仍可访问

## 9. 重构前后对比

### 9.1 查询路径差异

- 之前：搜索可能 Nebula 扫描兜底。
- 现在：ES-first（v2）；Nebula 仅 VID 详情与受限图查询。

### 9.2 fallback 行为差异

- 之前：可退化到 Nebula 高成本扫描路径。
- 现在：ES 故障返回结构化错误（如 `es_timeout/es_unavailable`），不做全图扫描；`FALLBACK_ENABLE_SCAN` 默认 `0`。

### 9.3 首屏请求流差异

- 之前：搜索/筛选可能伴随重图数据。
- 现在：搜索先节点；`entity_types` 延迟/按需；`relation_types` 在用户开启关系筛选时请求，不阻塞首屏。

### 9.4 边加载策略差异

- 之前：搜索可能联带大量边。
- 现在：默认不联带边；通过 `subgraph/expand/multi_entity_graph` 显式按需加载，且预算硬限制 + 裁剪标记。

## 10. 故障排查

### 10.1 `/api/health` 非200

命令：
- `curl -v http://127.0.0.1:8000/api/health`

排查：
- 检查 Nebula 地址/账号：`.env` 的 `NEBULA_*`
- 检查 space/tag/edge 是否存在：`USE demo_kg; SHOW TAGS; SHOW EDGES;`

### 10.2 `/api/search` 返回 ES 不可用

检查：
- `ES_URL`、`ES_INDEX`、`ES_ENABLED`
- ES 索引是否存在并有文档
- 正式搜索链路应使用 `kg_entity`
- `kg_entity_dev` 仅允许作为开发样本索引，不作为正式搜索验证依据

重建索引：
- `cd backend && .venv/bin/python scripts/build_es_index.py --batch-size 500`

### 10.3 `entity_types/relation_types` 为空或异常

执行：
- `bash data-import/scripts/10_migrate_metadata.sh`
- `bash data-import/scripts/05_verify_metadata.sh`

### 10.4 图接口频繁裁剪

调优：
- 上调 `GRAPH_*_MAX_NODES_CAP` / `GRAPH_*_MAX_EDGES_CAP` / `*_PER_ROOT_NEIGHBOR_CAP`
- 同时保留超级节点保护，不建议直接放开扫描上限。

### 10.5 前端端口冲突

现象：
- `start_stack.sh` 失败，`frontend.log` 中出现 `Port 5173 is already in use`

处理：
- 结束旧监听进程后重试 `bash scripts/start_stack.sh`
- 用 `bash scripts/check_stack.sh` 或 `ss -ltnp '( sport = :5173 )'` 确认占用者

## 11. 仍未解决的问题与后续建议（如实）

未解决问题：
1. 前端 lint 当前不通过（57 errors / 16 warnings），需要专项清理。
2. 浏览器自动化 UI 烟测在当前机器受系统依赖限制（`libnspr4` 缺失，且缺 sudo）。
3. `relation_types` 返回上限 5000，数据体量偏大，前端筛选体验仍有压力。
4. `npm run build` 仍有大 chunk 警告（>500KB）。

后续建议：
1. 增加 CI 门禁：后端测试 + 前端 build + 关键 API smoke（health/search/subgraph）。
2. 为前端补可执行 E2E（Playwright），在具备浏览器依赖的 runner 上执行。
3. 给 discovery 追加前端自动化回归，至少覆盖 seed 添加、运行查询、runtime filter、详情编辑入口。
4. 给 `relation_types` 增加分页/分组或 topN+搜索式下拉，避免一次返回 5000。
5. 前端做代码分包（dynamic import/manualChunks），降低首包体积。
6. 收敛并最终删除遗留 fallback 代码路径，避免误开风险。

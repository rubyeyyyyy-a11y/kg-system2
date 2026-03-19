# Multi-Space Canonical Search 验收基线

更新日期：2026-03-13

## 1. 文档目的

本文档是当前项目这一轮 multi-space canonical search 治理的正式验收基线。

它用于确认本轮已经完成的主目标：

- strict multi-space canonical search
- space readiness 合同统一
- import searchable 闭环
- demo_kg full canonical backfill
- 前端 per-space session 治理主链路

它同时作为后续开发、回归、交接、回滚和排障的基准文档。后续任何继续迭代，都应以本文档记录的“当前正式合同”和“当前验收事实”为准，而不是回退到历史单 space 习惯或旧的隐式 fallback 认知。

## 2. 背景与历史问题

旧 single-space 阶段的系统默认只有一个 Nebula space，前后端很多路径可以依赖默认 space 或共享会话状态工作。当前系统已经进入 strict multi-space canonical ES 阶段，当前 space 必须明确解析，搜索结果必须只来自当前 space，ES 文档也必须满足 canonical 合同。

`demo_kg` 是历史默认大 space。它的历史问题不是 Nebula 图丢失，也不是前端 space 切换失败，而是历史 ES 文档没有全部迁移到当前 canonical 合同上，因此切到大 space 时，ES 候选层只能看到少量符合新合同的文档。

这里的历史根因必须明确：

- canonical ES 合同已经变为 `_id={space}:{vid}`，且文档必须带 `space_name`
- 历史 `demo_kg` 大量旧 ES 文档没有 `space_name`
- 当前搜索统一按 `space_name=<current_space>` 过滤
- 因此旧无 `space_name` 文档在线上查询中不可见
- 根因不是 space 切换失败，而是 canonical backfill 未完成

本轮治理完成后，`demo_kg` 的 canonical backfill 已补齐，线上查询继续只认 canonical 合同；旧无 `space_name` 文档物理仍存在，但不再影响线上严格按 space 查询。

## 3. 当前正式合同

### 3.1 current space 合同

- 前端 current space 由 `frontend/src/features/space/store.ts` 持久化到 `localStorage`，并由 `useCurrentSpace()` 暴露给应用层。
- 前端启动和切 space 后，会通过 `/api/spaces/current` 解析当前实际生效的 space；`frontend/src/features/space/hooks/useSpaces.ts` 负责刷新 `spaces` 和 `resolvedCurrent`。
- 所有前端 KG API 请求都通过 `frontend/src/api/http.ts` 统一注入 `X-KG-Space`；若调用方显式传 `spaceName`，优先使用该值，否则回退到当前 store snapshot。
- 后端在 `backend/app/main.py` 的 HTTP middleware 中调用 `bind_request_space()`，只允许 `X-KG-Space` 覆盖默认 space，并把解析结果绑定到 `request.state.space_name` 与 `ContextVar`。
- 后端 `get_current_space()` 是请求期唯一 current space 读取入口；服务层不应再从 body/query 引入第二套 target space 语义。
- Nebula 与 ES 都消费这个 current space：
  - `NebulaClient` 默认使用显式 `space_name`，否则回退到 `get_current_space()`
  - `ElasticsearchClient` 默认使用显式 `space_name`，否则回退到 `get_current_space()`

### 3.2 canonical ES 合同

- 当前 canonical index 名称为 `kg_entity`（来自当前环境 `ES_INDEX` 默认值和 backfill summary）。
- canonical 文档 `_id` 格式为 `{space_name}:{vid}`。
- canonical 文档在 `_source` 中至少包含：
  - `vid`
  - `space_name`
  - `entity_name`
  - `description`
  - `entity_raw_id`
  - `entity_raw_id_text`
  - `raw_id_norm`
  - `raw_id_norm_text`
  - `entity_type`
  - `entity_type_text`
  - `source`
- `space_name` 是线上可见性的必要字段；没有 `space_name` 的旧文档不满足 canonical 合同。
- 搜索相关接口统一按 `term space_name=<current_space>` 过滤，包括：
  - `/api/search`
  - `/api/suggest`
  - `/api/suggest_raw_id`
  - `/api/discovery/entity_candidates`
- `space_meta` 由后端统一附带在搜索/候选响应中，反映当前 space 的 readiness / search 状态，而不是接口各自临时推导。

### 3.3 readiness 合同

- `graph_status` 合法值：
  - `unavailable`
  - `ready`
- `search_status` 合法值：
  - `unavailable`
  - `empty`
  - `partial`
  - `full`
  - `failed`
- readiness 与 `space_meta` 的唯一真相来源是 `backend/app/services/spaces/readiness_service.py`。
- `graph_status` 的判定条件：
  - registry `status=ready`
  - 且 `internal_status=ready`
- `search_status` 的判定基于 registry 中的 `index_status`：
  - `failed` -> `failed`
  - `verified_empty` -> `empty`
  - `verified_partial` -> `partial`
  - `verified_nonempty` 且 `coverage_pct < 100` -> `partial`
  - `verified_nonempty` 且 `coverage_pct >= 100` -> `full`
  - 非 ready space 或无 `index_status` -> `unavailable`
- readiness 真相来源不是在线 verify，不是接口即时扫描，而是 registry 中持久化的 `index_status` snapshot，经 `readiness_service` 派生后输出。
- `/api/spaces` 返回每个 space 的 registry summary，并附带 `graph_status`、`search_status`、`coverage_pct`。
- `/api/spaces/current` 返回当前解析到的 space，并附带：
  - `source`
  - `header_present`
  - `header_value`
  - `registry_status`
  - `graph_status`
  - `search_status`
  - `coverage_pct`
  - `index_status`

### 3.4 import searchable 合同

- 导入成功的业务完成定义，不再只是 Nebula 写入成功。
- 当前 import searchable 闭环为：
  1. 写 Nebula
  2. sync canonical ES
  3. verify imported entities visible
  4. refresh / persist registry `index_status`
  5. 生成 `completion_summary.searchable=true`
- 在实现上，`backend/app/services/imports/es_postprocess_service.py` 以如下条件判定 searchable：
  - `verify_success=true`
  - `registry_index_status_written=true`
- 导入作业最终可交付的完成判定应以 job state 中这些字段为准：
  - `status=succeeded`
  - `completion_summary.searchable=true`
  - `index_status_snapshot` 已写回
- 在线路径不再承担 verify 真相来源；verify 与 registry 回写发生在导入后处理或 backfill 管理脚本中。

## 4. 本轮实施结果

### 4.1 D1 readiness 合同收口

改动目标：

- 把 readiness / `space_meta` 收口到同一派生逻辑
- 消除接口各自重复推导、在线重 verify 和多套口径

核心实现点：

- `readiness_service.py` 成为 readiness 与 `space_meta` 的唯一派生器
- `/api/spaces`、`/api/spaces/current`、search / suggest / candidate 响应统一读取 registry / index snapshot
- 导入后处理中的重复 `search_status` 推导删除，改为复用同一 readiness 派生逻辑

影响的关键模块：

- `backend/app/services/spaces/readiness_service.py`
- `backend/app/services/spaces/index_status_service.py`
- `backend/app/routers/spaces.py`
- `backend/app/services/search_v2/service.py`
- `backend/app/services/discovery_entity_candidate_service.py`

为什么必要：

- 如果 readiness 不是统一合同，前后端对“当前 space 是否 ready / full / partial”的理解会继续分裂，后续导入验收、回归和交接都无法稳定。

### 4.2 D2 import searchable 闭环

改动目标：

- 让“导入成功”升级为“新导入数据已经进入 searchable 闭环”

核心实现点：

- 导入后处理显式执行 `sync_entities()` 和 `post_verify_index()`
- `post_verify_index()` 同时检查：
  - Nebula 中能否读到导入实体
  - ES 中 canonical 文档能否按 `_id={space}:{vid}` 取回
  - sample query 是否能从当前 space 命中新实体
  - registry `index_status` 是否已写回
- job state 固化 `index_status_snapshot` 和 `completion_summary`

影响的关键模块：

- `backend/app/services/imports/es_postprocess_service.py`
- `backend/app/services/search_v2/indexing_service.py`
- `backend/app/services/imports/job_service.py`
- `backend/tests/test_imports_service.py`

为什么必要：

- 如果导入只保证 Nebula 写入，不保证 searchable，那么后续开发仍然会遇到“导入完成但搜索不到”的灰色状态，无法作为正式回归基线。

### 4.3 D3 demo_kg canonical backfill 完成

改动目标：

- 把历史默认大 space `demo_kg` 恢复到 strict canonical search 的全量可搜索状态

核心实现点：

- backfill 脚本增加 `legacy_es_rewrite` 快路，把旧 ES 中“无 `space_name` 文档”重写为 canonical ES 文档
- backfill admin ES timeout 提升到 30s，避免大批量 bulk timeout
- 进度、覆盖率、verify 结果、completion snapshot 全部写入 state / summary / registry
- check 脚本统一汇总 state、summary、registry、log 和 legacy 文档计数

影响的关键模块：

- `backend/scripts/backfill_es_spaces.py`
- `backend/scripts/check_demo_kg_backfill.py`
- `backend/app/clients/es_client.py`
- `backend/app/services/search_v2/indexing_service.py`
- `backend/app/services/spaces/index_status_service.py`

为什么必要：

- `demo_kg` 是当前环境里最大的历史 space。若它仍停留在 `verified_partial`，则 strict multi-space canonical search 对真实大图场景不算完成。

### 4.4 D4 前端 per-space session 治理收紧

改动目标：

- 防止切换 space 后旧请求、旧候选、旧 graph 状态串入当前会话

核心实现点：

- API 层和 hooks 改为显式透传 `spaceName`
- 请求不再依赖“全局 store 在请求发出时临时注入 current space”这一隐式前提
- 旧请求即使晚返回，也只会绑定原始 `requestSpace`，随后被 `activeSpaceRef` / `scopeKey` / `scopeVersionRef` stale guard 丢弃
- 多实体槽位、本地 suggest/raw-id suggest、候选预览、graph/discovery expand、relation type catalog 均在切 space 时 reset 或加 stale guard
- `useSpaceSwitchCoordinator` 把切 space 变成显式流程：persist -> reset -> refresh readiness -> unblock

影响的关键模块：

- `frontend/src/api/http.ts`
- `frontend/src/api/kg.ts`
- `frontend/src/features/space/store.ts`
- `frontend/src/features/space/hooks/useSpaceSwitchCoordinator.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/LeftSearchPanel.tsx`
- `frontend/src/hooks/useSuggest.ts`
- `frontend/src/hooks/useRawIdSuggest.ts`
- `frontend/src/hooks/useEdgeSuggest.ts`
- `frontend/src/hooks/useDiscoveryCandidateResults.ts`
- `frontend/src/hooks/useGraphData.ts`
- `frontend/src/hooks/useDiscoveryGraphState.ts`
- `frontend/src/hooks/useEntityTypeOptions.ts`

为什么必要：

- 后端已经严格按 current space 查询。如果前端 session 仍允许旧 space 异步结果回写，就会造成“请求是对的，但页面展示串 space”的假象，验收无法成立。

## 5. 关键代码与模块清单

### 5.1 后端

| 文件路径 | 文件作用 | 为什么关键 |
| --- | --- | --- |
| `backend/app/core/space_context.py` | 解析并绑定 request-scoped current space | 定义 `X-KG-Space` 是唯一覆盖入口，决定全链路 strict multi-space 语义 |
| `backend/app/main.py` | middleware 绑定 current space，并回写响应头 `X-KG-Space` | 所有下游服务都依赖这里完成 request 级空间绑定 |
| `backend/app/routers/spaces.py` | `/api/spaces`、`/api/spaces/current` | readiness 对外正式出口 |
| `backend/app/services/spaces/readiness_service.py` | readiness / `space_meta` 唯一派生器 | D1 的核心收口点 |
| `backend/app/services/spaces/index_status_service.py` | `index_status` 分类、coverage 计算、completion snapshot | readiness 与 backfill / import searchable 的桥梁 |
| `backend/app/services/spaces/registry_service.py` | registry 读写与默认 space 注册 | readiness 真相存储入口 |
| `backend/app/clients/es_client.py` | ES canonical `_id`、`space_name` filter、count / mget / bulk upsert | 定义 strict canonical ES 合同 |
| `backend/app/services/search_v2/indexing_service.py` | canonical doc 构造、sync、verify、count、batch scan | import searchable 与 backfill 的核心基础设施 |
| `backend/app/services/search_v2/service.py` | `/api/search`、`/api/suggest`、`/api/suggest_raw_id` 主逻辑 | 线上候选搜索正式主链路 |
| `backend/app/services/discovery_entity_candidate_service.py` | `/api/discovery/entity_candidates` | 候选搜索与 discovery 候选页共用同一 ES v2 合同 |
| `backend/app/services/imports/es_postprocess_service.py` | 导入后的 ES sync / verify / registry 回写 | D2 闭环核心 |
| `backend/app/routers/imports.py` | import API 入口 | 导入请求强制落在 current space |
| `backend/scripts/backfill_es_spaces.py` | canonical backfill / legacy rewrite / registry 回写 | D3 主执行脚本 |
| `backend/scripts/check_demo_kg_backfill.py` | 读取 state / summary / registry / log 做 full-check | demo_kg 验收复查脚本 |
| `backend/tests/test_spaces_readiness_service.py` | readiness 状态映射单测 | 锁定 D1 合同 |
| `backend/tests/test_imports_service.py` | import searchable、job state、space freeze 单测 | 锁定 D2 合同 |
| `backend/tests/test_search_v2_indexing_service.py` | canonical doc、verify、space 显式传递单测 | 锁定 canonical ES 合同 |
| `backend/tests/test_backfill_es_spaces.py` | backfill completion / full_completion / state bucket 单测 | 锁定 D3 管理合同 |
| `backend/tests/test_es_client_space_aware.py` | ES `_id` 和 `space_name` filter 单测 | 锁定 strict multi-space query 隔离 |

### 5.2 前端

| 文件路径 | 文件作用 | 为什么关键 |
| --- | --- | --- |
| `frontend/src/features/space/store.ts` | current space store、switch nonce、switch phase | 前端 current space 正式状态源 |
| `frontend/src/features/space/hooks/useCurrentSpace.ts` | current space store hook | 应用层统一读取 current space |
| `frontend/src/features/space/hooks/useSpaceSwitchCoordinator.ts` | persist / reset / refresh / unblock 切换流程 | D4 收紧的协调器 |
| `frontend/src/features/space/hooks/useSpaces.ts` | 刷新 `/api/spaces` 与 `/api/spaces/current` | 前端 readiness 入口 |
| `frontend/src/features/space/api/space.ts` | space 相关 API | current space / default space 解析入口 |
| `frontend/src/api/http.ts` | 统一注入 `X-KG-Space` | 前端所有 KG 请求的空间绑定基线 |
| `frontend/src/api/kg.ts` | search / suggest / graph / discovery API 显式透传 `spaceName` | 避免隐式 current space 注入漂移 |
| `frontend/src/App.tsx` | current space 切换、space-scoped reset、stale guard 主编排 | D4 主入口 |
| `frontend/src/components/LeftSearchPanel.tsx` | 旧模块搜索入口、多实体槽位、space_meta 展示 | 搜索与 per-space session 最容易串状态的入口 |
| `frontend/src/hooks/useSuggest.ts` | 名称 suggest | 支持 `spaceName`、`scopeKey`、abort/request id |
| `frontend/src/hooks/useRawIdSuggest.ts` | raw-id suggest | 支持 `spaceName`、`scopeKey`、abort/request id |
| `frontend/src/hooks/useEdgeSuggest.ts` | edge suggest | 支持 `spaceName`、`scopeKey`、abort/request id |
| `frontend/src/hooks/useDiscoveryCandidateResults.ts` | discovery candidate 预览和结果列表 | 候选结果在切 space 时 reset，避免跨 space 残留 |
| `frontend/src/hooks/useGraphData.ts` | legacy graph/subgraph/expand 数据管理 | `scopeVersionRef` 和 abort 保证旧请求不回写 |
| `frontend/src/hooks/useDiscoveryGraphState.ts` | discovery graph expand/render 状态 | expand/probe 级 stale guard 关键点 |
| `frontend/src/hooks/useEntityTypeOptions.ts` | entity type options 缓存和 scope reset | 避免旧 space 的类型缓存残留到新 space |

## 6. 验收结果

### 6.1 编译/测试验收

本次实际复查命令与结果：

```bash
backend/.venv/bin/python -m compileall backend/app backend/scripts
```

结果：

- 执行通过

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest \
  backend.tests.test_spaces_readiness_service \
  backend.tests.test_imports_service \
  backend.tests.test_search_v2_indexing_service \
  backend.tests.test_backfill_es_spaces
```

结果：

- 41 项单测通过
- `OK`

```bash
cd frontend && npm run build
```

结果：

- `tsc -b && vite build` 通过
- Vite 生产构建完成，未见构建错误

### 6.2 readiness 验收

本次实际复查命令：

```bash
curl -sS -H 'X-KG-Space: demo_kg' http://127.0.0.1:8000/api/spaces/current
curl -sS -H 'X-KG-Space: it_space_218354' http://127.0.0.1:8000/api/spaces/current
curl -sS http://127.0.0.1:8000/api/spaces
```

关键结果：

- `demo_kg` `/api/spaces/current` 返回：
  - `registry_status=ready`
  - `graph_status=ready`
  - `search_status=full`
  - `coverage_pct=100.0`
  - `index_status.status=verified_nonempty`
  - `index_status.doc_count=5059789`
- `it_space_218354` `/api/spaces/current` 返回：
  - `registry_status=ready`
  - `graph_status=ready`
  - `search_status=full`
  - `coverage_pct=100.0`
  - `index_status.doc_count=4`
- `/api/spaces` 返回：
  - `demo_kg.graph_status=ready`
  - `demo_kg.search_status=full`
  - `it_space_218354.graph_status=ready`
  - `it_space_218354.search_status=full`
  - `it_space_218182.search_status=partial`
  - `it_space_217946.search_status=empty`

结论：

- readiness 合同已经按 registry / index snapshot 统一输出
- `demo_kg` 与当前验收用小 space 都处于可搜索状态

### 6.3 import searchable 验收

本次以真实导入作业 `job_ac0238e49a46` 为复查样本。

作业落盘状态来自：

- `.run/import-jobs/job_ac0238e49a46/state.json`
- `.run/import-jobs/job_ac0238e49a46/normalized_rows.csv`
- `.run/import-jobs/job_ac0238e49a46/job.log`

关键结果：

- `status=succeeded`
- `space_name=it_space_218354`
- `affected_entity_vids=[3375224]`
- `completion_summary.searchable=true`
- `completion_summary.search_status=full`
- `index_status_snapshot.status=verified_nonempty`
- `index_status_snapshot.doc_count=4`

本次实际复查命令：

```bash
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from app.services.search_v2 import indexing_service
print(indexing_service.fetch_entity_rows('it_space_218354', vids=[3375224]))
PY
```

Nebula 命中：

- `vid=3375224`
- `label='Codex Import Entity Final 1773375224'`
- `raw_id='CODEX:FINAL:1773375224'`

```bash
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from app.clients.es_client import ElasticsearchClient
client = ElasticsearchClient(index='kg_entity')
docs, took_ms = client.fetch_documents_by_ids('it_space_218354', [3375224])
print({'took_ms': round(took_ms, 3), 'docs': docs})
PY
```

ES 命中：

- `_id='it_space_218354:3375224'`
- `_source.space_name='it_space_218354'`
- `_source.entity_raw_id='CODEX:FINAL:1773375224'`

本次实际复查 API：

```bash
curl -sS -H 'X-KG-Space: it_space_218354' \
  'http://127.0.0.1:8000/api/suggest?q=Codex%20Import%20Entity%20Final&limit=5'

curl -sS -H 'X-KG-Space: it_space_218354' \
  'http://127.0.0.1:8000/api/suggest_raw_id?q=CODEX:FINAL:1773375224&limit=5'

curl -sS -H 'Content-Type: application/json' -H 'X-KG-Space: it_space_218354' \
  -d '{"q":"Codex Import Entity Final 1773375224","search_in_name":true,"search_in_description":false,"search_in_type":false,"search_in_raw_id":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains","include_edges":false}' \
  http://127.0.0.1:8000/api/search

curl -sS -H 'Content-Type: application/json' -H 'X-KG-Space: it_space_218354' \
  -d '{"q":"Codex Import Entity Final 1773375224","page":1,"page_size":10,"search_in_name":true,"search_in_description":false,"search_in_type":false,"search_in_raw_id":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains"}' \
  http://127.0.0.1:8000/api/discovery/entity_candidates
```

关键结果：

- `suggest` 命中 `vid=3375224`
- `suggest_raw_id` 命中 `entity_raw_id=CODEX:FINAL:1773375224`
- `search` 命中 `id=3375224`
- `entity_candidates` 命中 `vid=3375224`
- 上述 API 响应均返回：
  - `space_meta.space_name=it_space_218354`
  - `space_meta.search_status=full`

结论：

- 新导入实体已经形成 Nebula / ES / API 四处一致可见的 searchable 闭环

### 6.4 demo_kg full-search 验收

记录的最终 backfill 命令：

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/backfill_es_spaces.py \
  --space demo_kg --batch-size 5000 --verify --resume \
  --summary-json backend/state/demo_kg_backfill_full.json
```

说明：

- 该 backfill 主命令本次会话未重新执行
- 本次复查使用既有 run artifact：
  - `backend/state/demo_kg_backfill_full.json`
  - `backend/state/es_backfill_spaces.state.json`
  - `.run/space-registry/spaces.json`
- 本次实际重新执行了 check 脚本：

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/check_demo_kg_backfill.py --require-full
```

check 脚本关键结果：

- `status=verified_nonempty`
- `full_completion=true`
- `remaining_docs=0`
- `es_doc_count=5059789`
- `nebula_entity_count=5059789`
- `coverage_pct=100.0`
- `verify.ok=true`
- `verify.sample_ids_ok=true`
- `verify.sample_space_ok=true`
- `verify.sample_query_ok=true`

同时，本次 check 也确认：

- `legacy_missing_space_doc_count=5059789`

这表示：

- 旧无 `space_name` 文档物理仍存在于 `kg_entity`
- 但线上查询仍只认 canonical 合同，因为查询继续强制 `term space_name=<current_space>`

本次实际复查 demo_kg 查询：

```bash
curl -sS -H 'X-KG-Space: demo_kg' \
  'http://127.0.0.1:8000/api/suggest?q=allergic%20respiratory%20disease&limit=5'

curl -sS -H 'X-KG-Space: demo_kg' \
  'http://127.0.0.1:8000/api/suggest_raw_id?q=MONDO:0000771&limit=5'

curl -sS -H 'Content-Type: application/json' -H 'X-KG-Space: demo_kg' \
  -d '{"q":"allergic respiratory disease","search_in_name":true,"search_in_description":false,"search_in_type":false,"search_in_raw_id":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains","include_edges":false}' \
  http://127.0.0.1:8000/api/search

curl -sS -H 'Content-Type: application/json' -H 'X-KG-Space: demo_kg' \
  -d '{"q":"allergic respiratory disease","page":1,"page_size":10,"search_in_name":true,"search_in_description":false,"search_in_type":false,"search_in_raw_id":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains"}' \
  http://127.0.0.1:8000/api/discovery/entity_candidates
```

关键结果：

- `/api/suggest` 命中：
  - `vid=771`
  - `label='allergic respiratory disease'`
- `/api/suggest_raw_id` 命中：
  - `vid=771`
  - `entity_raw_id='MONDO:0000771'`
- `/api/search` 命中：
  - `id=771`
  - `label='allergic respiratory disease'`
- `/api/discovery/entity_candidates` 命中：
  - `vid=771`
  - `label='allergic respiratory disease'`
- 以上四类响应均返回：
  - `space_meta.space_name=demo_kg`
  - `space_meta.search_status=full`

结论：

- `demo_kg` 已恢复为 full canonical coverage
- 线上 demo_kg 查询已回到“全量 canonical searchable”状态

### 6.5 前端 session 行为验收

当前已完成的行为级验收事实：

- API 层所有 KG 请求支持显式透传 `spaceName`
- current space 切换后，`useSpaceSwitchCoordinator` 会先 reset space-scoped 状态，再 refresh `/api/spaces` 与 `/api/spaces/current`
- `App.tsx` 中搜索、详情、discovery、多实体图、路径应用等请求均捕获 `requestSpace`，晚返回结果若 space 已变化会被丢弃
- `useSuggest` / `useRawIdSuggest` / `useEdgeSuggest` 使用 request id、abort 和 `scopeKey` reset
- `useDiscoveryCandidateResults` 在 `scopeKey` 变化时 reset 预览、结果列表、selected ids
- `useGraphData` 使用 `scopeVersionRef`、abort 和 `scopeKey` reset，避免旧 subgraph/expand 回写
- `useDiscoveryGraphState` 使用 `scopeVersionRef`、abort 和 `scopeKey` reset，避免旧 expand/probe 回写
- relation type catalog、entity type options、多实体槽位、本地候选状态均已做 reset 或 stale guard

当前未执行项：

- 浏览器级 E2E harness 未执行
- 目前前端验收依据是：
  - 代码审查
  - `npm run build`
  - 运行态 API/space switch 合同复核

结论：

- 前端 per-space session 主链路已收紧
- 浏览器自动化回归仍是后续补项，不影响本轮主目标达成

## 7. 当前系统能力边界

### 7.1 当前已经保证的能力

- stable multi-space canonical search
- per-space import searchable
- `demo_kg` full canonical coverage
- space-aware API + frontend session 主链路
- 当前 space 可稳定切换
- 查询结果可严格按当前 space 隔离
- 新导入数据可进入 searchable 闭环
- `demo_kg` 已恢复为全量可搜索

### 7.2 当前尚未覆盖但不影响主目标的事项

- 缺少浏览器级 E2E harness
- 旧无 `space_name` 文档仍物理存在于 `kg_entity`
- 若后续要清理旧无 `space_name` 文档，那是独立数据清理任务，不属于本轮主验收前置条件

### 7.3 当前不应再依赖的行为

- 不应回滚到旧 `search_service` 作为主候选搜索链路
- 不应依赖 legacy fallback 来补 current space / canonical search 的空白
- 不应让在线接口承担 verify 真相来源
- 不应把旧无 `space_name` ES 文档重新纳入线上查询
- 不应在请求 body/query 中重新引入与 `X-KG-Space` 并行竞争的第二套 target space 语义

## 8. 后续建议

这里只记录收尾型建议，不引入新的大规划：

1. 补浏览器级 E2E harness，把切 space、suggest/search/discovery 串 space 防护固化成可重复自动验收。
2. 单独执行旧无 `space_name` 文档清理任务，减少 `kg_entity` 历史冗余存量。
3. 固化本轮回归命令为脚本或 runbook，避免后续回归靠人工拼接命令。
4. 继续拆分 `App.tsx`，但这只是后续工程化优化，不是当前主修复前置条件。

## 9. 回归基线清单

- [ ] 切换 space 后，`/api/spaces/current` 返回的 `space_name`、`graph_status`、`search_status` 与目标 space 一致。
- [ ] `/api/spaces` 中 `demo_kg.search_status=full`，`it_space_218354.search_status=full`。
- [ ] `/api/search` 返回的 `space_meta.space_name` 与请求 `X-KG-Space` 一致。
- [ ] `/api/suggest` 返回的 `space_meta.space_name` 与请求 `X-KG-Space` 一致。
- [ ] `/api/suggest_raw_id` 返回的 `space_meta.space_name` 与请求 `X-KG-Space` 一致。
- [ ] `/api/discovery/entity_candidates` 返回的 `space_meta.space_name` 与请求 `X-KG-Space` 一致。
- [ ] 小 space 导入作业完成后，job state 中 `completion_summary.searchable=true`。
- [ ] 小 space 导入后，Nebula / ES / search / suggest / suggest_raw_id / entity_candidates 都能命中新导入实体。
- [ ] `demo_kg.search_status=full`。
- [ ] `demo_kg` backfill check 返回 `coverage_pct=100.0`、`doc_count=5059789`、`nebula_entity_count=5059789`、`full_completion=true`。
- [ ] `demo_kg` 对 `MONDO:0000771` / `allergic respiratory disease` 的 search、suggest、suggest_raw_id、entity_candidates 均可命中。
- [ ] 前端切 space 后，旧 space 的搜索结果、候选、graph、relation type catalog 不会残留到新 space。

## 10. 附录：关键命令与样例输出

### 10.1 编译与单测

```bash
backend/.venv/bin/python -m compileall backend/app backend/scripts
```

样例结果：

```text
Listing 'backend/app'...
Listing 'backend/scripts'...
Compiling 'backend/scripts/check_demo_kg_backfill.py'...
```

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest \
  backend.tests.test_spaces_readiness_service \
  backend.tests.test_imports_service \
  backend.tests.test_search_v2_indexing_service \
  backend.tests.test_backfill_es_spaces
```

样例结果：

```text
Ran 41 tests in 0.073s
OK
```

```bash
cd frontend && npm run build
```

样例结果：

```text
vite v7.3.1 building client environment for production...
✓ built in 5.58s
```

### 10.2 backfill 与 check

记录的最终 backfill 命令：

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/backfill_es_spaces.py \
  --space demo_kg --batch-size 5000 --verify --resume \
  --summary-json backend/state/demo_kg_backfill_full.json
```

复查命令：

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/check_demo_kg_backfill.py --require-full
```

关键输出片段：

```text
status: verified_nonempty
full_completion: true
es_doc_count: 5059789
nebula_entity_count: 5059789
coverage_pct: 100.0
legacy_missing_space_doc_count: 5059789
```

### 10.3 readiness API

```bash
curl -sS -H 'X-KG-Space: demo_kg' http://127.0.0.1:8000/api/spaces/current
```

关键响应片段：

```json
{
  "space_name": "demo_kg",
  "registry_status": "ready",
  "graph_status": "ready",
  "search_status": "full",
  "coverage_pct": 100.0,
  "index_status": {
    "status": "verified_nonempty",
    "doc_count": 5059789
  }
}
```

```bash
curl -sS -H 'X-KG-Space: it_space_218354' http://127.0.0.1:8000/api/spaces/current
```

关键响应片段：

```json
{
  "space_name": "it_space_218354",
  "registry_status": "ready",
  "graph_status": "ready",
  "search_status": "full",
  "coverage_pct": 100.0,
  "index_status": {
    "status": "verified_nonempty",
    "doc_count": 4
  }
}
```

### 10.4 import searchable

导入作业样本：

```text
.run/import-jobs/job_ac0238e49a46/state.json
```

关键状态片段：

```json
{
  "job_id": "job_ac0238e49a46",
  "space_name": "it_space_218354",
  "status": "succeeded",
  "affected_entity_vids": [3375224],
  "index_status_snapshot": {
    "status": "verified_nonempty",
    "doc_count": 4
  },
  "completion_summary": {
    "searchable": true,
    "search_status": "full",
    "index_status": "verified_nonempty"
  }
}
```

Nebula / ES 复查命令：

```bash
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from app.services.search_v2 import indexing_service
print(indexing_service.fetch_entity_rows('it_space_218354', vids=[3375224]))
PY

PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from app.clients.es_client import ElasticsearchClient
client = ElasticsearchClient(index='kg_entity')
docs, took_ms = client.fetch_documents_by_ids('it_space_218354', [3375224])
print({'took_ms': round(took_ms, 3), 'docs': docs})
PY
```

关键输出片段：

```text
[{'vid': 3375224, 'label': 'Codex Import Entity Final 1773375224', ...}]
{'docs': [{'_id': 'it_space_218354:3375224', 'found': True, '_source': {...}}]}
```

### 10.5 demo_kg 查询样例

```bash
curl -sS -H 'X-KG-Space: demo_kg' \
  'http://127.0.0.1:8000/api/suggest?q=allergic%20respiratory%20disease&limit=5'
```

关键响应片段：

```json
{
  "items": [
    {
      "vid": 771,
      "label": "allergic respiratory disease"
    }
  ],
  "space_meta": {
    "space_name": "demo_kg",
    "search_status": "full"
  }
}
```

```bash
curl -sS -H 'X-KG-Space: demo_kg' \
  'http://127.0.0.1:8000/api/suggest_raw_id?q=MONDO:0000771&limit=5'
```

关键响应片段：

```json
{
  "items": [
    {
      "vid": 771,
      "entity_raw_id": "MONDO:0000771",
      "label": "allergic respiratory disease"
    }
  ],
  "space_meta": {
    "space_name": "demo_kg",
    "search_status": "full"
  }
}
```

```bash
curl -sS -H 'Content-Type: application/json' -H 'X-KG-Space: demo_kg' \
  -d '{"q":"allergic respiratory disease","search_in_name":true,"search_in_description":false,"search_in_type":false,"search_in_raw_id":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains","include_edges":false}' \
  http://127.0.0.1:8000/api/search
```

关键响应片段：

```json
{
  "nodes": [
    {
      "id": 771,
      "label": "allergic respiratory disease",
      "raw_id": "MONDO:0000771"
    }
  ],
  "space_meta": {
    "space_name": "demo_kg",
    "search_status": "full"
  }
}
```

```bash
curl -sS -H 'Content-Type: application/json' -H 'X-KG-Space: demo_kg' \
  -d '{"q":"allergic respiratory disease","page":1,"page_size":10,"search_in_name":true,"search_in_description":false,"search_in_type":false,"search_in_raw_id":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains"}' \
  http://127.0.0.1:8000/api/discovery/entity_candidates
```

关键响应片段：

```json
{
  "items": [
    {
      "vid": 771,
      "label": "allergic respiratory disease",
      "raw_id": "MONDO:0000771"
    }
  ],
  "space_meta": {
    "space_name": "demo_kg",
    "search_status": "full"
  }
}
```

## 未确认 / 未执行说明

- 浏览器级 E2E harness：未执行；当前仓库没有可直接复用的浏览器自动化验收脚本。
- `demo_kg` backfill 主命令：本次会话未重跑；本文依据既有 `summary/state/registry` 产物以及本次实际执行的 `check_demo_kg_backfill.py --require-full` 结果复查。
- 旧无 `space_name` 文档的物理清理：未执行；当前仅确认其仍存在且不会进入线上查询。

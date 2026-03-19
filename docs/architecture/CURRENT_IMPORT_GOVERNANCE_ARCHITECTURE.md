# Current Import Governance Architecture (Status as of 2026-03-19)

## 0. 文档定位与范围

本文档用于“当前重构成果收口与文档固化”，描述 import governance 相关架构在当前代码中的真实落点。

- 本文档描述的是**现状**，不是未来蓝图。
- 本文档聚焦 imports / cleanup / spaces / search / graph-discovery / team-ingestion / frontend import feature 的协作边界。
- 本文档不包含 AppShell/discovery/sqlite/runtime 的新增深改提案，仅记录当前边界和克制版后续建议。

---

## 1. 当前工程架构总览

当前 import governance 已形成“space-aware + batch-governed + cleanup-closed-loop”的主路径，核心不是单个模块，而是跨域协作闭环：

- `imports` 负责导入生命周期与执行闭环：upload/preview/draft/validate/job/freeze snapshot/postprocess，并向 batch ledger 写入“本批次引入项”的可清理依据。
- `cleanup` 负责针对 batch ledger 的可回收治理：请求校验、计划生成、冲突识别、执行分阶段推进、验证与 artifacts 归档。
- `spaces` 负责 current space 的治理入口与运行前提：space registry、模板化 provisioning、readiness/index_status，对 imports/cleanup/search/graph 提供一致的空间上下文。
- `search` / `search_v2` 负责 canonical entity 检索入口（`/api/search`、`/api/suggest`、`/api/suggest_raw_id`），并在 current space 下返回可检索实体面。
- `graph/discovery` 负责图查询与统一关系发现（`/api/graph/discovery`、`/api/subgraph`、`/api/expand`），对 space readiness 进行契约化回填。
- `team-ingestion` 是对 imports 主链路的受控自动化入口：复用 draft/job executor，不另起一套导入引擎，但额外增加 auth + idempotency + contract 约束。
- 前端 `features/import` 已成为 import 治理的容器层：在 Import Workspace 内串起 current space、draft flow、batch/cleanup flow，不改变主交互路径的前提下完成模块内聚。
- 运行时/状态/仓储边界当前是“file-store truth + repository seam + single-process worker”模式：先统一边界，再为后续更强 backend 预留迁移面。

---

## 2. 已完成的重构成果

### 2.1 阶段：batch/cleanup 主闭环

目标：
- 把“导入后可治理”从一次性脚本能力变为可复用闭环。

实际落地：
- import job 创建时同步创建 `ImportBatchRecord`。
- import 执行成功行写入 batch item ledger（entity/relation）。
- cleanup 可按 batch 发起，按 scope（`full_batch` / `relations_only`）执行。

架构提升：
- 从“导入即结束”升级为“导入-登记-治理”闭环。
- cleanup 不再脱离导入上下文，具备明确责任边界和状态追踪。

### 2.2 阶段：V1.5 explainability / artifacts / 幂等增强

目标：
- 提高可解释性与可追溯性，减少重复 ledger 写入风险。

实际落地：
- ledger 追加改为基于 `batch_id + item_key` 幂等写入。
- cleanup 增加 phase/failure_kind/failure_detail/duration_ms 等阶段化状态。
- cleanup artifacts 标准化输出（summary/conflicts/skipped/verify）。
- batch 记录带 `ledger_summary` 与一致性告警。

架构提升：
- 故障定位从“看日志猜测”变为“看结构化状态 + artifacts”。
- batch ledger 从“附属数据”升级为“治理可依赖输入”。

### 2.3 阶段：V2 planning + live graph reference scan

目标：
- 把 cleanup 决策前置并显式化，减少执行阶段不透明阻塞。

实际落地：
- cleanup planning 显式产出 `plan_summary`、blocked/deletable/conflicts。
- 冲突检测从仅 ledger 扩展到 ledger + live graph incident edge scan。
- live scan 与计划器耦合，而不是散落在删除执行分支。

架构提升：
- cleanup 从“边删边判断”转为“先规划再执行”。
- entity 删除边界更清晰，阻塞原因可结构化说明（`source=ledger/live_graph`）。

### 2.4 阶段：preview API + runtime shell + repository boundary

目标：
- 在不改现有运行时模型前提下，引入更清晰的演进边界。

实际落地：
- 新增 cleanup 预览 API：`POST /api/import/batches/cleanup-plan`。
- 预览只做规划，不创建 cleanup job，不触发删除。
- 引入 `job_runtime.QueuedWorkerRuntime` 作为 import/cleanup 共享 worker 壳层。
- 引入 `state_repository` 协议与 file-backed adapter，导入/批次/cleanup 状态走仓储边界。

架构提升：
- Preview/Execute 分层清晰，可在 UI 先评估再确认。
- runtime/repository 有统一接缝，后续替换 backend 不必重写业务逻辑。

### 2.5 阶段：cleanup 子域内部收口

目标：
- 降低 cleanup 内部状态分散与相互调用耦合。

实际落地：
- `cleanup_service` 负责 API-facing 请求校验、去重、job 创建与读取。
- `cleanup_planning_service` 负责 request normalize/validate + planning。
- `cleanup_executor_service` 负责分阶段执行、失败归因、artifact 落盘。
- `cleanup_graph_scan_service` 独立 live reference 扫描能力。

架构提升：
- cleanup 子域形成 service/planning/executor/scan 的内部分层。
- 模块变更可局部进行，不必牵动 imports 主执行链。

### 2.6 阶段：imports 主执行链内部收口

目标：
- 固化“冻结快照执行 + 后处理收敛 + 批次账本”的单一主链路。

实际落地：
- `job_service` 负责 draft 校验后创建 job + batch + execution snapshot。
- `executor_service` 负责按 compiled plan 执行写入、ledger 记录、失败行/目标级 artifacts。
- `postprocess_reconcile_service` 统一 metadata refresh / ES sync / verify 收敛逻辑。
- `cancel`、`startup interrupted recover`、`batch ledger consistency` 等运行态细节收口。

架构提升：
- 执行真相从前端提交 payload 转为 job snapshot 冻结产物。
- imports 主链路具备稳定生命周期状态机，便于测试与交接。

### 2.7 阶段：前端 `features/import` 容器化

目标：
- 将 Import 页面从“单文件组件堆叠”重构为容器 + hooks + 展示组件协作。

实际落地：
- `ImportWorkspace` 作为容器协调 current space、draft flow、job actions、cleanup flow、selection state。
- `ImportFlowPanels`/`ImportWorkspaceSidebar`/`BatchPanel` 拆分展示责任。
- hooks 分层为资源轮询、业务动作、页面选择状态。
- types 按 `draft/job/batch/cleanup` 分片并统一导出。

架构提升：
- 前端 import 子域可维护性明显提升，行为入口更可预测。
- 页面主交互保留（上传/预览/校验/提交 + batch cleanup），但实现边界更清晰。

---

## 3. 当前 imports 后端结构（职责边界）

### `job_service`

- 负责从 draft 创建 job 的入口逻辑：校验、actor 规范化、space 冻结、`job_id/batch_id` 生成。
- 写入 execution snapshot（draft snapshot + compiled_plan + input copy）并初始化 job/batch 记录。
- 提供 job 读取/列表/取消与启动恢复（interrupted jobs 标记）能力。

### `executor_service`

- 负责 import job 主执行链：按 target 批量写入 Nebula、记录成功/失败行、回写 job 状态。
- 负责 batch ledger 追加与 `ledger_summary` 一致性信息持久化。
- 在导入写阶段完成后调用 `postprocess_reconcile_service` 完成 postprocess 收敛。
- 通过 `job_runtime` 管理单进程 worker drain/ensure/startup recover。

### `postprocess_reconcile_service`

- 负责 postprocess 收敛编排：metadata refresh、ES 同步（job/space/none）、索引可见性 verify。
- 可用于 job 内部流程（`run_job_postprocess`）与独立 reconcile API（`reconcile_postprocess`）。
- 统一 completion summary 与 failure_stage 产出，避免后处理状态分散。

### `cleanup_service`

- 负责 cleanup API 对外入口的请求归一、权限边界校验、request_key 去重和 job 创建。
- 提供 batch/cleanup job 的空间内读取接口。
- 提供 preview 入口，调用 planner 但不产生执行副作用。

### `cleanup_planning_service`

- 负责 cleanup request 规范化、批次可清理性校验（test_data / cleanup_status / ledger existence）。
- 负责规划结果计算：deletable/blocker/conflict/warnings/verification_scope_note。
- 统一 ledger 冲突与 live graph 扫描结果聚合。

### `cleanup_executor_service`

- 负责 cleanup 分阶段执行：planning -> 删除关系 -> 删除实体 -> 删除 ES -> metadata -> reconcile -> verify。
- 负责 phase history、failure_kind/detail、final artifacts 写入。
- 负责 cleanup startup interrupted recovery 与 worker 启动。

### `state_repository`

- 提供 imports/cleanup 状态读写协议层（ImportJobState/ImportBatchRecord/CleanupJobRecord）。
- 当前实现为 file-backed adapter，底层仍调用 `file_store`。
- 价值在于抽离业务逻辑对具体存储介质的直接依赖。

### `file_store`

- 当前 file-based 真值层：`.run` 路径、JSON/CSV/JSONL 落盘、原子写、artifact/staging 清理。
- 负责 import 文件、draft、job snapshot、batch ledger、cleanup artifacts 的实际 I/O。
- 也是当前 repository adapter 的底层实现。

### `job_runtime`

- 提供通用 `QueuedWorkerRuntime` 壳层，封装 queued record 扫描、drain loop、线程生命周期。
- import executor 与 cleanup executor 复用同一 runtime 模式。
- 当前仍是单进程内存队列模型，不涉及分布式 claim/lease。

### 当前协作方式（摘要）

- 导入链路：`router -> job_service(create snapshot) -> executor_service(run) -> postprocess_reconcile_service -> batch/job state`
- 清理链路：`router -> cleanup_service(validate/create or preview) -> cleanup_planning_service -> cleanup_executor_service(run)`
- 状态链路：`service -> state_repository -> file_store -> .run`

---

## 4. 当前前端 import feature 结构

### 容器与展示分工

- `ImportWorkspace`：import 子域容器，负责空间上下文、flow 组合、跨面板状态协调。
- `ImportFlowPanels`：上传/targets/validate-plan 主流程展示面板。
- `ImportWorkspaceSidebar`：warnings、draft snapshot、job logs 侧边可观测面板。
- `BatchPanel`：batch 列表 + 详情治理总面板。
- `BatchListPanel`：batch 选择与多选（对应 BatchList 责任）。
- `BatchDetailPanel`：batch 详情 + cleanup 入口（对应 BatchDetail 责任）。
- `CleanupPlanPreviewPanel`：preview 结果与 confirm 入口（对应 CleanupPlanPreview 责任）。
- `CleanupResultPanel`：cleanup 结果、conflicts、verify、artifact 下载（对应 CleanupResult 责任）。

### hooks 分层

- 资源轮询层：`useImportPollingResource` + `useImportJobs` / `useImportBatches` / `useCleanupJobs`。
- 动作编排层：`useImportDraftFlow`、`useImportCleanupFlow`、`useImportJobActions`。
- 页面选择状态层：`useImportWorkspaceSelection`（selected job/batch/items/logs/tabs）。

### types 分片

- `types/import/draft.ts`：draft/preview/schema/compiled plan。
- `types/import/job.ts`：job 状态与 artifact。
- `types/import/batch.ts`：batch/ledger item。
- `types/import/cleanup.ts`：cleanup preview/job/conflict/artifacts。
- `types/import/index.ts` 统一导出，`types/import.ts` 作为外部入口。

### 交互稳定性

- 页面主交互未改为新范式，仍是原有治理路径增强版：
  - upload -> preview -> save draft -> validate -> submit job
  - batches 里执行 cleanup（新增 preview-confirm 主路径，同时保留 quick cleanup 兼容入口）
- 未改变前端用户交互契约，也未改动后端既有主要 API 契约。

---

## 5. 状态与持久化现状

### `.run` 关键状态目录（当前）

- `.run/import-staging/files/`：上传后的 CSV 暂存与 meta。
- `.run/import-drafts/`：draft 真值。
- `.run/import-jobs/<job_id>/`：job state、snapshot、input copy、job artifacts、logs/events。
- `.run/import-batches/`：batch record、items ledger、item key index。
- `.run/import-cleanup-jobs/`：cleanup record 与 artifacts。
- `.run/space-registry/`：spaces registry 真值（`spaces.json`）与 lock/audit。
- `.run/team-ingestion/`：team-ingestion submission 与 idempotency（按需生成）。

### `file_store` 与 `repository` 的关系

- `file_store` 是当前真实存储实现与 I/O 能力层。
- `state_repository` 是 imports/cleanup 状态仓储抽象层，目前 adapter 全部落到 `file_store`。
- 因此现状是“有仓储边界，但尚未替换底层介质”。

### 已开始走 repository 边界的状态

- `ImportJobState`（`import_job_states`）。
- `ImportBatchRecord` / `ImportBatchItem` 相关批次治理状态（`import_batches`）。
- `CleanupJobRecord` 及其读取/更新（`cleanup_jobs` / `cleanup_state`）。

### 仍以 file-based 为真值的状态

- 上传文件与文件 meta、draft 本体、job input snapshots、CSV/JSON artifacts。
- batch ledger 的 `items.jsonl` / `item_keys.json`。
- cleanup artifacts JSON 文件。
- spaces registry 与 team-ingestion idempotency/submission。

### 当前尚未迁 sqlite 的原因（现状说明）

- 当前代码已经显式把阶段目标限定在“边界抽离”而不是“运行时/存储迁移”。
- 运行时仍是 single-process worker + file-state，未引入 sqlite/postgres/redis/celery 依赖链。
- repository seam 已铺设，但尚未进入 backend 替换阶段；这是当前版本有意保持的风险可控策略，不是遗漏。

---

## 6. 当前验证体系

### backend tests

- 通过 `scripts/backend_pytest.sh` 统一在项目 venv 中执行 pytest。
- 覆盖 imports API/服务、cleanup preview 与执行边界、job closure contract、team-ingestion contract/idempotency 等关键后端行为。
- 主要验证“状态转换正确性 + 空间隔离 + 失败语义 + artifacts 合约”。

### mock e2e

- `frontend/e2e/specs/08-import-minimal.spec.ts`、`09-import-batches-cleanup.spec.ts` 通过 route mock 验证前端流程与状态展示。
- 重点验证 Import Workspace 主流程、batch cleanup 预览与结果展示、artifact 按钮可见性等 UI 合约。
- 不验证真实 Nebula/ES 链路正确性。

### quick cleanup 兼容 e2e

- `09-import-batches-cleanup.spec.ts` 中 `@quick-cleanup` 场景。
- 验证在 preview-confirm 主路径存在的同时，Quick Cleanup 兼容入口仍可用，避免回归断裂。

### real smoke

- `scripts/smoke_import_cleanup.py` 走真实后端链路：
  - 创建隔离测试 space
  - 执行 import job
  - 运行 cleanup preview + execute
  - 验证 search/suggest 可见性变化
- 用于补 mock e2e 无法覆盖的真实系统联动风险。

### build / type check

- `frontend` 使用 `npm run build`（`tsc -b && vite build`）作为类型与构建基线。
- 后端以 pytest 与脚本化 smoke 为主进行回归校验。

---

## 7. 当前推荐使用路径（团队实践）

- 推荐治理路径：`Preview Cleanup Plan -> Confirm Cleanup`。
- `Quick Cleanup` 定位：兼容入口与应急路径，不是默认推荐路径。
- 建议优先在隔离 test space 执行导入与治理，避免默认 project space 混入测试数据。
- 每次 cleanup 后建议优先查看：
  - `plan_summary` 与 `verification_scope_note`
  - `summary.json` / `verify_summary.json`
  - `conflicts.json` 与 warning messages
- 对“已存在历史 batch 但无 ledger”的数据，应按 read-only 历史数据看待，不把 cleanup 当作可完整回滚工具。

---

## 8. 当前已知边界与限制（正式 handover 口径）

- 当前核心状态仍是 file-based state。
- import/cleanup worker 仍是单机单进程线程队列，不具备分布式并发 claim/lease 能力。
- cleanup 不是事务型操作，失败时可能出现部分删除已生效。
- live graph scan 只扫描配置 `EDGE_TYPE` 的 incident edges，且受 `IMPORT_CLEANUP_LIVE_SCAN_MAX_EDGES` 上限影响。
- cleanup preview 不落盘、不创建 cleanup job、无 plan artifacts 持久化。
- preview 与 execute 之间存在漂移可能，execute 会在执行前重算计划。
- 历史导入若没有 batch ledger，cleanup 不承诺完全恢复或补算。
- 当前尚未迁移到 sqlite / postgres / 更强 repository backend。

---

## 9. 后续建议（克制版）

- 在现有 mock e2e 基线外，补一层真实浏览器+真实后端环境的稳定化回归（重点覆盖 import + cleanup 主链路）。
- 将 `docs/governance/IMPORT_BATCH_GOVERNANCE_TEST_RUNBOOK.md` 与本状态文档作为固定入口，减少口口相传依赖。
- 延续 runtime/repository 收口：优先扩大 repository 覆盖面，再评估 backend 替换，而不是直接跳到重型迁移。
- 在 execute 前增加轻量差异提示（当 preview 与当前状态明显变化时给出用户提示）。
- 如业务确有复核需求，再评估 preview 持久化；否则保持 preview 轻量与无副作用语义。

---

## 10. 模块边界短版摘要（可贴 PR/交接）

### 已收口模块

- 后端：imports 主执行链（job_service -> executor_service -> postprocess_reconcile）已形成稳定闭环。
- 后端：cleanup 子域（cleanup_service / planning / executor / graph_scan）已完成内部职责分层。
- 前端：`features/import` 已完成容器化拆分，主流程与治理面板职责分离。

### 当前最重要工程边界

- 状态真值仍在 `.run` 文件体系，repository 目前是 file-backed seam。
- worker 运行模型仍是单进程队列，不是分布式任务系统。
- cleanup 具备规划与 explainability，但不是事务回滚系统。

### 当前推荐回归基线

- 后端：`scripts/backend_pytest.sh`（imports/cleanup/team-ingestion 相关用例）。
- 前端：`npm run e2e:import-mock` + `npm run e2e:quick-cleanup`。
- 联调：`python3 scripts/smoke_import_cleanup.py`。
- 构建：`cd frontend && npm run build`。

### 当前不建议立即动的区域

- 不建议立即发起 sqlite/postgres/celery 级别运行时迁移。
- 不建议同时改 AppShell/discovery 主链路与 imports/cleanup 治理链路。
- 不建议在无额外回归护栏下重写 cleanup execute 语义。

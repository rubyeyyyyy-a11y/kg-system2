# Backend Architecture

## 分层结构

后端当前按“职责分层”组织，目录与职责对应如下：

```text
routers
  -> 解析 HTTP 参数、鉴权/请求上下文、返回 response model
  -> 只调用 services

services
  -> 业务编排、流程控制、错误语义、跨模块聚合
  -> 可以依赖 platform / repository / state / runtime

platform
  -> 底层能力封装，例如 graph traversal、metadata fallback、search helper
  -> 不理解 HTTP，不读 request

repository / state
  -> 文件、状态、注册表、草稿、job snapshot、审计持久化
  -> 当前主要实现位于：
     - `app/services/imports/file_store.py`
     - `app/services/imports/state_repository.py`
     - `app/services/spaces/registry_service.py`
     - `app/services/spaces/audit_service.py`
     - `app/services/team_ingestion/idempotency_store.py`

runtime
  -> 后台任务执行、队列轮询、worker 生命周期
  -> 当前主要实现位于 `app/services/imports/job_runtime.py`
```

## 各层职责

### `routers`

- 负责 HTTP 入参、query/path/body 解析
- 负责 response model 组装
- 负责调用 service 并把 service 错误转成 HTTP 语义

### `services`

- 负责用例级编排
- 负责“先做什么、后做什么、失败如何处理”
- 负责聚合多个底层模块的结果

### `platform`

- 提供图遍历、metadata fallback、底层搜索/图能力
- 提供可被多个 service 复用的无 HTTP 上下文能力

### `repository / state`

- 提供文件读写、registry、draft/job state、artifact 状态访问
- 把本地文件结构和原子写入细节收口在固定模块里

### `runtime`

- 提供排队执行与 worker 生命周期控制
- 只被 service 层间接驱动，不暴露给 router

## 禁止行为

- `router` 不得直接调用 `platform`
- `service` 不得直接操作本地文件；必须通过 `repository/state`
- `runtime` 不得被 `router` 直接调用
- `platform` 不得依赖 HTTP / request

## 本轮已修正的明显越界

- `backend/app/routers/search.py`
  - 之前直接调用 `platform.metadata.entity_catalog_service`
  - 现已改为调用 `services/entity_type_service.py`

- `backend/app/routers/imports.py`
  - artifact 下载、job log、failed rows 的路径解析原先直接在 router 内处理
  - 现已下沉到 `job_service` / `cleanup_service` / `draft_service`

- `backend/app/services/team_ingestion/contract_service.py`
  - CSV header 读取不再直接 `open()`，改走 `imports/file_store.py`

- `backend/app/services/team_ingestion/failures_service.py`
  - failed rows 读取不再直接 `open()`，改走 `imports/file_store.py`

## 当前保留的结构性 TODO

- `backend/app/services/team_ingestion/gateway_service.py`
  - 仍包含流式上传落盘逻辑。
  - 已加 TODO 注释。
  - 原因：这里同时承担上传体积限制、UTF-8 合约校验、SHA256 计算与 staged file 原子落盘，直接抽离风险较高。

- `repository/state` 角色目前有一部分仍位于 `app/services/...`
  - 这是历史结构遗留，不影响职责判定，但后续若继续治理，可考虑物理迁移到独立目录。

## 运行态目录

运行态统一收口到仓库根目录 `runtime/`：

- `runtime/.run/`：registry、import jobs、pid 等运行态状态
- `runtime/logs/`：backend/frontend/ops 运行日志
- `runtime/artifacts/`：保留给运维或批处理产物

这套路径约束同时被脚本、backend 配置和 runbook 共享。

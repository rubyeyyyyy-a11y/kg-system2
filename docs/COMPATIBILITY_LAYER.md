# Compatibility Layer

本文档收口所有带 `COMPAT(2026-03)` 标记的兼容代码，避免历史桥接逻辑继续变成“隐式知识”。

## 当前 COMPAT 项

### 入口兼容

- `dev.sh`
  - 原因：历史上一键前后台前台运行入口仍有人使用。
  - 删除条件：团队完全切换到 `scripts/dev/*`。

- `scripts/bootstrap_env.sh`
- `scripts/start_stack.sh`
- `scripts/stop_stack.sh`
- `scripts/check_stack.sh`
- `scripts/verify_stack.sh`
- `scripts/smoke_api.sh`
- `scripts/backend_pytest.sh`
- `scripts/smoke_import_cleanup.py`
  - 原因：保留旧的顶级 `scripts/*` 调用路径。
  - 删除条件：README、runbook、人工习惯与外部引用全部切到 `scripts/dev|verify|test/*`。

### Python 入口兼容

- `backend/main.py`
  - 原因：保留 `backend.main:app` 导入面。
  - 删除条件：所有运行命令与外部工具统一为 `app.main:app`。

- `backend/app/__init__.py`
- `backend/app.py`
  - 原因：保留 `from app import app` 与 `app:app` 的旧入口习惯。
  - 删除条件：所有入口统一使用 `app.main:app`。

### API 兼容

- `backend/app/routers/detail.py`
  - 项：`/api/node_detail` alias
  - 原因：兼容旧客户端访问路径。
  - 删除条件：确认客户端全部切到 `/api/node/{vid}`。

### Import payload / snapshot 兼容

- `backend/app/schemas/imports.py`
  - 项：`mode -> workspace_mode` 请求兼容
  - 原因：旧请求仍可能发送 `mode`
  - 删除条件：所有请求负载停止发送 `mode`

- `backend/app/services/imports/models.py`
  - 项：`field_mappings -> identity/property mappings`
  - 原因：兼容旧 draft / compiled plan 快照
  - 删除条件：历史快照完成迁移或失效

- `backend/app/services/imports/models.py`
  - 项：`mode <-> workspace_mode` 双向兼容
  - 原因：兼容旧 draft / job / compiled plan 持久化记录
  - 删除条件：存量状态文件完成迁移且不再被读取

### Frontend 路径兼容

- `frontend/src/features/discovery/DiscoveryWorkspace.tsx`
  - 原因：旧 import 路径仍可用，实际容器已迁到 `container/`
  - 删除条件：所有 import 语句切到 `features/discovery/container/DiscoveryWorkspace`

- `frontend/src/features/import/ImportWorkspace.tsx`
  - 原因：旧 import 路径仍可用，实际容器已迁到 `container/`
  - 删除条件：所有 import 语句切到 `features/import/container/ImportWorkspace`

- `frontend/src/features/import/types/import.ts`
  - 原因：保留旧的扁平 type 入口
  - 删除条件：调用方全部切到 `features/import/types/import/*`

## 不属于 COMPAT、但需要关注的 TODO

- `backend/app/services/team_ingestion/gateway_service.py`
  - 已标注 TODO，但不是历史兼容桥。
  - 它是当前仍未完全收口到 repository 的文件落盘逻辑。

## 使用规则

- 新增兼容代码时，必须附带 `COMPAT(YYYY-MM): 原因，remove after 条件`
- 没有删除条件的兼容代码，不应入库
- 兼容桥只允许“转发/映射/双读”，不允许继续承载新业务逻辑

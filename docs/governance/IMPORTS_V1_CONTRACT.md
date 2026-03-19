# Imports V1 Contract Freeze

本文档冻结 `/api/import/*` 子系统的一期工程契约。目标是让当前实现具备稳定交接、稳定维护、稳定演进的基线，而不是继续扩功能。

当前稳态目标：

- 单文件 CSV 最大支持 `100MB`
- 单 draft 总大小最大支持 `200MB`
- preview 只展示样本，不做高成本全量统计
- validate 只做格式 / mapping / 规则层检查，不保证最终写入成功
- 仍保留总行数保护，避免窄行超长 CSV 把 job 时长拉到不可控

本轮默认预算：

- `IMPORT_MAX_UPLOAD_BYTES=104857600`
- `IMPORT_MAX_DRAFT_TOTAL_BYTES=209715200`
- `IMPORT_MAX_DRAFT_FILES=5`
- `IMPORT_MAX_SAMPLE_ROWS=300`
- `IMPORT_MAX_JOB_ROWS=300000`
- `IMPORT_MAX_FAILED_ROWS_WRITTEN=3000`

## 1. 子系统目录结构

后端：

- `backend/app/routers/imports.py`
- `backend/app/schemas/imports.py`
- `backend/app/services/imports/`

前端：

- `frontend/src/features/import/`

运行目录：

- `.run/import-staging/files/<file_id>/`
- `.run/import-drafts/<draft_id>.json`
- `.run/import-jobs/<job_id>/`

## 2. 生命周期

Draft 生命周期：

- `files_uploaded`
- `preview_ready`
- `mapped`
- `validated`

Job 生命周期：

- `queued`
- `running`
- `post_metadata_refresh`
- `post_es_sync`
- `succeeded`
- `failed_import`
- `failed_postprocess`
- `cancelled`

原则：

- Draft 只描述可编辑配置，不直接驱动执行。
- Compiled Import Plan 在 validate / submit 时冻结。
- Job 只消费 job snapshot 和 `compiled_plan.json`。

## 3. staging / draft / snapshot 关系

- staging：上传后的原始 CSV 暂存区。
- draft：用户正在编辑的导入定义。
- job snapshot：提交 job 时复制出的不可变执行输入。

边界：

- 执行器不能回读 draft 的可变状态。
- 执行器不能回读 staging 原始文件。
- 执行器只读 `.run/import-jobs/<job_id>/input/*` 和 `.run/import-jobs/<job_id>/compiled_plan.json`。

## 4. 事实来源定义

- Draft 真相来源：
  `.run/import-drafts/<draft_id>.json`
- Draft 不是真正在跑的执行输入；它只是可编辑定义的持久化真相来源。
- Job 真相来源：
  `.run/import-jobs/<job_id>/state.json`
- Plan 真相来源：
  `.run/import-jobs/<job_id>/compiled_plan.json`
- 这里的 `compiled_plan.json` 是 submit 时冻结进 job snapshot 的执行真相来源。
- Job 事件来源：
  `.run/import-jobs/<job_id>/events.jsonl`
- 失败复盘来源：
  `.run/import-jobs/<job_id>/failed_rows.csv`

UI 只是展示层，不是真相来源。

space 绑定补充：

- Draft 的 `space_name` 只来自当前 request-level current space。
- Job 的 `space_name` 只来自 draft / submit 时冻结的 current space。
- Job 执行器只认 job snapshot 中冻结下来的 `space_name` 与 `compiled_plan.json`。
- imports v1 不通过 body 散落传 `target_space` 作为主机制。

## 5. 持久化格式契约

### 5.1 Draft

文件：

- `.run/import-drafts/<draft_id>.json`

顶层稳定字段：

- `format_version`
- `draft_id`
- `status`
- `mode`
- `file_ids`
- `discriminator_column`
- `mapping`
- `update_strategy`
- `schema_options`
- `postprocess_options`
- `created_at`
- `updated_at`
- `validation`

说明：

- `format_version=imports-v1` 是 v1 设计锚点。
- v1 不删字段，非必要不改字段名。
- `space_name` 是 draft 所属 space 的冻结字段，不允许 UI 自己再维护并行真相。
- `validation.compiled_plan` 只是最近一次 validate 产物；job 提交后真正执行依据是 job snapshot 下的 `compiled_plan.json`。
- `ImportFileRecord.row_count` 允许延迟补全；upload 结束时可以是 `0` 且 `row_count_pending=true`，后续在 preview / validate / submit 相关扫描中补齐。

### 5.2 Compiled Import Plan

文件：

- `.run/import-jobs/<job_id>/compiled_plan.json`

顶层稳定字段：

- `format_version`
- `plan_id`
- `space_name`
- `template_type`
- `integration_scope`
- `mode`
- `file_ids`
- `discriminator_column`
- `targets`
- `schema_create_plan`
- `update_strategy`
- `rank_generation_strategy`
- `postprocess_options`
- `warnings`
- `integration_level`
- `compiled_at`

执行器真正依赖的字段：

- `mode`
- `discriminator_column`
- `targets`
- `schema_create_plan`
- `postprocess_options`
- `rank_generation_strategy`

展示辅助字段：

- `warnings`
- `integration_level`

`targets[*]` 稳定字段：

- `object_type`
- `object_name`
- `discriminator_value`
- `field_mappings`
- `property_types`
- `identity_fields`
- `update_fields`
- `create_fields`
- `integration_level`
- `warnings`

### 5.3 Job state.json

文件：

- `.run/import-jobs/<job_id>/state.json`

顶层稳定字段：

- `format_version`
- `job_id`
- `draft_id`
- `status`
- `created_by`
- `mode`
- `plan_id`
- `file_ids`
- `compiled_plan_path`
- `failed_rows_path`
- `normalized_rows_path`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`
- `cancel_requested`
- `total_rows`
- `processed_rows`
- `success_rows`
- `failed_rows`
- `warnings`
- `integration_warnings`
- `integration_level`
- `error_message`
- `interrupted`
- `metadata_refreshed`
- `es_sync_skipped`
- `failed_rows_truncated`
- `cancel_effective_at_batch`
- `affected_entity_vids`
- `affected_schema_objects`

说明：

- `space_name` / `template_type` / `integration_scope` 让 compiled plan 在交接与审计场景下可以脱离 UI 独立理解。
- `status` 是 job 主状态机唯一真相来源。
- `interrupted=true` 表示启动修正判死，不表示续跑。
- `failed_rows_truncated=true` 表示失败行文件只保留前 N 条。

### 5.4 events.jsonl

文件：

- `.run/import-jobs/<job_id>/events.jsonl`

每行 JSON 稳定字段：

- `event_type`
- `ts`
- `level`
- `message`
- `context`

当前典型 `event_type`：

- `job_queued`
- `job_started`
- `row_failed`
- `job_failed_rows_generated`
- `job_succeeded`
- `job_failed`
- `cancel_requested`
- `cancel_ignored`
- `job_cancelled`

约束：

- 这是 job 运行期事件流，不是运维清理日志。
- staging/job artifact 清理行为只写应用日志，不倒写历史 `events.jsonl`。

### 5.5 failed_rows.csv

文件：

- `.run/import-jobs/<job_id>/failed_rows.csv`

列顺序：

- 原始 CSV 全部列，保持原始顺序
- 再追加系统列：
  `__file_id`, `__row_number`, `__error`, `__target_object`, `__target_type`

复盘必需列：

- 原始业务列
- `__file_id`
- `__row_number`
- `__error`
- `__target_object`
- `__target_type`

mixed 模式：

- 使用 `__target_object` + `__target_type` 标识最终目标对象

截断表达：

- `state.json.failed_rows_truncated=true`
- 且 `failed_rows.csv` 中追加一条截断提示行

## 6. API 契约

### 6.1 成功响应

- `POST /api/import/files`
  返回上传元数据，不返回服务端存储路径；upload 阶段只做流式落盘和轻量 metadata 探测，不做全量 decode / row_count / validate。
- `POST /api/import/preview`
  返回 `columns`, `sample_rows`, `inferred_mode_candidates`, `warnings`；preview 默认是 sample-only 语义。
- `GET /api/import/schema`
  返回当前可见 tag / edge type / property
- `POST /api/import/schema/plan`
  返回 `schema_create_plan`, `warnings`, `integration_warnings`
- `POST /api/import/drafts`
  返回 draft 全量快照
- `GET /api/import/drafts/{draft_id}`
  返回 draft 全量快照
- `POST /api/import/drafts/{draft_id}/validate`
  返回 `passed`, `errors`, `warnings`, `integration_warnings`, `semantic_notes`, `compiled_plan`
- `POST /api/import/jobs`
  返回 job 摘要
- `GET /api/import/jobs`
  返回 job 列表
- `GET /api/import/jobs/{job_id}`
  返回 job 详情
- `GET /api/import/jobs/{job_id}/logs`
  返回 job 日志行
- `GET /api/import/jobs/{job_id}/failed_rows`
  返回 CSV 文件下载
- `POST /api/import/jobs/{job_id}/cancel`
  返回取消后的 job 状态

### 6.2 错误响应

imports 子系统内部尽量统一为：

```json
{
  "detail": {
    "error_code": "IMPORT_*",
    "message": "human readable message",
    "field": "optional_field_name",
    "extra": {}
  }
}
```

重点场景：

- upload
- submit job
- download failed rows
- draft/job not found
- file type / row limit / file count limit
- draft total size limit

说明：

- v1 不要求全项目统一错误格式，只冻结 imports 子系统内部契约。

## 7. 固定用户语义

### 7.1 Validate 固定语义

固定文案：

> Validate checks CSV format, mapping, and import rules only. It is not a Nebula existence preflight and does not guarantee final write success.

要求：

- 后端 validate 响应通过 `semantic_notes` 返回
- 前端 validate 区域固定展示
- validate 采用逐文件、逐行流式扫描，只保留有限错误样本，并返回 `scanned_rows`, `error_rows`, `errors_truncated`

### 7.1.1 Preview 固定语义

固定含义：

- preview 只展示样本行，不代表全量文件一定可 validate / import 成功
- 后端最多返回 `IMPORT_MAX_SAMPLE_ROWS`
- 前端默认请求前 `200` 行
- warning 中必须明确表达 `sample_rows capped` 与 `preview is sample-only`

### 7.2 Integration Warning 固定含义

固定含义：

- 导入成功不等于自动进入当前搜索、discovery、graph 主链路
- `integration_level` 描述的是产品集成程度，不是写入成功与否

必须贯穿展示：

- schema create plan
- validate 结果
- job detail / success summary

### 7.3 Success Summary 固定含义

使用 `job detail / success summary`，不要求独立成功页。

术语固定含义：

- `imported successfully`
  仅表示 job 写入与后处理在 v1 边界内成功完成
- `fully integrated`
  当前对象进入现有主链路能力
- `partially integrated`
  当前对象部分兼容现有能力，但不是全主链路接入
- `import-only`
  仅保证写入和导入管理可见，不承诺产品主链路可见

## 8. 运行边界

- 单 worker 串行执行
- 单 space 假设，前端不传 `target_space`
- interrupted job 启动后只判死，不续跑
- metadata 后处理只在 job 末尾统一执行，且强制 DB source
- ES 后处理只针对实体增量 upsert，不处理边
- edge-only job 默认跳过 ES postprocess
- 不做 delete
- 不做 destructive schema migration
- 不做多 job 并发
- 不做断点续跑

## 9. created_by / updated_by 规则

- `created_by` 由 job 提交方传入
- `created_by` 经 `validate_updated_by` 校验后，作为本 job 的 actor 固化
- 执行阶段写入图上的 `updated_by` 统一取 job actor
- 允许字符以现有 `sanitize_text` / `validate_updated_by` 为准
- 最大长度为当前系统 `updated_by` 限制
- 校验失败使用 imports/validation 错误契约返回

## 10. 最小运维说明

查看当前 jobs：

- 读取 `.run/import-jobs/*/state.json`
- 或调用 `GET /api/import/jobs`

判断 job 卡死/失败：

- 若应用重启后 `queued/running/post_metadata_refresh/post_es_sync` 会被修正为失败态
- 失败真相来源是 `state.json.status`

手动清理：

- staging：`.run/import-staging/files/*`
- drafts：`.run/import-drafts/*.json`
- jobs：`.run/import-jobs/*`

注意：

- 手动清理前优先保留 `state.json` 和 `compiled_plan.json`
- 自动清理只写应用日志，不写回历史 job events

## 11. 已知限制

- validate 不做 Nebula 存在性预检查
- 执行器仍为逐行 nGQL，吞吐有限
- 单 worker 串行，无并发 job
- 无 auth / 权限体系，`created_by` 可信度有限
- 无断点续跑
- 无 importer adapter

## 12. V1 稳定性取舍

- v1 不改字段名：
  稳定性和兼容性优先于命名美化
- validate 不承诺最终写入成功：
  逐行写入受运行时数据和数据库状态影响
- 清理行为不写回历史 job events：
  运维行为不应污染 job 执行事实流
- v1 不做并发、不做断点续跑：
  先保证状态机和事实来源简单稳定
- integration warning 必须贯穿三处：
  防止用户误解“导入成功 = 自动产品可见”

## 13. 测试交付定义

验收最小闭环：

1. 后端单测通过
2. imports API 集成测试通过
3. 前端 build 通过
4. 本文档可覆盖交接最小信息闭环

## 14. 二期演进摘要

只写设计，不在 v1 中实现。

### 14.1 从逐行 nGQL 到批处理执行

- 保持 Draft / Compiled Plan / Job 三层不变
- 在执行层引入批处理 planner
- 将当前 `import_ngql_service` 抽象为 adapter 接口
- 先支持同 target 合批，再支持 schema-aware 分桶执行

### 14.2 存在性预检查

- 在 validate 前增加可选 preflight
- 对 VID / edge key 做存在性采样或批量探测
- 结果写入 validate 附加报告，不改变 validate 基本语义

### 14.3 importer adapter 演进

- 当前执行器可被 `ImporterAdapter` 接口替换
- 默认 adapter 仍是逐行 nGQL
- 后续接入 offline importer / bulk importer 时，只替换 adapter，不改 Draft / Job contract

### 14.4 多 job 并发

- 先引入 job-level 锁和 postprocess barrier
- metadata refresh / ES sync 应与 job 执行解耦
- 并发执行不应破坏 `state.json` 和 postprocess 一致性

### 14.5 auth / 审计主体增强

- 将 `created_by` 从调用方自报改为可信认证主体
- 审计日志中区分 submitter / executor / impersonation
- 对 job cancel / schema create / postprocess 增加主体来源标识

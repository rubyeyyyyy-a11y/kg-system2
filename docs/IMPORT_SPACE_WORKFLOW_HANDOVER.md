# Import Workspace + Managed Spaces Handover

本文档面向当前阶段的接手人，解释为什么主线已经收口为“选择/创建 space -> 导入 -> 在该 space 中查看图谱”，以及当前实现的事实来源、边界、限制和最小运维动作。

## 1. 为什么主线先抽离 single-space 假设

multi-space phase-1 的核心不是“多一个 spaces 页面”，而是去掉运行时默认把所有请求都打到单一 `NEBULA_SPACE` 的旧假设。

需要同时收口的对象有：

- imports
- spaces provisioning
- search / graph / detail
- metadata cache
- Elasticsearch 文档与查询

当前实现刻意保持 request-level current space 为单一入口，避免未来继续出现“某些接口读 header、某些接口读 body、某些 worker 读全局变量”的多真相。

## 2. 为什么创建 space 被收编到 Import Workspace

这不是取消 `spaces` 子域，而是收口主 UI 入口。

- `spaces` 继续负责模板化 provisioning 与 registry
- `features/space` 继续保留 hooks / api / types
- 变化只发生在前端信息架构：
  用户不再需要先去独立 space 主入口，再回 Import 页面

当前推荐主路径：

1. 在 Import Workspace 顶部确认 current space
2. 如果需要隔离测试，在同页创建模板 space
3. 创建成功后自动切换 current space
4. 继续上传 CSV、preview、validate、submit
5. 切到 graph/search/discovery 查看该 space 数据

imports v1 当前稳态预算：

- 单文件 CSV 最大支持 `100MB`
- 单 draft 总大小最大支持 `200MB`
- 单 draft 最多 `5` 个文件
- preview 后端最多取样 `300` 行，前端默认请求 `200` 行
- failed rows 最多落盘 `3000` 条
- job 仍保留 `300000` 行保护；大文件导入更慢是预期行为，不是异常

## 3. 事实来源与真相边界

### Imports

- Draft truth source:
  `.run/import-drafts/<draft_id>.json`
- Compiled plan execution truth source:
  `.run/import-jobs/<job_id>/compiled_plan.json`
- Job truth source:
  `.run/import-jobs/<job_id>/state.json`

补充说明：

- validate 返回给 UI 的 `compiled_plan` 只是最近一次校验产物
- 真正执行时只认 job snapshot 下冻结的 `compiled_plan.json`
- UI 只是展示层，不是真相来源
- upload 已改成流式落盘；upload 阶段不再做全量 decode / row_count 扫描
- `ImportFileRecord.row_count` 允许延迟补全，初次 upload 后可能仍是 pending

### Spaces

- Space registry truth source:
  `.run/space-registry/spaces.json`

registry 记录的是管理面真相，不是图数据本身；图数据真相仍在 Nebula 对应 space 内。

## 4. Current space 解析规则

唯一入口：`backend/app/core/space_context.py`

规则固定为：

- current space 只来自 request-level header `X-KG-Space`
- header 缺失时回落默认 project space
- header 非法时返回 `400 SPACE_HEADER_INVALID`
- header 指向未注册 space 时返回 `404 SPACE_NOT_REGISTERED`
- request body 中不允许再散落引入 `target_space` 作为主机制
- 后台 import worker 不读取可变全局状态，只读取 job snapshot 冻结的 `space_name`

运行时落点：

- `request.state.space_name`
- `request.state.space_resolution`
- request-scoped `ContextVar`

这意味着 current space 不是全局 mutable singleton。

## 5. 子域边界

### imports

- 负责 CSV 导入生命周期
- 负责 draft / validate / compiled plan / job snapshot
- 负责导入后的 metadata refresh 与 entity ES sync
- validate 仍不是最终成功保证；它只是格式 / mapping / 规则检查
- executor 仍是单 worker、单 job 顺序执行，不做并发导入

### spaces

- 负责受控模板化 provisioning
- 负责 registry 写入与状态流转
- 当前只支持 `entity_rel2_default`

### search / graph / detail

- 负责 current space 下的数据访问
- 不负责切换或创建 space

### metadata

- cache 按 `space_name` 分桶
- refresh / invalidate 都是 space-aware

### Elasticsearch

- 文档写入带 `space_name`
- `_id = {space_name}:{vid}`
- 查询强制追加 `space_name` filter

## 6. Import 页面里的 current space 流程

Import Workspace 顶部固定区域负责：

- 展示当前 `space_name`
- 展示 `display_name`
- 展示 `template_type`
- 展示 `integration_scope`
- 展示 `status`
- 提供 Switch Space 入口
- 提供 Create New Space 入口

Create New Space 使用页内 inline panel，不跳走独立页面。

创建成功后必须立即完成：

1. current space 自动切换到新 space
2. create panel 关闭
3. 页面内展示 success summary
4. 明确引导“下一步上传 CSV”

后续 imports 请求继续通过统一 http helper 自动注入 `X-KG-Space`。

补充：

- 当前空间切换不再依赖 Import Workspace 内部的临时刷新循环
- App 层的 `space switch coordinator` 会统一完成 space-scoped 状态清空、`/api/spaces` 刷新，以及 readiness / `index_status` 回填
- Import Workspace 只负责发起切换和展示当前状态，不再维护第二套 current-space 刷新主线

## 7. 默认 space 风险提示的产品含义

如果 current space 是默认 project space，Import Workspace 必须显示：

`You are importing into the default project space. Create a new test space if you want isolated testing.`

含义不是禁止导入，而是提醒内部用户：

- 默认 space 会混入主项目数据
- 做模板实验或回归验证时，更推荐先创建隔离测试 space

如果 current space 是模板测试 space，则显示：

`You are importing into an isolated template-based space.`

这是正向确认，帮助用户建立“当前操作是隔离的”心智。

## 8. Discovery best-effort 边界

非默认 managed space 下的 discovery 仍是 phase-1 best-effort：

- 不承诺任意模板对象都完整进入 discovery 主链路
- 不等于 fully supported multi-space discovery
- UI 和文档都必须显式提示，避免用户把“导入成功”误解成“所有 downstream 能力都完整支持”
- 但 discovery 的候选搜索链路已经要求严格 space-aware；历史 space 若仍使用旧 ES 文档，必须先做受控 backfill，而不是在查询链路加 fallback
- 受控 backfill 与验收分层说明见 `docs/MULTI_SPACE_ES_ALIGNMENT.md`

更明确地说：

- ES 候选层必须可用：`/api/search`、`/api/suggest`、`/api/suggest_raw_id`、`/api/discovery/entity_candidates`
- Nebula 图层必须 space-aware：`/api/graph/discovery`、`/api/node/*`、`/api/edge_detail`、`/api/subgraph`、`/api/expand`、`/api/relation_types`
- 小空间结果少通常是数据规模问题，不等于 current space 失效

## 9. 最小运维/排障说明

### 9.1 查看当前 registry

直接查看：

- `.run/space-registry/spaces.json`

常用命令：

```bash
cat .run/space-registry/spaces.json
python -m json.tool .run/space-registry/spaces.json
```

### 9.2 判断当前请求命中了哪个 space

优先看响应头：

- `X-KG-Space`

例如：

```bash
curl -i -H 'X-KG-Space: test_space_a' http://localhost:8000/api/spaces/current
```

服务端会把最终解析后的 space 回写到响应头；如果 header 缺失，就会看到默认 space。

### 9.3 判断 provisioning failed

看两处：

1. `POST /api/spaces` 返回的错误
2. registry 对应 entry

重点字段：

- `status`
- `internal_status`
- `last_error`
- `ready_at`

如果 `status=failed`，说明模板化 provisioning 没有完成，需要根据 `last_error` 排查。

### 9.4 手工清理测试 space 的 registry 记录

当前没有 delete space API，只支持谨慎手工清理 registry 记录。

建议步骤：

1. 先确认目标是测试 space，不是默认 project space
2. 先备份 `.run/space-registry/spaces.json`
3. 确认没有正在运行的 `POST /api/spaces` provisioning
4. 只删除对应测试 space 的 registry entry，不要改默认 space entry
5. 保存后重新用 `python -m json.tool` 校验 JSON 格式

注意：

- 这只清理 registry 管理记录，不会自动删除 Nebula / ES 内的数据
- 如果底层数据仍保留，后续是否重建同名 space 要由运维自己判断

### 9.5 当前事实来源文件清单

- `.run/import-drafts/<draft_id>.json`
- `.run/import-jobs/<job_id>/state.json`
- `.run/import-jobs/<job_id>/compiled_plan.json`
- `.run/import-jobs/<job_id>/events.jsonl`
- `.run/import-jobs/<job_id>/failed_rows.csv`
- `.run/space-registry/spaces.json`

## 10. 当前已知限制

- 不支持 delete space
- 不支持新增模板类型
- 不支持复杂 Nebula 参数编辑 UI
- 不支持 auth / permission
- 不支持多 worker / 多 job 并发契约
- 不支持断点续跑
- 不支持对象存储、分片上传、断点续传
- 不把 imports v1 扩成通用大文件平台
- `300000` 行以上的 CSV 即使体积仍在 100MB 内，也会被保护阈值拒绝
- discovery 在非默认 space 下仍是 best-effort
- registry 仍是 runtime-local JSON，而不是分布式控制面
- `demo_kg` 全量 canonical backfill 仍需继续推进；这是历史主空间搜索恢复任务，不是可无限后置的可选运维项

## 11. 后续二期方向

- discovery 的模板化支持边界做得更清晰
- 更完整的 template version / migration 机制
- provisioning 异步化与更明确的进度反馈
- registry repair / reconciliation 运维工具
- 如果以后引入并发 worker，再补跨实例协调与更强的控制面

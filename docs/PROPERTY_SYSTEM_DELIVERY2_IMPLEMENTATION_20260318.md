## Delivery 2: Import Preservation + `edge_kind`

### Why `edge_kind`

- `REL2` 继续保持单物理边类型，但需要一个稳定的语义主键字段来区分边语义。
- `edge_kind` 现在会作为持久化属性进入 `REL2.props`，供后续 detail/edit/layout/backfill 复用。
- 导入链路会优先使用显式 `edge_kind` 列；没有显式列时，再使用 import context 提供的默认值；最后才回退到 `relation` 列。

### Import preservation rules

- 节点采用“固定字段显式映射 + 未知列原样保留”：
  - 固定字段：`ID`, `entity_type`, `entity_name`, `entity_raw_id`, `description`, `source`, `synonyms`
  - 其他列默认按原列名保留
- 边采用“公共字段显式映射 + 未知列原样保留”：
  - identity：`srcVID`, `dstVID`, `rank`
  - 公共字段：`relation`, `source`, `evidence`, `version`, `updated_at`, `updated_by`
  - 类型专属列和其他未知列默认按原列名保留
- `edge_kind` 会在后端归一化阶段注入到 property mappings，并进入 schema plan / compiled plan / 写入语句。

### Alias changes

- `evidence` 仍然是显式目标字段。
- `pmid` 和 `relation_detail` 不再默认压缩到 `evidence`。
- 如果需要把 `pmid` 或 `relation_detail` 合并到 `evidence`，现在应由用户手工映射，而不是系统默认别名合并。

### Consistency target

- `team-ingestion` 草稿构建和通用 `ImportWorkspace` 默认映射现在使用同一套导入规则中心。
- 后端统一规则位于 `backend/app/object_meta/import_rules.py`。
- `ImportWorkspace` 默认映射改为基于后端返回的 alias hints 和默认 edge-kind 上下文，而不是前端本地压缩规则。

### Backfill scope

- 本轮没有自动触发 `demo_kg` 全量回填或重导。
- 当前交付只提供回填准备能力：
  - 小样本节点导入验证
  - 小样本边导入验证
  - `synonyms` 保留验证
  - 边专属字段保留验证
  - `edge_kind` 持久化验证

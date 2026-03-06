# Metadata Stats Migration (Phase 2)

## 1. 命名与结构

- Tag: `EntityTypeStat`
  - `entity_type` (string)
  - `entity_type_norm` (string, lowercase key)
  - `count` (int64)
  - `updated_at` (int64)
  - `updated_by` (string)
- Tag: `RelationTypeStat`
  - `relation_type` (string)
  - `relation_type_norm` (string, lowercase key)
  - `count` (int64)
  - `updated_at` (int64)
  - `updated_by` (string)

说明：
- 元数据仍在 NebulaGraph 内，未引入文件缓存。
- 只新增 metadata tags，不改动现有 `Entity` / `REL2` 结构。

## 2. 迁移命令（不重导原图）

```bash
cd /home/ray/kg-system
bash data-import/scripts/10_migrate_metadata.sh
```

常用环境变量：
- `GRAPH_HOST/GRAPH_PORT/GRAPH_USER/GRAPH_PASSWORD`
- `SPACE`（默认 `demo_kg`）
- `EDGE_TYPE`（默认 `REL2`）
- `SOURCE_MODE`（`auto|csv|db`，默认 `auto`）
- `NEBULA_TIMEOUT_MS`（默认 120000）

## 3. 导入后自动刷新

`data-import/run.sh` 已在 `import_edges` 后新增步骤：
- `Step 7/8 refresh_metadata`：执行 `04_refresh_metadata.py --mode rebuild`
- `Step 8/8 verify`：包含 `05_verify_metadata.sh`

## 4. 校验命令

```bash
cd /home/ray/kg-system
bash data-import/scripts/05_verify_metadata.sh
```

该脚本会：
- 检查 `EntityTypeStat` / `RelationTypeStat` 非空
- 将 metadata 统计与基线数据比对（`SOURCE_MODE=auto` 时优先 CSV 分片，缺失时退化到 DB 聚合）

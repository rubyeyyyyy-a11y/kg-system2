# REL2 + Rank Migration (B1)

## 1) Create New Edge Type

```ngql
-- Keep old REL as-is, create REL2 for ranked multi-edges.
CREATE EDGE IF NOT EXISTS REL2(
  relation string,
  source string,
  evidence string,
  version int64,
  updated_at int64,
  updated_by string
);
```

Notes:
- Keep property set aligned with your current REL schema.
- If your REL has more props, add them to REL2 too.

## 2) Generate Ranked CSV

```bash
python3 backend/scripts/generate_rel2_ranked_edges.py \
  --input /path/to/edges_clean.csv \
  --output /path/to/edges_with_rank.csv
```

Rank rule:
- same `(src,dst)` group gets `rank=0..n-1`
- ranking order is stable by `(relation, source_db, evidence)`

## 3) Import REL2 with nebula-importer

Use config: `backend/scripts/nebula_import_rel2.yaml`

```bash
nebula-importer --config backend/scripts/nebula_import_rel2.yaml
```

Update the yaml `space/connection/path` fields before import.

## 4) Verify Rank In Nebula Studio

```ngql
GO FROM 123 OVER REL2
YIELD src(edge) AS src, dst(edge) AS dst, rank(edge) AS rank, properties(edge).relation AS relation, properties(edge).source AS source
LIMIT 20;
```

Expected:
- `rank` not all `0`.
- same `src -> dst` can have multiple rows with different `rank`.

API note:
- Backend returns `rank` as string in JSON to avoid JS int64 precision loss.
- Edge detail/update API定位键为 `(src, dst, rank-string)`，服务端会再解析为 int64。

## 5) Backend Runtime Switch

Set env:

```bash
EDGE_TYPE=REL2
```

Default is `REL`, so old data remains readable until switched.

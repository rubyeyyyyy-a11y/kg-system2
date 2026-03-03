# raw_id_norm Migration (NebulaGraph)

## 1) Schema change

```ngql
ALTER TAG Entity ADD (raw_id_norm string);
```

Optional index (recommended for large data):

```ngql
CREATE TAG INDEX IF NOT EXISTS idx_entity_raw_id_norm ON Entity(raw_id_norm);
```

After backfill/import:

```ngql
REBUILD TAG INDEX idx_entity_raw_id_norm;
```

## 2) Normalization rule (must match backend search)

`normalize_raw_id(s)`:

1. Unicode NFKC
2. Replace full-width colon `：` -> `:`
3. Remove all `:`
4. Remove all whitespace
5. `casefold()` (lowercase)

Examples:

- `MONDO：0005148` -> `mondo0005148`
- `MONDO:0005148` -> `mondo0005148`
- `MONDO0005148` -> `mondo0005148`
- ` ０００５１４８ ` -> `0005148`

## 3) Offline backfill (recommended for large data)

Use script:

```bash
cd backend
python3 scripts/generate_raw_id_norm_csv.py \
  --input /path/to/vertices.csv \
  --output /path/to/vertices.with_raw_id_norm.csv \
  --raw-id-column entity_raw_id
```

Then import with nebula-importer in update/overwrite mode for vertices (or rebuild space and full import).

## 4) Online UPDATE (small data only)

For very small datasets only. For million-level and above, avoid online per-vertex update in nGQL due performance.

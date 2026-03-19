# Legacy ES No-Space Purge Runbook

## Purpose

This runbook physically removes historical ES documents that do not satisfy the canonical contract because they do not have `space_name`.

Scope is fixed:

- global `legacy no-space purge`
- no per-space delete
- no online API participation
- no backfill/import inline deletion

## Preconditions

The purge must not run until all of the following are true:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/check_demo_kg_backfill.py --require-full
```

- `demo_kg` full completion is still true
- `demo_kg.index_status.doc_count == demo_kg.index_status.nebula_entity_count`
- current online search remains on the canonical multi-space contract
- legacy no-space documents can be counted precisely with dry-run

## Commands

Dry-run:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/purge_legacy_es_docs.py
```

Execute:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/purge_legacy_es_docs.py --execute
```

Optional explicit summary path:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/purge_legacy_es_docs.py \
  --execute \
  --summary-json backend/state/legacy_es_purge_execute_latest.json
```

## Fixed Flow

The script enforces this sequence:

1. prove `demo_kg` full completion from registry/index snapshot
2. count legacy no-space documents
3. `delete_by_query` all documents missing `space_name`
4. re-count legacy no-space documents
5. verify canonical per-space doc counts are unchanged
6. re-run `check_demo_kg_backfill.py --require-full`
7. write a JSON summary into `backend/state/`

## Expected Success Signals

- `verification.legacy_missing_space_after.count == 0`
- `verification.all_canonical_counts_unchanged == true`
- `verification.demo_kg_full_check.ok == true`

After execute, sample the live product paths again:

```bash
curl -sS -H 'X-KG-Space: demo_kg' 'http://127.0.0.1:8000/api/suggest?q=allergic%20respiratory%20disease&limit=5'
curl -sS -H 'X-KG-Space: demo_kg' 'http://127.0.0.1:8000/api/suggest_raw_id?q=MONDO:0000771&limit=5'
curl -sS -H 'X-KG-Space: it_space_218354' 'http://127.0.0.1:8000/api/suggest?q=Codex%20Import%20Entity%20Final&limit=5'
curl -sS -H 'Content-Type: application/json' -H 'X-KG-Space: it_space_218354' \
  -d '{"q":"Codex Import Entity Final 1773375224","page":1,"page_size":10,"search_in_name":true,"search_in_description":false,"search_in_type":false,"search_in_raw_id":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains"}' \
  http://127.0.0.1:8000/api/discovery/entity_candidates
```

## Explicitly Forbidden

- deleting “legacy no-space docs for one space”
- embedding delete logic into import/backfill/online search
- mutating the canonical document contract

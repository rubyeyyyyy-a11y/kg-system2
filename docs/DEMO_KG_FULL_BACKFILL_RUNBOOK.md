# demo_kg Full Canonical Backfill Runbook

## 1. Why This Exists

`demo_kg` is the historical default space in the current environment.

Its full canonical backfill is not optional maintenance. It is the delivery path for restoring historical search coverage under the current multi-space contract:

- ES queries stay filtered by `space_name`
- ES document `_id` stays `{space_name}:{vid}`
- no legacy fallback is added to online search/discovery

That means `demo_kg` search coverage can recover only by continuing canonical backfill until the historical space is substantially aligned.

## 2. Formal Execution Entry

Recommended working directory:

- repo root: `/home/ray/kg-system`

Recommended command:

```bash
bash backend/scripts/run_demo_kg_backfill_round.sh
```

The wrapper keeps the current backfill logic unchanged and only fixes the operational contract:

- target space is always `demo_kg`
- `--resume` is always enabled
- `--verify` is always enabled
- default `--batch-size=500`
- default `--max=5000`
- per-run log and per-run summary are emitted automatically

Override knobs when needed:

```bash
DEMO_KG_BACKFILL_MAX_DOCS=10000 DEMO_KG_BACKFILL_BATCH_SIZE=500 bash backend/scripts/run_demo_kg_backfill_round.sh
```

Pass-through flags are still possible for exceptional cases, but the default runbook does not require them.

## 3. Fixed Paths

State file:

- `backend/state/es_backfill_spaces.state.json`

Per-run summary directory:

- `backend/state/demo_kg_backfill_runs/`

Latest summary file:

- `backend/state/demo_kg_backfill_summary_latest.json`

Per-run log directory:

- `backend/logs/demo_kg_backfill/`

Direct inspection command:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/check_demo_kg_backfill.py
```

## 4. Recommended Round Size

Default round:

- `batch-size=500`
- `max=5000`

Why this is the default:

- keeps each round bounded and easy to inspect
- reduces the blast radius of transient Nebula/ES instability
- produces visible cursor/doc-count movement without turning the run into a long opaque batch

Do not increase `max` first.

Only consider larger rounds after several stable rounds show all of the following:

- cursor continues to advance
- `doc_count` keeps increasing
- verify keeps passing
- logs do not show repeated timeout/connection failures

## 5. Single-Round Checklist

After each round, check all of the following.

### 5.1 State file

Inspect:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/check_demo_kg_backfill.py --tail 0
```

Must check:

- `spaces.demo_kg.cursor` moved forward
- `spaces.demo_kg.last_vid` moved forward or stayed consistent with the latest cursor strategy
- `spaces.demo_kg.updated_at` refreshed

### 5.2 Summary file

Must check:

- `summaries[0].status`
- `summaries[0].es_doc_count`
- `summaries[0].nebula_entity_count`
- `summaries[0].coverage_pct`
- `summaries[0].fail_count`
- `summaries[0].verify.ok`
- `summaries[0].verify.sample_query_ok`

Expected default outcome:

- `status=verified_partial` until coverage is much closer to the historical full space
- `fail_count=0`
- `verify.ok=true`

### 5.3 Log file

Find the latest run:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/check_demo_kg_backfill.py
```

Must check for:

- `[backfill] batch=... cursor=...`
- `[backfill] verify space=demo_kg status=...`
- `[backfill] done space=demo_kg status=...`
- absence of repeated Nebula timeout / connection errors
- absence of ES bulk failure lines

If logs contain a one-off Nebula metadata fallback warning but the round still advances, keep observing; do not reset immediately.

### 5.4 Product sampling

With backend running, sample the candidate layer against `demo_kg`:

```bash
curl -s -H 'X-KG-Space: demo_kg' 'http://127.0.0.1:8000/api/suggest?q=mondo&limit=5'
curl -s -H 'X-KG-Space: demo_kg' 'http://127.0.0.1:8000/api/suggest_raw_id?q=MONDO:0000&limit=5'
curl -s -H 'X-KG-Space: demo_kg' -X POST 'http://127.0.0.1:8000/api/search' -H 'Content-Type: application/json' -d '{"q":"adenoiditis","search_in_name":true,"search_in_description":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains","include_edges":false}'
curl -s -H 'X-KG-Space: demo_kg' -X POST 'http://127.0.0.1:8000/api/discovery/entity_candidates' -H 'Content-Type: application/json' -d '{"q":"adenoiditis","page":1,"page_size":10,"search_in_name":true,"search_in_description":true,"search_in_type":false,"search_in_raw_id":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains"}'
```

Must check:

- API returns `200`
- results are non-empty for known historical entities when those entities are already canonicalized
- candidate behavior does not regress between rounds

## 6. Failure Recovery and Resume

Default action after any failed or interrupted round:

1. do not reset state
2. inspect latest log + summary + state bucket
3. rerun the same wrapper command

Why:

- the state file is the normal resume mechanism
- `cursor` / `last_vid` is the continuity anchor
- resetting too early risks replaying already-processed ranges and losing progress visibility

Resume command:

```bash
bash backend/scripts/run_demo_kg_backfill_round.sh
```

Continue running when all of the following hold:

- cursor advances
- `es_doc_count` increases over time
- `coverage_pct` trends upward
- verify stays healthy
- failures are transient rather than repeating identically

Pause and investigate when any of the following holds:

- multiple consecutive rounds show no `cursor` movement
- multiple consecutive rounds show no `es_doc_count` growth
- verify fails
- identical timeout/connection errors recur across rounds
- bulk failures appear

## 7. reset-space-state Boundary

Default rule:

- do **not** use `--reset-space-state demo_kg`

Absolutely do not reset when:

- the round merely timed out once
- the process was interrupted after partial progress
- cursor is still advancing across rounds
- doc_count is still growing

Only consider reset when:

- the state bucket is clearly corrupt or obviously inconsistent with the latest summary/logs
- repeated resume attempts restart from a bad pointer and make no forward progress
- the operator intentionally decides to replay `demo_kg` from the beginning as a controlled action

Reset is therefore an exception path, not the normal retry path.

## 8. Completion Criteria

### 8.1 Technical completion

Phase A:

- multiple consecutive rounds succeed
- `cursor` and `doc_count` keep growing
- verify remains healthy

Phase B:

- `coverage_pct` reaches a clearly improved band relative to the current 0.2%
- `verified_partial` remains stable without recurring failures

Phase C:

- `coverage_pct` is close enough to the historical full-space expectation that remaining gaps are operational tail work, not the main user-visible bottleneck
- verify remains stable across repeated rounds

### 8.2 Product completion

- common historical `demo_kg` search / suggest / raw-id / discovery-candidate queries feel close to the pre-migration full-database behavior
- candidate search in unified discovery is no longer obviously under-covering the historical space
- operators no longer need to explain missing `demo_kg` candidates as “backfill not caught up yet” for normal historical lookups

## 9. Current Baseline Snapshot

Current recorded baseline before the remaining tail work:

- `index_status=verified_partial`
- `es_doc_count=10000`
- `nebula_entity_count=5059789`
- `coverage_pct=0.2`
- state bucket shows `cursor=100`, `last_vid=5047041`

This is enough to prove the mechanism works.

It is not enough to claim historical search recovery is finished.

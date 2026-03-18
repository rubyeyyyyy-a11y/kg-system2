#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any
from urllib import error, parse, request


def _now() -> int:
    return int(time.time())


BACKEND_BASE = os.environ.get("SMOKE_BACKEND_BASE") or f"http://{os.environ.get('BACKEND_HOST', '127.0.0.1')}:{os.environ.get('BACKEND_PORT', '8000')}"
SMOKE_TIMEOUT_SEC = int(os.environ.get("SMOKE_CLEANUP_TIMEOUT_SEC", "240"))
SMOKE_POLL_INTERVAL_SEC = float(os.environ.get("SMOKE_CLEANUP_POLL_INTERVAL_SEC", "2"))
ACTOR = os.environ.get("SMOKE_CLEANUP_ACTOR", "smoke_import_cleanup")
SPACE_NAME = os.environ.get("SMOKE_CLEANUP_SPACE_NAME") or f"it_cleanup_smoke_{_now()}"
ENTITY_VID = int(os.environ.get("SMOKE_CLEANUP_ENTITY_VID", str(700000000 + (_now() % 1000000))))
ENTITY_TOKEN = os.environ.get("SMOKE_CLEANUP_ENTITY_TOKEN") or f"SmokeCleanup{_now()}{uuid.uuid4().hex[:6]}"
CSV_FILENAME = os.environ.get("SMOKE_CLEANUP_FILENAME", "cleanup_smoke.csv")


class SmokeError(RuntimeError):
    pass


def _log(message: str) -> None:
    print(f"[cleanup-smoke] {message}")


def _json_dumps(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _http_json(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any | None = None,
    timeout_sec: int = 30,
) -> Any:
    url = f"{BACKEND_BASE}{path}"
    req_headers: dict[str, str] = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    data: bytes | None = None
    if body is not None:
        data = _json_dumps(body)
        req_headers["Content-Type"] = "application/json"
    req = request.Request(url=url, method=method.upper(), headers=req_headers, data=data)
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return None
            return json.loads(raw)
    except error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise SmokeError(f"HTTP {exc.code} {method.upper()} {path} failed: {payload}") from exc
    except error.URLError as exc:
        raise SmokeError(f"{method.upper()} {path} failed: {exc}") from exc


def _encode_multipart(
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[str, bytes]:
    boundary = f"----cleanupsmoke{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for key, (filename, content, content_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", b"".join(chunks)


def _upload_csv(space_name: str, csv_bytes: bytes) -> dict[str, Any]:
    content_type, body = _encode_multipart(fields={}, files={"file": (CSV_FILENAME, csv_bytes, "text/csv")})
    req = request.Request(
        url=f"{BACKEND_BASE}/api/import/files",
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": content_type,
            "X-KG-Space": space_name,
        },
        data=body,
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise SmokeError(f"HTTP {exc.code} POST /api/import/files failed: {payload}") from exc
    except error.URLError as exc:
        raise SmokeError(f"POST /api/import/files failed: {exc}") from exc


def _poll_until(name: str, probe: Any, *, timeout_sec: int = SMOKE_TIMEOUT_SEC, interval_sec: float = SMOKE_POLL_INTERVAL_SEC) -> Any:
    deadline = time.time() + timeout_sec
    last_payload: Any = None
    while time.time() < deadline:
        done, payload = probe()
        last_payload = payload
        if done:
            return payload
        time.sleep(interval_sec)
    raise SmokeError(f"timeout waiting for {name}; last payload: {json.dumps(last_payload, ensure_ascii=False)}")


def _search_and_suggest(space_name: str, query: str) -> dict[str, int]:
    headers = {"X-KG-Space": space_name}
    search_payload = _http_json(
        "POST",
        "/api/search",
        headers=headers,
        body={
            "q": query,
            "search_in_name": True,
            "search_in_description": False,
            "include_edges": False,
        },
    )
    suggest_query = parse.urlencode({"q": query, "limit": 5})
    suggest_payload = _http_json("GET", f"/api/suggest?{suggest_query}", headers=headers)
    return {
        "search_nodes": len(search_payload.get("nodes") or []),
        "search_total_candidates": int(search_payload.get("total_candidates") or 0),
        "suggest_items": len(suggest_payload.get("items") or []),
    }


def main() -> int:
    _log(f"backend={BACKEND_BASE}")
    _log(f"space_name={SPACE_NAME} entity_token={ENTITY_TOKEN} entity_vid={ENTITY_VID}")

    health = _http_json("GET", "/api/health")
    _log(f"health ok={bool(health.get('ok'))} hosts_rows={health.get('hosts_rows')}")

    create_space_payload = {
        "space_name": SPACE_NAME,
        "display_name": SPACE_NAME,
        "description": "cleanup smoke isolated space",
        "template_type": "entity_rel2_default",
        "created_by": ACTOR,
    }
    created = _http_json("POST", "/api/spaces", body=create_space_payload)
    _log(f"create_space status={created.get('status')} warnings={len(created.get('warnings') or [])}")

    space_ready = _poll_until(
        "space ready",
        lambda: (
            (lambda payload: (payload.get("status") == "ready", payload))(_http_json("GET", f"/api/spaces/{SPACE_NAME}"))
        ),
    )
    _log(
        "space_ready "
        f"status={space_ready.get('status')} graph_status={space_ready.get('graph_status')} search_status={space_ready.get('search_status')}"
    )

    headers = {"X-KG-Space": SPACE_NAME}
    csv_bytes = f"ID,entity_name,entity_type,source\n{ENTITY_VID},{ENTITY_TOKEN},Disease,smoke\n".encode("utf-8")
    uploaded = _upload_csv(SPACE_NAME, csv_bytes)
    file_id = str(uploaded.get("file_id") or "")
    if not file_id:
        raise SmokeError(f"upload did not return file_id: {json.dumps(uploaded, ensure_ascii=False)}")
    _log(f"upload file_id={file_id}")

    preview = _http_json(
        "POST",
        "/api/import/preview",
        headers=headers,
        body={"file_ids": [file_id], "sample_rows": 5, "mode_hint": "vertex"},
    )
    sources = preview.get("sources") or []
    if len(sources) != 1:
        raise SmokeError(f"expected exactly 1 preview source, got {len(sources)}")

    draft = _http_json(
        "POST",
        "/api/import/drafts",
        headers=headers,
        body={
            "mode": "vertex",
            "file_ids": [file_id],
            "mapping": [
                {
                    "object_type": "tag",
                    "object_name": "Entity",
                    "field_mappings": [
                        {"source_column": "ID", "target_field": "ID"},
                        {"source_column": "entity_name", "target_field": "entity_name"},
                        {"source_column": "entity_type", "target_field": "entity_type"},
                        {"source_column": "source", "target_field": "source"},
                    ],
                }
            ],
            "update_strategy": {"mode": "merge_partial", "create_if_missing": True, "update_existing": True},
            "schema_options": {"allow_create_object": True, "allow_add_properties": True},
            "postprocess_options": {"refresh_metadata": True, "sync_entity_es": True},
        },
    )
    draft_id = str(draft.get("draft_id") or "")
    if not draft_id:
        raise SmokeError("draft_id missing from /api/import/drafts response")
    _log(f"draft draft_id={draft_id} status={draft.get('status')}")

    validation = _http_json("POST", f"/api/import/drafts/{draft_id}/validate", headers=headers, body={})
    if not bool(validation.get("passed")):
        raise SmokeError(f"validation failed: {json.dumps(validation, ensure_ascii=False)}")
    plan_id = str(((validation.get("compiled_plan") or {}).get("plan_id")) or "")
    _log(f"validate passed=true plan_id={plan_id}")

    created_job = _http_json(
        "POST",
        "/api/import/jobs",
        headers=headers,
        body={"draft_id": draft_id, "created_by": ACTOR, "is_test_data": True},
    )
    job_id = str(created_job.get("job_id") or "")
    if not job_id:
        raise SmokeError("job_id missing from /api/import/jobs response")
    _log(f"job_created job_id={job_id} status={created_job.get('status')}")

    final_job = _poll_until(
        "import job completion",
        lambda: (
            (lambda payload: (str(payload.get("status")) in {"succeeded", "failed_import", "failed_postprocess", "cancelled"}, payload))(
                _http_json("GET", f"/api/import/jobs/{job_id}", headers=headers)
            )
        ),
    )
    if str(final_job.get("status")) != "succeeded":
        raise SmokeError(f"import job did not succeed: {json.dumps(final_job, ensure_ascii=False)}")
    batch_id = str(final_job.get("batch_id") or created_job.get("batch_id") or "")
    if not batch_id:
        raise SmokeError(f"batch_id missing from job payload: {json.dumps(final_job, ensure_ascii=False)}")
    _log(f"job_succeeded job_id={job_id} batch_id={batch_id}")

    pre_visibility = _poll_until(
        "search/suggest visibility after import",
        lambda: (
            (lambda payload: (payload["search_nodes"] > 0, payload))(_search_and_suggest(SPACE_NAME, ENTITY_TOKEN))
        ),
    )
    _log(
        "before_cleanup "
        f"search_nodes={pre_visibility['search_nodes']} search_total_candidates={pre_visibility['search_total_candidates']} "
        f"suggest_items={pre_visibility['suggest_items']}"
    )

    batches_before_cleanup = _http_json("GET", "/api/import/batches", headers=headers)
    if not any(str(item.get("batch_id")) == batch_id for item in (batches_before_cleanup or [])):
        raise SmokeError("batch record missing from /api/import/batches before cleanup")

    preview_cleanup = _http_json(
        "POST",
        "/api/import/batches/cleanup-plan",
        headers=headers,
        body={"batch_ids": [batch_id], "scope": "full_batch", "created_by": ACTOR},
    )
    plan_summary = preview_cleanup.get("plan_summary") or {}
    if not isinstance(plan_summary, dict) or "deletable_entity_count" not in plan_summary:
        raise SmokeError(f"cleanup preview missing plan_summary: {json.dumps(preview_cleanup, ensure_ascii=False)}")
    _log(
        "preview_plan "
        f"requested_entities={plan_summary.get('requested_entity_count')} "
        f"deletable_entities={plan_summary.get('deletable_entity_count')} "
        f"blocked_entities={plan_summary.get('blocked_entity_count')} "
        f"conflicts={plan_summary.get('conflict_count')}"
    )

    cleanup_created = _http_json(
        "POST",
        "/api/import/batches/cleanup",
        headers=headers,
        body={"batch_ids": [batch_id], "scope": "full_batch", "created_by": ACTOR},
    )
    cleanup_job_id = str(cleanup_created.get("cleanup_job_id") or "")
    if not cleanup_job_id:
        raise SmokeError(f"cleanup_job_id missing from cleanup create response: {json.dumps(cleanup_created, ensure_ascii=False)}")
    _log(f"cleanup_created cleanup_job_id={cleanup_job_id} status={cleanup_created.get('status')}")

    final_cleanup_job = _poll_until(
        "cleanup job completion",
        lambda: (
            (lambda payload: (str(payload.get("status")) in {"succeeded", "partial_succeeded", "failed"}, payload))(
                _http_json("GET", f"/api/import/cleanup-jobs/{cleanup_job_id}", headers=headers)
            )
        ),
    )
    if str(final_cleanup_job.get("status")) not in {"succeeded", "partial_succeeded"}:
        raise SmokeError(f"cleanup job did not succeed: {json.dumps(final_cleanup_job, ensure_ascii=False)}")
    _log(
        "cleanup_completed "
        f"status={final_cleanup_job.get('status')} deleted_entities={final_cleanup_job.get('deleted_entity_count')} "
        f"deleted_relations={final_cleanup_job.get('deleted_relation_count')} conflicts={final_cleanup_job.get('conflict_count')}"
    )

    post_visibility = _poll_until(
        "search/suggest cleanup propagation",
        lambda: (
            (lambda payload: (payload["search_nodes"] == 0 and payload["suggest_items"] == 0, payload))(
                _search_and_suggest(SPACE_NAME, ENTITY_TOKEN)
            )
        ),
    )
    _log(
        "after_cleanup "
        f"search_nodes={post_visibility['search_nodes']} search_total_candidates={post_visibility['search_total_candidates']} "
        f"suggest_items={post_visibility['suggest_items']}"
    )

    batches_after_cleanup = _http_json("GET", "/api/import/batches", headers=headers)
    matching_batch = next((item for item in (batches_after_cleanup or []) if str(item.get("batch_id")) == batch_id), None)
    if matching_batch is None:
        raise SmokeError("batch record missing from /api/import/batches after cleanup")

    cleanup_jobs_after = _http_json("GET", "/api/import/cleanup-jobs", headers=headers)
    matching_cleanup = next((item for item in (cleanup_jobs_after or []) if str(item.get("cleanup_job_id")) == cleanup_job_id), None)
    if matching_cleanup is None:
        raise SmokeError("cleanup job record missing from /api/import/cleanup-jobs after cleanup")

    summary = {
        "space_name": SPACE_NAME,
        "entity_token": ENTITY_TOKEN,
        "batch_id": batch_id,
        "cleanup_job_id": cleanup_job_id,
        "preview_plan_summary": {
            "requested_entity_count": plan_summary.get("requested_entity_count"),
            "requested_relation_count": plan_summary.get("requested_relation_count"),
            "deletable_entity_count": plan_summary.get("deletable_entity_count"),
            "deletable_relation_count": plan_summary.get("deletable_relation_count"),
            "blocked_entity_count": plan_summary.get("blocked_entity_count"),
            "conflict_count": plan_summary.get("conflict_count"),
        },
        "execute_summary": {
            "status": matching_cleanup.get("status"),
            "phase": matching_cleanup.get("phase"),
            "deleted_entity_count": matching_cleanup.get("deleted_entity_count"),
            "deleted_relation_count": matching_cleanup.get("deleted_relation_count"),
            "conflict_count": matching_cleanup.get("conflict_count"),
        },
        "batch_cleanup_status": matching_batch.get("cleanup_status"),
        "post_cleanup_visibility": post_visibility,
    }
    _log(f"summary={json.dumps(summary, ensure_ascii=False)}")
    _log("completed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeError as exc:
        _log(f"failed: {exc}")
        raise SystemExit(1) from exc

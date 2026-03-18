import { expect, test, type Page } from "@playwright/test";

import { gotoApp } from "../helpers";

async function mockSpaceEndpoints(page: Page) {
  const spaces = [
    {
      space_name: "demo_kg",
      display_name: "demo_kg",
      description: "",
      template_type: "entity_rel2_default",
      template_version: "entity_rel2_default.v1",
      integration_scope: "entity_rel2_core",
      status: "ready",
      internal_status: "ready",
      created_by: "system",
      created_at: "2026-03-16T00:00:00Z",
      ready_at: "2026-03-16T00:00:01Z",
      graph_status: "ready",
      search_status: "full",
      coverage_pct: 100,
      index_status: { status: "verified_nonempty", doc_count: 4, note: "", updated_at: null },
    },
  ];
  await page.route("**/api/spaces/current", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        space_name: "demo_kg",
        source: "default",
        header_present: false,
        header_value: null,
        registry_status: "ready",
        graph_status: "ready",
        search_status: "full",
        coverage_pct: 100,
        index_status: { status: "verified_nonempty", doc_count: 4, note: "", updated_at: null },
      }),
    });
  });
  await page.route("**/api/spaces", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(spaces) });
  });
}

test("import batches tab lists history, submits cleanup, and shows selected cleanup result details", async ({ page }) => {
  let cleanupJobs: Array<Record<string, unknown>> = [];
  let batches = [
    {
      batch_id: "batch_1",
      space_id: "demo_kg",
      source_type: "import_ui",
      created_at: 1,
      updated_at: 1,
      is_test_data: true,
      draft_id: "draft_1",
      job_id: "job_1",
      submission_id: null,
      status: "succeeded",
      entity_count: 2,
      relation_count: 1,
      searchable: true,
      cleanup_status: "not_requested",
      tags: [],
      notes: null,
      ledger_summary: {},
      warning_messages: [],
    },
    {
      batch_id: "batch_2",
      space_id: "demo_kg",
      source_type: "import_ui",
      created_at: 3,
      updated_at: 3,
      is_test_data: true,
      draft_id: "draft_2",
      job_id: "job_2",
      submission_id: null,
      status: "succeeded",
      entity_count: 1,
      relation_count: 0,
      searchable: true,
      cleanup_status: "not_requested",
      tags: [],
      notes: null,
      ledger_summary: {},
      warning_messages: [],
    },
  ];

  await mockSpaceEndpoints(page);
  await page.route("**/api/import/schema", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ tags: [], edge_types: [] }) });
  });
  await page.route("**/api/import/jobs", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
  });
  await page.route("**/api/import/batches", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(batches) });
  });
  await page.route("**/api/import/batches/batch_1/items", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          item_id: "item_entity_1",
          batch_id: "batch_1",
          space_id: "demo_kg",
          job_id: "job_1",
          created_at: 1,
          item_type: "entity",
          created_by_batch: true,
          vid: 101,
          entity_raw_id: "raw-101",
          entity_name: "Alpha",
          row_index: 1,
          item_key: "entity:101",
        },
        {
          item_id: "item_relation_1",
          batch_id: "batch_1",
          space_id: "demo_kg",
          job_id: "job_1",
          created_at: 1,
          item_type: "relation",
          created_by_batch: true,
          src_vid: 101,
          dst_vid: 102,
          relation: "rel_a",
          rank: 0,
          edge_type: "REL2",
          row_index: 2,
          item_key: "relation:REL2:101:102:rel_a:0",
        },
      ]),
    });
  });
  await page.route("**/api/import/batches/batch_2/items", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
  });
  await page.route("**/api/import/cleanup-jobs", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(cleanupJobs) });
  });
  await page.route("**/api/import/batches/cleanup-plan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        batch_ids: ["batch_1"],
        scope: "full_batch",
        plan_summary: {
          requested_entity_count: 2,
          requested_relation_count: 1,
          ledger_blocked_entity_count: 1,
          live_graph_blocked_entity_count: 0,
          blocked_entity_count: 1,
          deletable_entity_count: 1,
          deletable_relation_count: 1,
          conflict_count: 1,
          warnings: ["cleanup request contained duplicate ledger entries; duplicates were skipped before delete execution"],
          verification_scope_note: "scope=full_batch mock note",
          generated_at: 25,
        },
        conflicts: [
          {
            vid: 102,
            item_type: "entity",
            source: "ledger",
            reason: "referenced_by_other_batches",
            blocking_batch_ids: ["batch_2"],
            blocking_relations: 1,
            details: { entity_name: "Beta" },
          },
        ],
        blocked_entities: {
          total_count: 1,
          sample: [
            {
              vid: 102,
              entity_name: "Beta",
              entity_raw_id: "raw-102",
              item_key: "entity:102",
              conflict_sources: ["ledger"],
              conflicts: [],
            },
          ],
        },
        deletable_entities: { total_count: 1, sample: [{ vid: 101, entity_name: "Alpha", entity_raw_id: "raw-101", item_key: "entity:101" }] },
        deletable_relations: {
          total_count: 1,
          sample: [{ edge_type: "REL2", src_vid: 101, dst_vid: 102, rank: 0, relation: "rel_a", item_key: "relation:REL2:101:102:rel_a:0" }],
        },
        warning_messages: ["cleanup request contained duplicate ledger entries; duplicates were skipped before delete execution"],
        verification_scope_note: "scope=full_batch mock note",
        has_plan_artifacts: false,
        artifacts: [],
        consistency_note:
          "preview is a point-in-time analysis based on current ledger + graph state; execute recalculates plan before deletion",
      }),
    });
  });
  await page.route("**/api/import/batches/cleanup", async (route) => {
    batches = batches.map((batch) => ({ ...batch, cleanup_status: batch.batch_id === "batch_1" ? "queued" : batch.cleanup_status }));
    cleanupJobs = [
      {
        cleanup_job_id: "cleanup_other",
        space_id: "demo_kg",
        batch_ids: ["batch_2"],
        scope: "full_batch",
        created_by: "import_workspace",
        created_at: 3,
        updated_at: 3,
        started_at: 3,
        finished_at: 4,
        status: "succeeded",
        phase: "completed",
        final_phase: "completed",
        phase_history: [{ phase: "planning", at: 3 }, { phase: "completed", at: 4 }],
        requested_relation_count: 0,
        requested_entity_count: 1,
        deleted_relation_count: 0,
        deleted_entity_count: 1,
        skipped_relation_count: 0,
        skipped_entity_count: 0,
        deduplicated_relation_count: 0,
        deduplicated_entity_count: 0,
        conflict_count: 0,
        warning_messages: [],
        error_message: null,
        failure_phase: null,
        failure_kind: null,
        failure_detail: {},
        duration_ms: 1000,
        conflicts: [],
        plan_summary: {
          requested_entity_count: 1,
          requested_relation_count: 0,
          ledger_blocked_entity_count: 0,
          live_graph_blocked_entity_count: 0,
          blocked_entity_count: 0,
          deletable_entity_count: 1,
          deletable_relation_count: 0,
          conflict_count: 0,
          warnings: [],
          verification_scope_note: "scope=full_batch mock",
          generated_at: 10,
        },
        has_plan_artifacts: true,
        verify_summary: { ok: true, note: "other job" },
        metadata_summary: { ok: true },
        reconcile_summary: { ok: true },
        artifacts: [{ kind: "plan_summary", filename: "plan_summary.json", path: "/tmp/plan_summary_other.json" }],
      },
      {
        cleanup_job_id: "cleanup_1",
        space_id: "demo_kg",
        batch_ids: ["batch_1"],
        scope: "full_batch",
        created_by: "import_workspace",
        created_at: 2,
        updated_at: 2,
        started_at: 2,
        finished_at: 5,
        status: "queued",
        phase: "planning",
        final_phase: null,
        phase_history: [{ phase: "planning", at: 2 }],
        requested_relation_count: 1,
        requested_entity_count: 2,
        deleted_relation_count: 0,
        deleted_entity_count: 0,
        skipped_relation_count: 0,
        skipped_entity_count: 0,
        deduplicated_relation_count: 0,
        deduplicated_entity_count: 0,
        conflict_count: 1,
        warning_messages: ["entity verification skipped because scope=relations_only"],
        error_message: null,
        failure_phase: null,
        failure_kind: null,
        failure_detail: {},
        duration_ms: 3000,
        conflicts: [
          {
            vid: 102,
            item_type: "entity",
            source: "ledger",
            reason: "referenced_by_other_batches",
            blocking_batch_ids: ["batch_2"],
            blocking_relations: 1,
            details: { entity_name: "Beta" },
          },
        ],
        plan_summary: {
          requested_entity_count: 2,
          requested_relation_count: 1,
          ledger_blocked_entity_count: 1,
          live_graph_blocked_entity_count: 0,
          blocked_entity_count: 1,
          deletable_entity_count: 1,
          deletable_relation_count: 1,
          conflict_count: 1,
          warnings: ["cleanup request contained duplicate ledger entries; duplicates were skipped before delete execution"],
          verification_scope_note: "scope=full_batch mock note",
          generated_at: 20,
        },
        has_plan_artifacts: true,
        verify_summary: { ok: true, note: "relations_only cleanup does not verify relation-level leftovers or global graph references" },
        metadata_summary: { ok: true, refreshed: 1 },
        reconcile_summary: { ok: true, sync_scope: "none" },
        artifacts: [
          { kind: "summary", filename: "summary.json", path: "/tmp/summary.json" },
          { kind: "conflicts", filename: "conflicts.json", path: "/tmp/conflicts.json" },
          { kind: "verify_summary", filename: "verify_summary.json", path: "/tmp/verify_summary.json" },
          { kind: "plan_summary", filename: "plan_summary.json", path: "/tmp/plan_summary.json" },
          { kind: "blocked_entities", filename: "blocked_entities.json", path: "/tmp/blocked_entities.json" },
          { kind: "deletable_entities", filename: "deletable_entities.json", path: "/tmp/deletable_entities.json" },
          { kind: "deletable_relations", filename: "deletable_relations.json", path: "/tmp/deletable_relations.json" },
        ],
      },
    ];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(cleanupJobs[1]) });
  });

  await gotoApp(page);
  await page.getByTestId("workspace-tab-import").click();
  await page.getByTestId("import-tab-batches").click();

  await expect(page.getByTestId("import-batch-item-batch_1")).toBeVisible();
  await expect(page.getByTestId("import-selected-batch-id")).toHaveText("batch_1");
  await expect(page.getByText("entity vid=101 name=Alpha raw_id=raw-101 created_by_batch=yes")).toHaveCount(1);

  await page.getByTestId("import-batch-select-batch_1").check();
  await page.getByTestId("import-batch-preview-cleanup-button").click();
  await expect(page.getByTestId("cleanup-plan-preview")).toContainText("Cleanup Plan Preview");
  await expect(page.getByTestId("cleanup-plan-preview")).toContainText("blocked_entities=1");
  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.getByTestId("import-batch-confirm-cleanup-button").click();

  await expect(page.getByTestId("cleanup-job-status")).toContainText("cleanup_1");
  await expect(page.getByTestId("cleanup-job-status")).toContainText("status=queued");
  await expect(page.getByTestId("cleanup-job-status")).not.toContainText("cleanup_other");
  await expect(page.getByTestId("cleanup-conflicts-summary")).toContainText("referenced_by_other_batches");
  await expect(page.getByTestId("cleanup-verify-summary")).toContainText("relations_only cleanup");
  await expect(page.getByTestId("cleanup-error-summary")).toContainText("entity verification skipped");
  await expect(page.getByTestId("cleanup-job-status")).toContainText("plan.blocked_entities=1");
  await expect(page.getByTestId("cleanup-job-status")).toContainText("plan.live_graph_blocked=0");
  await expect(page.getByTestId("cleanup-job-status")).toContainText("scope=full_batch mock note");
  await expect(page.getByRole("button", { name: "Download Summary" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download Conflicts" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download Plan Summary" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download Blocked Entities" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download Deletable Entities" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download Deletable Relations" })).toBeVisible();
});

test("@quick-cleanup quick cleanup compatibility path stays available without breaking preview-confirm flow", async ({ page }) => {
  let cleanupSubmitCount = 0;
  let cleanupJobs: Array<Record<string, unknown>> = [];
  let batches = [
    {
      batch_id: "batch_compat_1",
      space_id: "demo_kg",
      source_type: "import_ui",
      created_at: 10,
      updated_at: 10,
      is_test_data: true,
      draft_id: "draft_compat_1",
      job_id: "job_compat_1",
      submission_id: null,
      status: "succeeded",
      entity_count: 1,
      relation_count: 0,
      searchable: true,
      cleanup_status: "not_requested",
      tags: [],
      notes: null,
      ledger_summary: {},
      warning_messages: [],
    },
  ];

  await mockSpaceEndpoints(page);
  await page.route("**/api/import/schema", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ tags: [], edge_types: [] }) });
  });
  await page.route("**/api/import/jobs", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
  });
  await page.route("**/api/import/batches", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(batches) });
  });
  await page.route("**/api/import/batches/batch_compat_1/items", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          item_id: "item_entity_compat_1",
          batch_id: "batch_compat_1",
          space_id: "demo_kg",
          job_id: "job_compat_1",
          created_at: 10,
          item_type: "entity",
          created_by_batch: true,
          vid: 2001,
          entity_raw_id: "raw-2001",
          entity_name: "Compat Entity",
          row_index: 1,
          item_key: "entity:2001",
        },
      ]),
    });
  });
  await page.route("**/api/import/cleanup-jobs", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(cleanupJobs) });
  });
  await page.route("**/api/import/batches/cleanup-plan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        batch_ids: ["batch_compat_1"],
        scope: "full_batch",
        plan_summary: {
          requested_entity_count: 1,
          requested_relation_count: 0,
          ledger_blocked_entity_count: 0,
          live_graph_blocked_entity_count: 0,
          blocked_entity_count: 0,
          deletable_entity_count: 1,
          deletable_relation_count: 0,
          conflict_count: 0,
          warnings: [],
          verification_scope_note: "scope=full_batch compat preview",
          generated_at: 30,
        },
        conflicts: [],
        blocked_entities: { total_count: 0, sample: [] },
        deletable_entities: { total_count: 1, sample: [{ vid: 2001, entity_name: "Compat Entity", entity_raw_id: "raw-2001", item_key: "entity:2001" }] },
        deletable_relations: { total_count: 0, sample: [] },
        warning_messages: [],
        verification_scope_note: "scope=full_batch compat preview",
        has_plan_artifacts: false,
        artifacts: [],
        consistency_note:
          "preview is a point-in-time analysis based on current ledger + graph state; execute recalculates plan before deletion",
      }),
    });
  });
  await page.route("**/api/import/batches/cleanup", async (route) => {
    cleanupSubmitCount += 1;
    if (cleanupSubmitCount === 1) {
      const quickJob = {
        cleanup_job_id: "cleanup_quick_1",
        space_id: "demo_kg",
        batch_ids: ["batch_compat_1"],
        scope: "full_batch",
        created_by: "import_workspace",
        created_at: 31,
        updated_at: 31,
        started_at: 31,
        finished_at: null,
        status: "queued",
        phase: "planning",
        final_phase: null,
        phase_history: [{ phase: "planning", at: 31 }],
        requested_relation_count: 0,
        requested_entity_count: 1,
        deleted_relation_count: 0,
        deleted_entity_count: 0,
        skipped_relation_count: 0,
        skipped_entity_count: 0,
        deduplicated_relation_count: 0,
        deduplicated_entity_count: 0,
        conflict_count: 0,
        warning_messages: [],
        error_message: null,
        failure_phase: null,
        failure_kind: null,
        failure_detail: {},
        duration_ms: null,
        conflicts: [],
        plan_summary: {
          requested_entity_count: 1,
          requested_relation_count: 0,
          ledger_blocked_entity_count: 0,
          live_graph_blocked_entity_count: 0,
          blocked_entity_count: 0,
          deletable_entity_count: 1,
          deletable_relation_count: 0,
          conflict_count: 0,
          warnings: [],
          verification_scope_note: "scope=full_batch quick",
          generated_at: 31,
        },
        has_plan_artifacts: true,
        verify_summary: { ok: true, note: "quick cleanup queued" },
        metadata_summary: { ok: true },
        reconcile_summary: { ok: true },
        artifacts: [{ kind: "summary", filename: "summary.json", path: "/tmp/summary_quick.json" }],
      };
      cleanupJobs = [quickJob];
      batches = batches.map((batch) => ({ ...batch, cleanup_status: "queued" }));
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(quickJob) });
      return;
    }

    const confirmJob = {
      cleanup_job_id: "cleanup_confirm_1",
      space_id: "demo_kg",
      batch_ids: ["batch_compat_1"],
      scope: "full_batch",
      created_by: "import_workspace",
      created_at: 35,
      updated_at: 36,
      started_at: 35,
      finished_at: 36,
      status: "succeeded",
      phase: "completed",
      final_phase: "completed",
      phase_history: [{ phase: "planning", at: 35 }, { phase: "completed", at: 36 }],
      requested_relation_count: 0,
      requested_entity_count: 1,
      deleted_relation_count: 0,
      deleted_entity_count: 1,
      skipped_relation_count: 0,
      skipped_entity_count: 0,
      deduplicated_relation_count: 0,
      deduplicated_entity_count: 0,
      conflict_count: 0,
      warning_messages: [],
      error_message: null,
      failure_phase: null,
      failure_kind: null,
      failure_detail: {},
      duration_ms: 1200,
      conflicts: [],
      plan_summary: {
        requested_entity_count: 1,
        requested_relation_count: 0,
        ledger_blocked_entity_count: 0,
        live_graph_blocked_entity_count: 0,
        blocked_entity_count: 0,
        deletable_entity_count: 1,
        deletable_relation_count: 0,
        conflict_count: 0,
        warnings: [],
        verification_scope_note: "scope=full_batch confirm",
        generated_at: 35,
      },
      has_plan_artifacts: true,
      verify_summary: { ok: true, note: "confirm cleanup done" },
      metadata_summary: { ok: true, refreshed: 1 },
      reconcile_summary: { ok: true, sync_scope: "none" },
      artifacts: [
        { kind: "summary", filename: "summary_confirm.json", path: "/tmp/summary_confirm.json" },
        { kind: "plan_summary", filename: "plan_summary_confirm.json", path: "/tmp/plan_summary_confirm.json" },
      ],
    };
    cleanupJobs = [confirmJob, ...cleanupJobs];
    batches = batches.map((batch) => ({ ...batch, cleanup_status: "succeeded" }));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(confirmJob) });
  });

  await gotoApp(page);
  await page.getByTestId("workspace-tab-import").click();
  await page.getByTestId("import-tab-batches").click();

  await page.getByTestId("import-batch-select-batch_compat_1").check();
  await expect(page.getByTestId("import-batch-cleanup-button")).toBeVisible();
  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.getByTestId("import-batch-cleanup-button").click();

  await expect(page.getByTestId("cleanup-job-status")).toContainText("cleanup_quick_1");
  await expect(page.getByTestId("cleanup-job-status")).toContainText("status=queued");
  await expect(page.getByRole("button", { name: "Download Summary" })).toBeVisible();

  await page.getByTestId("import-batch-preview-cleanup-button").click();
  await expect(page.getByTestId("cleanup-plan-preview")).toContainText("Cleanup Plan Preview");
  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.getByTestId("import-batch-confirm-cleanup-button").click();

  await expect(page.getByTestId("cleanup-job-status")).toContainText("cleanup_confirm_1");
  await expect(page.getByTestId("cleanup-job-status")).toContainText("status=succeeded");
  await expect(page.getByTestId("cleanup-verify-summary")).toContainText("confirm cleanup done");
  await expect(page.getByRole("button", { name: "Download Summary" })).toBeVisible();
});

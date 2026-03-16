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
    {
      space_name: "it_space_218354",
      display_name: "it_space_218354",
      description: "",
      template_type: "entity_rel2_default",
      template_version: "entity_rel2_default.v1",
      integration_scope: "entity_rel2_core",
      status: "ready",
      internal_status: "ready",
      created_by: "tester",
      created_at: "2026-03-16T00:00:00Z",
      ready_at: "2026-03-16T00:00:01Z",
      graph_status: "ready",
      search_status: "full",
      coverage_pct: 100,
      index_status: { status: "verified_nonempty", doc_count: 2, note: "", updated_at: null },
    },
  ];
  await page.route("**/api/spaces/current", async (route) => {
    const spaceName = route.request().headers()["x-kg-space"] || "demo_kg";
    const current = spaces.find((item) => item.space_name === spaceName) || spaces[0];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        space_name: current.space_name,
        source: current.space_name === "demo_kg" ? "default" : "header",
        header_present: current.space_name !== "demo_kg",
        header_value: current.space_name === "demo_kg" ? null : current.space_name,
        registry_status: current.status,
        graph_status: current.graph_status,
        search_status: current.search_status,
        coverage_pct: current.coverage_pct,
        index_status: current.index_status,
      }),
    });
  });
  await page.route("**/api/spaces", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(spaces),
    });
  });
}

async function mockImportSchema(page: Page) {
  await page.route("**/api/import/schema", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        tags: [{ object_type: "tag", name: "Entity", exists: true, properties: [{ name: "entity_name", type: "string", nullable: true }] }],
        edge_types: [{ object_type: "edge_type", name: "REL2", exists: true, properties: [{ name: "relation", type: "string", nullable: true }] }],
      }),
    });
  });
}

test("import minimal happy path freezes upload preview validate submit flow", async ({ page }) => {
  let jobs = [] as Array<Record<string, unknown>>;

  await mockSpaceEndpoints(page);
  await mockImportSchema(page);
  await page.route("**/api/import/files", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        file_id: "file_1",
        original_name: "demo.csv",
        size_bytes: 48,
        detected_delimiter: ",",
        detected_encoding: "utf-8",
      }),
    });
  });
  await page.route("**/api/import/preview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        sources: [
          {
            source_id: "source_1",
            file_id: "file_1",
            filename: "demo.csv",
            columns: ["ID", "entity_name", "entity_type", "source"],
            sample_rows: [{ ID: "1", entity_name: "Demo Import Entity", entity_type: "Disease", source: "manual" }],
            header_hash: "hash_1",
            inferred_kind: "vertex",
            warnings: [],
            alias_hints: [
              { source_column: "ID", logical_field: "ID" },
              { source_column: "entity_name", logical_field: "entity_name" },
            ],
            recommended_object_type: "tag",
          },
        ],
        workspace_mode_candidates: ["vertex"],
        warnings: [],
        columns: ["ID", "entity_name", "entity_type", "source"],
        sample_rows: [{ ID: "1", entity_name: "Demo Import Entity", entity_type: "Disease", source: "manual" }],
        inferred_mode_candidates: ["vertex"],
      }),
    });
  });
  await page.route("**/api/import/drafts", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        draft_id: "draft_1",
        space_name: "demo_kg",
        status: "mapped",
        workspace_mode: "vertex",
        mode: "vertex",
        file_ids: ["file_1"],
        sources: [
          {
            source_id: "source_1",
            file_id: "file_1",
            filename: "demo.csv",
            columns: ["ID", "entity_name", "entity_type", "source"],
            sample_rows: [{ ID: "1", entity_name: "Demo Import Entity", entity_type: "Disease", source: "manual" }],
            header_hash: "hash_1",
            inferred_kind: "vertex",
            warnings: [],
            alias_hints: [],
            recommended_object_type: "tag",
          },
        ],
        mapping: [],
        update_strategy: { mode: "merge_partial", create_if_missing: true, update_existing: true },
        schema_options: { allow_create_object: true, allow_add_properties: true },
        postprocess_options: { refresh_metadata: true, sync_entity_es: true },
        validation: null,
        created_at: 1,
        updated_at: 1,
      }),
    });
  });
  await page.route("**/api/import/drafts/draft_1/validate", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        passed: true,
        errors: [],
        warnings: [],
        integration_warnings: [],
        semantic_notes: [],
        scanned_rows: 1,
        error_rows: 0,
        errors_truncated: false,
        target_results: [
          {
            target_id: "target_1",
            source_id: "source_1",
            object_type: "tag",
            object_name: "Entity",
            source_columns: ["ID", "entity_name", "entity_type", "source"],
            passed: true,
            errors: [],
            warnings: [],
            hints: [],
            scanned_rows: 1,
            error_rows: 0,
          },
        ],
        compiled_plan: {
          plan_id: "plan_1",
          space_name: "demo_kg",
          template_type: "entity_rel2_default",
          integration_scope: "entity_rel2_core",
          workspace_mode: "vertex",
          mode: "vertex",
          file_ids: ["file_1"],
          sources: [
            {
              source_id: "source_1",
              file_id: "file_1",
              filename: "demo.csv",
              columns: ["ID", "entity_name", "entity_type", "source"],
              sample_rows: [{ ID: "1", entity_name: "Demo Import Entity", entity_type: "Disease", source: "manual" }],
              header_hash: "hash_1",
              inferred_kind: "vertex",
              warnings: [],
              alias_hints: [],
              recommended_object_type: "tag",
            },
          ],
          targets: [
            {
              target_id: "target_1",
              object_type: "tag",
              object_name: "Entity",
              source_id: "source_1",
              source_file_id: "file_1",
              source_filename: "demo.csv",
              source_columns: ["ID", "entity_name", "entity_type", "source"],
              inferred_source_kind: "vertex",
              identity_mapping: { id_column: "ID", src_column: null, dst_column: null, rank_column: null },
              property_mappings: [
                { source_column: "entity_name", target_field: "entity_name", logical_field: "entity_name" },
              ],
              row_selector: null,
              property_types: { entity_name: "string" },
              identity_fields: ["ID"],
              update_fields: ["entity_name"],
              create_fields: ["ID", "entity_name"],
              integration_level: "fully_integrated",
              warnings: [],
            },
          ],
          schema_create_plan: [],
          update_strategy: {},
          rank_generation_strategy: "preserve_input",
          postprocess_options: { refresh_metadata: true, sync_entity_es: true },
          warnings: [],
          integration_level: "fully_integrated",
          compiled_at: 1,
        },
      }),
    });
  });
  await page.route("**/api/import/jobs", async (route) => {
    if (route.request().method() === "POST") {
      jobs = [
        {
          job_id: "job_1",
          draft_id: "draft_1",
          space_name: "demo_kg",
          template_type: "entity_rel2_default",
          status: "queued",
          created_by: "import_workspace",
          workspace_mode: "vertex",
          mode: "vertex",
          plan_id: "plan_1",
          file_ids: ["file_1"],
          sources: [],
          targets: [],
          artifacts: [],
          created_at: 1,
          updated_at: 1,
          started_at: null,
          finished_at: null,
          cancel_requested: false,
          total_rows: 1,
          processed_rows: 0,
          success_rows: 0,
          failed_rows: 0,
          warnings: [],
          integration_warnings: [],
          integration_level: "fully_integrated",
          error_message: null,
          failure_stage: null,
          interrupted: false,
          metadata_refreshed: false,
          es_sync_skipped: false,
          failed_rows_truncated: false,
          cancel_effective_at_batch: false,
          affected_entity_vids: [],
          affected_schema_objects: [],
          index_status_snapshot: null,
          completion_summary: null,
        },
      ];
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(jobs[0]) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(jobs) });
  });
  await page.route("**/api/import/jobs/job_1/logs", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "job_1", lines: ["job queued"] }),
    });
  });

  await gotoApp(page);
  await page.getByTestId("workspace-tab-import").click();

  await page.getByTestId("import-file-input").setInputFiles({
    name: "demo.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("ID,entity_name,entity_type,source\n1,Demo Import Entity,Disease,manual\n", "utf8"),
  });
  await page.getByTestId("import-preview-button").click();
  await expect(page.getByText("source_id=source_1")).toHaveCount(1);
  await expect(page.getByText("columns=ID, entity_name, entity_type, source")).toHaveCount(1);

  await page.getByTestId("import-save-draft-button").click();
  await expect(page.getByText("draft_1 | mapped")).toHaveCount(1);

  await page.getByTestId("import-validate-button").click();
  await expect(page.getByText("compiled plan frozen: plan_1 | workspace=vertex | integration=fully_integrated | space=demo_kg")).toHaveCount(1);

  await page.getByTestId("import-submit-job-button").click();
  await expect(page.getByText("job_1")).toHaveCount(2);
  await expect(page.getByText("job queued")).toHaveCount(1);
});

test("import job list stays bound to current space after switch and queued job can cancel", async ({ page }) => {
  let smallJobCancelled = false;

  await mockSpaceEndpoints(page);
  await mockImportSchema(page);
  await page.route("**/api/import/jobs", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fulfill({ status: 405, body: "method not allowed" });
      return;
    }
    const spaceName = route.request().headers()["x-kg-space"] || "demo_kg";
    if (spaceName === "demo_kg") {
      await new Promise((resolve) => setTimeout(resolve, 500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            job_id: "demo_job_1",
            draft_id: "draft_demo",
            space_name: "demo_kg",
            template_type: "entity_rel2_default",
            status: "queued",
            created_by: "import_workspace",
            workspace_mode: "vertex",
            mode: "vertex",
            plan_id: "plan_demo",
            file_ids: ["file_demo"],
            sources: [],
            targets: [],
            artifacts: [],
            created_at: 1,
            updated_at: 1,
            cancel_requested: false,
            total_rows: 1,
            processed_rows: 0,
            success_rows: 0,
            failed_rows: 0,
            warnings: [],
            integration_warnings: [],
            integration_level: "fully_integrated",
            error_message: null,
            interrupted: false,
            metadata_refreshed: false,
            es_sync_skipped: false,
            failed_rows_truncated: false,
            cancel_effective_at_batch: false,
            affected_entity_vids: [],
            affected_schema_objects: [],
            index_status_snapshot: { status: "verified_nonempty", doc_count: 4, note: "", updated_at: null },
            completion_summary: { searchable: true, search_status: "full", index_status: "verified_nonempty" },
          },
        ]),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          job_id: "small_job_1",
          draft_id: "draft_small",
          space_name: "it_space_218354",
          template_type: "entity_rel2_default",
          status: smallJobCancelled ? "cancelled" : "queued",
          created_by: "import_workspace",
          workspace_mode: "vertex",
          mode: "vertex",
          plan_id: "plan_small",
          file_ids: ["file_small"],
          sources: [],
          targets: [],
          artifacts: [],
          created_at: 1,
          updated_at: 2,
          cancel_requested: false,
          total_rows: 1,
          processed_rows: 0,
          success_rows: 0,
          failed_rows: 0,
          warnings: [],
          integration_warnings: [],
          integration_level: "fully_integrated",
          error_message: null,
          interrupted: false,
          metadata_refreshed: false,
          es_sync_skipped: false,
          failed_rows_truncated: false,
          cancel_effective_at_batch: smallJobCancelled,
          affected_entity_vids: [],
          affected_schema_objects: [],
          index_status_snapshot: { status: "verified_nonempty", doc_count: 2, note: "", updated_at: null },
          completion_summary: { searchable: true, search_status: "full", index_status: "verified_nonempty" },
        },
      ]),
    });
  });
  await page.route("**/api/import/jobs/*/logs", async (route) => {
    const spaceName = route.request().headers()["x-kg-space"] || "demo_kg";
    const lines =
      spaceName === "it_space_218354"
        ? [smallJobCancelled ? "job cancelled before start" : "job queued in small space"]
        : ["job queued in demo space"];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ job_id: route.request().url().split("/").slice(-2)[0], lines }),
    });
  });
  await page.route("**/api/import/jobs/*/cancel", async (route) => {
    smallJobCancelled = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "small_job_1",
        draft_id: "draft_small",
        space_name: "it_space_218354",
        template_type: "entity_rel2_default",
        status: "cancelled",
        created_by: "import_workspace",
        workspace_mode: "vertex",
        mode: "vertex",
        plan_id: "plan_small",
        file_ids: ["file_small"],
        sources: [],
        targets: [],
        artifacts: [],
        created_at: 1,
        updated_at: 2,
        cancel_requested: false,
        total_rows: 1,
        processed_rows: 0,
        success_rows: 0,
        failed_rows: 0,
        warnings: [],
        integration_warnings: [],
        integration_level: "fully_integrated",
        error_message: null,
        interrupted: false,
        metadata_refreshed: false,
        es_sync_skipped: false,
        failed_rows_truncated: false,
        cancel_effective_at_batch: true,
        affected_entity_vids: [],
        affected_schema_objects: [],
        index_status_snapshot: { status: "verified_nonempty", doc_count: 2, note: "", updated_at: null },
        completion_summary: { searchable: true, search_status: "full", index_status: "verified_nonempty" },
      }),
    });
  });

  await gotoApp(page);
  await page.getByTestId("workspace-tab-import").click();
  await page.getByTestId("import-space-selector").selectOption("it_space_218354");
  await expect(page.getByText("small_job_1")).toHaveCount(2);
  await expect(page.getByTestId("import-job-closure-summary")).toContainText("searchable=yes");
  await expect(page.getByTestId("import-job-closure-summary")).toContainText("index_status=verified_nonempty");
  await expect(page.getByText("demo_job_1")).toHaveCount(0);

  await page.getByRole("button", { name: "取消" }).click();
  await expect(page.getByText("job cancelled before start")).toHaveCount(1);
  await expect(page.getByText("cancelled")).toHaveCount(2);
});

import { expect, test } from "@playwright/test";

import { fillDiscoverySearch, goToDiscovery, gotoApp, multiSpaceFixture, switchSpace } from "../helpers";

const demoSpace = multiSpaceFixture.spaces.demo;

function demoCandidateResponse(pageSize: number) {
  return {
    items: [
      {
        id: demoSpace.expected.vid,
        vid: demoSpace.expected.vid,
        label: demoSpace.expected.label,
        entity_type: "disease",
        raw_id: demoSpace.expected.rawId,
        source: "mock",
        score: 98.5,
        snippet: `${demoSpace.expected.label} snippet`,
        description: `${demoSpace.expected.label} description`,
      },
    ],
    page: 1,
    page_size: pageSize,
    returned: 1,
    has_more: false,
    next_page: null,
    meta: { request_id: "req-demo" },
    space_meta: {
      space_name: demoSpace.spaceName,
      graph_status: demoSpace.readiness.graphStatus,
      search_status: demoSpace.readiness.searchStatus,
      coverage_pct: 100,
      index_status: {
        status: demoSpace.readiness.indexStatus,
        doc_count: 1,
        coverage_pct: 100,
      },
    },
  };
}

function discoveryRunResponse() {
  return {
    nodes: [
      {
        id: demoSpace.expected.vid,
        label: demoSpace.expected.label,
        entity_type: "disease",
        raw_id: demoSpace.expected.rawId,
        source: "mock",
        score: null,
        snippet: "seed snippet",
        role: "seed",
        layer: "core",
        priority_score: 100,
        min_seed_distance: 0,
        bridge_seed_count: 0,
        local_anchor_seed: null,
        matched_seed_pairs: [],
        seed_support_count: 1,
        seed_support_vids: [demoSpace.expected.vid],
        score_breakdown: { seed_rank: 1 },
      },
      {
        id: 20,
        label: "Unified Discovery Node",
        entity_type: "gene",
        raw_id: "HGNC:20",
        source: "mock",
        score: null,
        snippet: "node twenty",
        role: "candidate",
        layer: "shared",
        priority_score: 9,
        min_seed_distance: 1,
        bridge_seed_count: 1,
        local_anchor_seed: null,
        matched_seed_pairs: [],
        seed_support_count: 1,
        seed_support_vids: [demoSpace.expected.vid],
        score_breakdown: { is_valid_shared_bridge: true },
      },
    ],
    edges: [
      {
        source: demoSpace.expected.vid,
        target: 20,
        rank: "0",
        edge_type: "REL2",
        relation: "treats",
        source_db: "mock",
        role: "seed_candidate",
        layer: "shared",
        priority_score: 9,
        seed_support_vids: [demoSpace.expected.vid],
        path_pair: "",
        is_backbone: true,
      },
    ],
    facets: {
      entity_types: [
        { entity_type: "disease", count: 1, seed_count: 1, candidate_count: 0, core_count: 1, shared_count: 0, local_count: 0, supplement_count: 0 },
        { entity_type: "gene", count: 1, seed_count: 0, candidate_count: 1, core_count: 0, shared_count: 1, local_count: 0, supplement_count: 0 },
      ],
      relation_types: [
        { relation_type: "treats", count: 1, seed_candidate_count: 1, candidate_candidate_count: 0, seed_seed_count: 0, core_count: 0, shared_count: 1, local_count: 0, supplement_count: 0 },
      ],
      query_summary: {
        search_type: "graph_discovery",
        selected_seed_count: 1,
        selected_seeds: [{ id: demoSpace.expected.vid, label: demoSpace.expected.label, entity_type: "disease" }],
        total_entities: 2,
        total_relationships: 1,
      },
      layers: [
        { layer: "core", node_count: 1, edge_count: 0 },
        { layer: "shared", node_count: 1, edge_count: 1 },
      ],
      seeds: [
        { seed_vid: demoSpace.expected.vid, label: demoSpace.expected.label, entity_type: "disease", local_count: 0, shared_touch_count: 1, core_path_count: 0 },
      ],
    },
    stats: {
      ranking_mode: "layered_multiseed",
      seed_count: 1,
      seeds_count: 1,
      candidate_count: 1,
      node_count: 2,
      edge_count: 1,
      final_nodes: 2,
      final_edges: 1,
      truncated: false,
      core_count: 1,
      shared_count: 1,
      local_count: 0,
      supplement_count: 0,
      dropped_nodes: 0,
      dropped_edges: 0,
      dropped_neighbors: 0,
      dropped_by_budget: 0,
      dropped_by_type_budget: 0,
      dropped_generic_hubs: 0,
      recall_candidate_count: 1,
      kept_candidate_count: 1,
      budget_applied: { max_nodes: 90, max_edges: 140 },
    },
    request_space: demoSpace.spaceName,
    space_meta: {
      space_name: demoSpace.spaceName,
      graph_status: demoSpace.readiness.graphStatus,
      search_status: demoSpace.readiness.searchStatus,
      coverage_pct: 100,
      index_status: {
        status: demoSpace.readiness.indexStatus,
        doc_count: 1,
        coverage_pct: 100,
      },
    },
    warnings: [],
    dropped_candidates: [],
    node_capabilities: [
      { node_id: demoSpace.expected.vid, expandable: true, terminal: false },
      { node_id: 20, expandable: true, terminal: false },
    ],
  };
}

function nodeDetailResponse(vid: number) {
  if (vid === 20) {
    return {
      vid: 20,
      entity_name: "Unified Discovery Node",
      entity_type: "gene",
      source: "mock",
      description:
        "Editable discovery node with a longer text block that should initially render in summary mode until the user expands it from the detail panel.",
      entity_raw_id: "HGNC:20",
      version: 3,
      updated_at: 0,
      updated_by: "system",
      props: {
        entity_name: "Unified Discovery Node",
        description:
          "Editable discovery node with a longer text block that should initially render in summary mode until the user expands it from the detail panel.",
        custom_flag: "delivery1",
      },
    };
  }
  return {
    vid,
    entity_name: demoSpace.expected.label,
    entity_type: "disease",
    source: "mock",
    description: "Seed detail",
    entity_raw_id: demoSpace.expected.rawId,
    version: 1,
    updated_at: 0,
    updated_by: "",
    props: {},
  };
}

test("entity type options stay space scoped and fallback safely across switch", async ({ page }) => {
  await page.route("**/api/entity_types", async (route) => {
    const spaceName = String(route.request().headers()["x-kg-space"] || demoSpace.spaceName);
    if (spaceName === demoSpace.spaceName) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ entity_type: "demo_only", count: 7 }]),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await gotoApp(page);
  await switchSpace(page, demoSpace);
  await goToDiscovery(page);
  await page.getByTestId("discovery-search-advanced-toggle").click();

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await goToDiscovery(page);
  if ((await page.getByTestId("discovery-search-advanced-entity-type").count()) === 0) {
    await page.getByTestId("discovery-search-advanced-toggle").click();
  }

  const select = page.getByTestId("discovery-search-advanced-entity-type");
  await expect(select.locator("option").filter({ hasText: "disease (201562)" })).toHaveCount(1);
  await expect(select.locator("option").filter({ hasText: "demo_only (7)" })).toHaveCount(0);

  await page.waitForTimeout(1800);
  await expect(select.locator("option").filter({ hasText: "disease (201562)" })).toHaveCount(1);
  await expect(select.locator("option").filter({ hasText: "demo_only (7)" })).toHaveCount(0);
});

test("discovery run and expand freeze rendered contract and dropped state", async ({ page }) => {
  let discoveryRequest: unknown = null;
  let expandRequest: unknown = null;

  await page.route("**/api/discovery/entity_candidates", async (route) => {
    const body = route.request().postDataJSON() as { page_size?: number };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(demoCandidateResponse(Number(body.page_size || 10))),
    });
  });
  await page.route("**/api/graph/discovery", async (route) => {
    discoveryRequest = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(discoveryRunResponse()),
    });
  });
  await page.route("**/api/node/*", async (route) => {
    const vid = Number(route.request().url().split("/").pop() || "0");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(nodeDetailResponse(vid)),
    });
  });
  await page.route("**/api/graph/discovery/expand", async (route) => {
    expandRequest = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        new_nodes: [
          {
            id: 30,
            label: "Expanded Node",
            entity_type: "protein",
            raw_id: "PR:30",
            source: "mock",
            score: null,
            snippet: "expanded node",
            role: "candidate",
            layer: "local",
            priority_score: 6,
            min_seed_distance: 2,
            bridge_seed_count: 0,
            local_anchor_seed: demoSpace.expected.vid,
            matched_seed_pairs: [],
            seed_support_count: 1,
            seed_support_vids: [demoSpace.expected.vid],
            score_breakdown: { expand_rank: 1 },
          },
        ],
        new_edges: [
          {
            source: 20,
            target: 30,
            rank: "0",
            edge_type: "REL2",
            relation: "interacts_with",
            source_db: "mock",
            role: "candidate_candidate",
            layer: "local",
            priority_score: 6,
            seed_support_vids: [demoSpace.expected.vid],
            path_pair: "",
            is_backbone: false,
          },
        ],
        support_edges: [],
        dropped_candidates: [
          {
            node_id: 31,
            label: "Dropped Leaf",
            entity_type: "compound",
            raw_id: "CMP:31",
            source: "mock",
            snippet: "dropped node",
            reason: "budget",
            source_node_id: 20,
            support_edges: [],
          },
        ],
        has_more_candidates_before_budget: true,
        has_more_candidates_after_filters: true,
        terminal: false,
        request_space: demoSpace.spaceName,
        space_meta: {
          space_name: demoSpace.spaceName,
          graph_status: demoSpace.readiness.graphStatus,
          search_status: demoSpace.readiness.searchStatus,
          coverage_pct: 100,
          index_status: {
            status: demoSpace.readiness.indexStatus,
            doc_count: 1,
            coverage_pct: 100,
          },
        },
        warnings: [],
        stats: {
          candidate_neighbor_count: 2,
          filtered_candidate_count: 1,
          new_nodes_count: 1,
          new_edges_count: 1,
          dropped_by_budget: 1,
          dropped_by_type_filter: 0,
          dropped_by_relation_filter: 0,
          dropped_neighbors: 0,
          scanned_rows: 2,
          budget_applied: { expand_max_new_nodes: 1, expand_max_new_edges: 1 },
        },
      }),
    });
  });

  await gotoApp(page);
  await switchSpace(page, demoSpace);
  await goToDiscovery(page);
  await fillDiscoverySearch(page, demoSpace.searchTerm);
  await page.getByTestId("discovery-search-submit").click();
  await page.getByTestId(`discovery-candidate-add-seed-${demoSpace.expected.vid}`).click();
  await page.getByTestId("discovery-run-button").click();

  await expect(page.getByTestId("discovery-result-contract")).toHaveAttribute("data-request-space", demoSpace.spaceName);
  await expect(page.getByTestId("discovery-result-contract")).toHaveAttribute("data-node-count", "2");
  await expect(page.getByTestId("discovery-result-contract")).toHaveAttribute("data-edge-count", "1");
  expect(discoveryRequest).toMatchObject({ seed_vids: [demoSpace.expected.vid] });

  await page.getByText("Rendered Nodes").click();
  await page.getByTestId("managed-node-view-detail-20").click();
  await page.getByTestId("discovery-expand-button").click();

  expect(expandRequest).toMatchObject({ target_node_id: 20 });
  await expect(page.getByTestId("managed-node-view-detail-30")).toHaveCount(1);
  await expect(page.getByTestId("managed-node-view-detail-31")).toHaveCount(1);
});

test("discovery detail and edit stay reachable in unified workflow", async ({ page }) => {
  let editableFieldsCount = 0;
  let nodePatchBody: Record<string, unknown> | null = null;
  let edgeDetailCount = 0;
  let edgePatchBody: Record<string, unknown> | null = null;

  await page.route("**/api/discovery/entity_candidates", async (route) => {
    const body = route.request().postDataJSON() as { page_size?: number };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(demoCandidateResponse(Number(body.page_size || 10))),
    });
  });
  await page.route("**/api/graph/discovery", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(discoveryRunResponse()),
    });
  });
  await page.route("**/api/schema/editable_fields", async (route) => {
    editableFieldsCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        entity: {
          fields: [
            { name: "entity_name", required: true, maxLen: 120, multiline: false },
            { name: "description", required: false, maxLen: 500, multiline: true },
          ],
        },
        edge: {
          fields: [
            { name: "source", required: false, maxLen: 120, multiline: false },
            { name: "evidence", required: false, maxLen: 500, multiline: true },
          ],
        },
      }),
    });
  });
  await page.route("**/api/node/*", async (route) => {
    const vid = Number(route.request().url().split("/").pop() || "0");
    if (route.request().method() === "PATCH") {
      nodePatchBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          vid,
          version: 4,
          updated_at: 1,
          updated_by: String(nodePatchBody.updated_by || ""),
          updated: { description: String((nodePatchBody.set as Record<string, unknown>).description || "") },
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(nodeDetailResponse(vid)),
    });
  });
  await page.route("**/api/edge_detail", async (route) => {
    edgeDetailCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        edge_type: "REL2",
        src: demoSpace.expected.vid,
        dst: 20,
        rank: "0",
        relation: "treats",
        source_db: edgeDetailCount > 1 ? "mock_updated" : "mock",
        evidence: "Evidence line for testing expandable edge text behavior in Delivery 1.",
        version: edgeDetailCount > 1 ? 6 : 5,
        updated_at: 1,
        updated_by: edgeDetailCount > 1 ? "playwright" : "system",
        updated: false,
        props: {
          relation: "treats",
          source: edgeDetailCount > 1 ? "mock_updated" : "mock",
          evidence: "Evidence line for testing expandable edge text behavior in Delivery 1.",
          edge_kind: "treats",
        },
      }),
    });
  });
  await page.route("**/api/edge", async (route) => {
    edgePatchBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        edge_type: "REL2",
        src: demoSpace.expected.vid,
        dst: 20,
        rank: "0",
        version: 6,
        updated_at: 1,
        updated_by: String(edgePatchBody.updated_by || ""),
        updated: { source: String((edgePatchBody.set as Record<string, unknown>).source || "") },
      }),
    });
  });

  await gotoApp(page);
  await switchSpace(page, demoSpace);
  await goToDiscovery(page);
  await fillDiscoverySearch(page, demoSpace.searchTerm);
  await page.getByTestId("discovery-search-submit").click();
  await page.getByTestId(`discovery-candidate-add-seed-${demoSpace.expected.vid}`).click();
  await page.getByTestId("discovery-run-button").click();

  await page.getByText("Rendered Nodes").click();
  await page.getByTestId("managed-node-view-detail-20").click();
  await expect(page.getByTestId("selected-node-detail")).toContainText("Unified Discovery Node");
  await expect(page.getByTestId("selected-node-detail")).toContainText("Custom Flag");
  await expect(page.getByTestId("detail-raw-json-content")).toHaveCount(0);
  await page.getByTestId("detail-expand-description").click();
  await expect(page.getByTestId("selected-node-detail")).toContainText("until the user expands it from the detail panel");
  await page.getByTestId("detail-raw-json-toggle").click();
  await expect(page.getByTestId("detail-raw-json-content")).toHaveCount(1);

  await page.getByTestId("detail-panel-tab-edit").click();
  await page.getByTestId("edit-save-updated-by-input").fill("playwright");
  await page.getByTestId("edit-field-description").fill("patched in discovery");
  await page.getByTestId("selected-node-save-button").click();
  await expect(page.getByText("保存成功，version=4")).toHaveCount(1);

  await page.getByTestId("detail-panel-tab-direct").click();
  await page.getByTestId("direct-edge-src-input").fill(String(demoSpace.expected.vid));
  await page.getByTestId("direct-edge-dst-input").fill("20");
  await page.getByTestId("direct-edge-rank-input").fill("0");
  await page.getByTestId("direct-edge-load-button").click();
  await page.getByTestId("edit-save-updated-by-input").fill("playwright");
  await expect(page.getByTestId("edit-field-relation")).toContainText("treats");
  await expect(page.getByTestId("edit-field-version")).toContainText("5");
  await page.getByTestId("edit-field-source").fill("mock_updated");
  await page.getByTestId("direct-edge-save-button").click();
  await expect(page.getByText("边保存成功，version=6")).toHaveCount(1);

  expect(editableFieldsCount).toBeGreaterThanOrEqual(1);
  expect(nodePatchBody).toMatchObject({
    expected_version: 3,
    updated_by: "playwright",
    set: { description: "patched in discovery" },
  });
  expect(edgePatchBody).toMatchObject({
    edge_type: "REL2",
    src: demoSpace.expected.vid,
    dst: 20,
    rank: "0",
    expected_version: 5,
    updated_by: "playwright",
    set: { source: "mock_updated" },
  });
});

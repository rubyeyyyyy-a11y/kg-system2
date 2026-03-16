import { expect, test } from "@playwright/test";

import {
  expectDiscoveryPreviewContains,
  fillDiscoverySearch,
  fillLegacySearch,
  goToDiscovery,
  goToLegacy,
  gotoApp,
  multiSpaceFixture,
  switchSpace,
} from "../helpers";

const demoSpace = multiSpaceFixture.spaces.demo;
const smallSpace = multiSpaceFixture.spaces.small;

function discoveryCandidateResponse(spaceName: string, label: string, vid: number, rawId: string) {
  const readiness = spaceName === demoSpace.spaceName ? demoSpace.readiness : smallSpace.readiness;
  return {
    items: [
      {
        id: vid,
        vid,
        label,
        entity_type: "disease",
        raw_id: rawId,
        source: "mock",
        score: 98.5,
        snippet: `${label} snippet`,
        description: `${label} description`,
      },
    ],
    page: 1,
    page_size: 10,
    returned: 1,
    has_more: false,
    next_page: null,
    meta: { request_id: `req-${spaceName}` },
    space_meta: {
      space_name: spaceName,
      graph_status: readiness.graphStatus,
      search_status: readiness.searchStatus,
      coverage_pct: 100,
      index_status: {
        status: readiness.indexStatus,
        doc_count: 1,
        coverage_pct: 100,
      },
    },
  };
}

function legacySearchResponse(spaceName: string, label: string, vid: number) {
  const readiness = spaceName === demoSpace.spaceName ? demoSpace.readiness : smallSpace.readiness;
  return {
    nodes: [
      {
        id: vid,
        label,
        entity_type: "disease",
        raw_id: `${spaceName}:${vid}`,
        source: "mock",
        score: 77,
        snippet: `${label} snippet`,
      },
    ],
    edges: [],
    total_candidates: 1,
    truncated: false,
    meta: { request_id: `legacy-${spaceName}` },
    space_meta: {
      space_name: spaceName,
      graph_status: readiness.graphStatus,
      search_status: readiness.searchStatus,
      coverage_pct: 100,
      index_status: {
        status: readiness.indexStatus,
        doc_count: 1,
        coverage_pct: 100,
      },
    },
  };
}

test("discovery candidate search freezes preview submit list and space meta", async ({ page }) => {
  await page.route("**/api/discovery/entity_candidates", async (route) => {
    const headers = route.request().headers();
    const body = route.request().postDataJSON() as { page_size?: number };
    const spaceName = String(headers["x-kg-space"] || demoSpace.spaceName);
    const payload =
      spaceName === demoSpace.spaceName
        ? discoveryCandidateResponse(demoSpace.spaceName, demoSpace.expected.label, demoSpace.expected.vid, demoSpace.expected.rawId)
        : discoveryCandidateResponse(smallSpace.spaceName, smallSpace.expected.label, smallSpace.expected.vid, smallSpace.expected.rawId);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...payload, page_size: Number(body.page_size || payload.page_size) }),
    });
  });

  await gotoApp(page);
  await switchSpace(page, demoSpace);
  await goToDiscovery(page);
  await fillDiscoverySearch(page, demoSpace.searchTerm);
  await expectDiscoveryPreviewContains(page, demoSpace);

  await page.getByTestId("discovery-search-submit").click();

  const firstCandidate = page.getByTestId("discovery-candidate-item").first();
  await expect(firstCandidate).toHaveAttribute("data-label", demoSpace.expected.label);
  await expect(page.getByTestId("discovery-candidate-space-meta")).toHaveAttribute("data-space-name", demoSpace.spaceName);
  await expect(page.getByTestId("discovery-candidate-space-meta")).toHaveAttribute("data-search-status", demoSpace.readiness.searchStatus);
});

test("discovery candidate load subgraph enters formal drilldown without legacy fallback", async ({ page }) => {
  let subgraphRequest: unknown = null;

  await page.route("**/api/discovery/entity_candidates", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        discoveryCandidateResponse(demoSpace.spaceName, demoSpace.expected.label, demoSpace.expected.vid, demoSpace.expected.rawId)
      ),
    });
  });
  await page.route("**/api/subgraph", async (route) => {
    subgraphRequest = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        root_vid: demoSpace.expected.vid,
        nodes: [
          {
            id: demoSpace.expected.vid,
            label: demoSpace.expected.label,
            entity_type: "disease",
            raw_id: demoSpace.expected.rawId,
            source: "mock",
            score: null,
            snippet: "root node",
          },
        ],
        edges: [],
        stats: {
          node_count: 1,
          edge_count: 0,
          truncated: false,
          dropped_nodes: 0,
          dropped_edges: 0,
          dropped_neighbors: 0,
          budget_applied: { max_nodes: 300, max_edges: 20000 },
        },
      }),
    });
  });
  await page.route(`**/api/node/${demoSpace.expected.vid}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        vid: demoSpace.expected.vid,
        entity_name: demoSpace.expected.label,
        entity_type: "disease",
        source: "mock",
        description: "root detail",
        entity_raw_id: demoSpace.expected.rawId,
        version: 1,
        updated_at: 0,
        updated_by: "",
        props: {},
      }),
    });
  });

  await gotoApp(page);
  await switchSpace(page, demoSpace);
  await goToDiscovery(page);
  await fillDiscoverySearch(page, demoSpace.searchTerm);
  await page.getByTestId("discovery-search-submit").click();
  await page.getByTestId(`discovery-candidate-load-subgraph-${demoSpace.expected.vid}`).click();

  await expect(page.getByTestId("workspace-topbar")).toHaveAttribute("data-workspace-mode", "discovery");
  await expect(page.getByTestId("discovery-result-anchor")).toHaveAttribute("data-state", "drilldown");
  await expect(page.getByTestId("discovery-drilldown-contract")).toHaveAttribute("data-root-vid", String(demoSpace.expected.vid));
  await page.getByTestId("detail-panel-tab-edit").click();
  await expect(page.getByTestId("detail-panel-tab-edit")).toBeVisible();
  expect(subgraphRequest).toMatchObject({ root_vid: demoSpace.expected.vid });
});

test("space switch reset freezes legacy discovery and page scoped reset", async ({ page }) => {
  await page.route("**/api/discovery/entity_candidates", async (route) => {
    const spaceName = String(route.request().headers()["x-kg-space"] || demoSpace.spaceName);
    const payload =
      spaceName === demoSpace.spaceName
        ? discoveryCandidateResponse(demoSpace.spaceName, demoSpace.expected.label, demoSpace.expected.vid, demoSpace.expected.rawId)
        : discoveryCandidateResponse(smallSpace.spaceName, smallSpace.expected.label, smallSpace.expected.vid, smallSpace.expected.rawId);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.route("**/api/search", async (route) => {
    const spaceName = String(route.request().headers()["x-kg-space"] || demoSpace.spaceName);
    const payload =
      spaceName === demoSpace.spaceName
        ? legacySearchResponse(demoSpace.spaceName, demoSpace.expected.label, demoSpace.expected.vid)
        : legacySearchResponse(smallSpace.spaceName, smallSpace.expected.label, smallSpace.expected.vid);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.route("**/api/subgraph", async (route) => {
    const body = route.request().postDataJSON() as { root_vid: number };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        root_vid: body.root_vid,
        nodes: [
          {
            id: body.root_vid,
            label: demoSpace.expected.label,
            entity_type: "disease",
            raw_id: demoSpace.expected.rawId,
            source: "mock",
            score: null,
            snippet: "root node",
          },
        ],
        edges: [],
        stats: {
          node_count: 1,
          edge_count: 0,
          truncated: false,
          dropped_nodes: 0,
          dropped_edges: 0,
          dropped_neighbors: 0,
          budget_applied: { max_nodes: 300, max_edges: 20000 },
        },
      }),
    });
  });
  await page.route(`**/api/node/${demoSpace.expected.vid}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        vid: demoSpace.expected.vid,
        entity_name: demoSpace.expected.label,
        entity_type: "disease",
        source: "mock",
        description: "root detail",
        entity_raw_id: demoSpace.expected.rawId,
        version: 1,
        updated_at: 0,
        updated_by: "",
        props: {},
      }),
    });
  });

  await gotoApp(page);
  await switchSpace(page, demoSpace);

  await goToLegacy(page);
  await fillLegacySearch(page, demoSpace.searchTerm);
  await page.getByTestId("legacy-search-submit").click();
  await expect(page.locator(`[data-testid="legacy-search-result-item"][data-label="${demoSpace.expected.label}"]`)).toHaveCount(1);

  await goToDiscovery(page);
  await fillDiscoverySearch(page, demoSpace.searchTerm);
  await page.getByTestId("discovery-search-submit").click();
  await expect(page.locator(`[data-testid="discovery-candidate-item"][data-label="${demoSpace.expected.label}"]`)).toHaveCount(1);
  await page.getByTestId(`discovery-candidate-load-subgraph-${demoSpace.expected.vid}`).click();
  await expect(page.getByTestId("workspace-topbar")).toHaveAttribute("data-workspace-mode", "discovery");
  await expect(page.getByTestId("discovery-result-anchor")).toHaveAttribute("data-state", "drilldown");

  await switchSpace(page, smallSpace);

  await goToLegacy(page);
  await expect(page.locator(`[data-testid="legacy-search-result-item"][data-label="${demoSpace.expected.label}"]`)).toHaveCount(0);

  await goToDiscovery(page);
  await expect(page.locator(`[data-testid="discovery-candidate-item"][data-label="${demoSpace.expected.label}"]`)).toHaveCount(0);
  await expect(page.locator(`[data-testid="discovery-preview-item"][data-label="${demoSpace.expected.label}"]`)).toHaveCount(0);
  await expect(page.getByTestId("discovery-result-anchor")).toHaveAttribute("data-state", "empty");
});

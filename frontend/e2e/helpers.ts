import { expect, type Page } from "@playwright/test";

import { multiSpaceFixture, type SpaceFixture } from "./fixture";

export async function gotoApp(page: Page) {
  await page.goto("/");
  await page.getByTestId("workspace-tab-discovery").waitFor();
}

export async function goToDiscovery(page: Page) {
  await page.getByTestId("workspace-tab-discovery").click();
  await page.getByTestId("current-space-selector").waitFor();
}

export async function switchSpace(page: Page, space: SpaceFixture) {
  await goToDiscovery(page);
  await page.getByTestId("current-space-selector").selectOption(space.spaceName);
  await expect(page.getByTestId("current-space-display")).toHaveAttribute("data-space-name", space.spaceName);
  await expect(page.getByTestId("current-space-display")).toHaveAttribute("data-graph-status", space.readiness.graphStatus);
  await expect(page.getByTestId("current-space-display")).toHaveAttribute("data-search-status", space.readiness.searchStatus);
  await expect(page.getByTestId("current-space-readiness-display")).toHaveAttribute("data-index-status", space.readiness.indexStatus);
  await expect(page.getByTestId("space-switch-overlay")).toHaveCount(0);
}

export async function expectDiscoveryPreviewContains(page: Page, expected: SpaceFixture) {
  const list = page.getByTestId("discovery-preview-list");
  await expect(list).toBeVisible();
  await expect(list.locator('[data-testid="discovery-preview-item"]').first()).toHaveAttribute("data-label", expected.expected.label);
}

export async function expectDiscoveryCandidatesContain(page: Page, expected: SpaceFixture) {
  const list = page.getByTestId("discovery-candidate-list");
  await expect(list).toBeVisible();
  await expect(list.locator('[data-testid="discovery-candidate-item"]').first()).toHaveAttribute("data-label", expected.expected.label);
  await expect(page.getByTestId("discovery-candidate-space-meta")).toHaveAttribute("data-space-name", expected.spaceName);
  await expect(page.getByTestId("discovery-candidate-space-meta")).toHaveAttribute("data-search-status", expected.readiness.searchStatus);
}

export async function fillDiscoverySearch(page: Page, value: string) {
  const input = page.getByTestId("discovery-search-input");
  await input.fill(value);
}

export async function fillDiscoveryRawId(page: Page, value: string) {
  await page.getByTestId("discovery-search-advanced-toggle").click();
  await page.getByTestId("discovery-search-advanced-raw-id").fill(value);
}

export async function expectNoDiscoveryPreviewLabel(page: Page, label: string) {
  await expect(page.locator(`[data-testid="discovery-preview-item"][data-label="${label}"]`)).toHaveCount(0);
}

export async function expectNoDiscoveryCandidateLabel(page: Page, label: string) {
  await expect(page.locator(`[data-testid="discovery-candidate-item"][data-label="${label}"]`)).toHaveCount(0);
}

export { multiSpaceFixture };

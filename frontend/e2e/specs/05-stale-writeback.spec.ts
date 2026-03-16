import { test } from "@playwright/test";

import {
  expectDiscoveryPreviewContains,
  expectNoDiscoveryPreviewLabel,
  fillDiscoverySearch,
  goToDiscovery,
  gotoApp,
  multiSpaceFixture,
  switchSpace,
} from "../helpers";

test("late discovery preview response cannot write back into a newer space session", async ({ page }) => {
  await page.route("**/api/discovery/entity_candidates", async (route) => {
    const headers = route.request().headers();
    const body = route.request().postDataJSON() as { q?: string; page_size?: number };
    const isPreview = Number(body.page_size || 0) === 10;
    const isDemoRequest =
      String(headers["x-kg-space"] || "") === multiSpaceFixture.spaces.demo.spaceName &&
      String(body.q || "").includes(multiSpaceFixture.spaces.demo.searchTerm);
    if (isPreview && isDemoRequest) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    await route.continue();
  });

  await gotoApp(page);
  await switchSpace(page, multiSpaceFixture.spaces.demo);
  await goToDiscovery(page);
  await fillDiscoverySearch(page, multiSpaceFixture.spaces.demo.searchTerm);
  await page.waitForTimeout(400);

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await goToDiscovery(page);
  await fillDiscoverySearch(page, multiSpaceFixture.spaces.small.searchTerm);
  await expectDiscoveryPreviewContains(page, multiSpaceFixture.spaces.small);
  await expectNoDiscoveryPreviewLabel(page, multiSpaceFixture.spaces.demo.expected.label);

  await page.waitForTimeout(1800);
  await expectDiscoveryPreviewContains(page, multiSpaceFixture.spaces.small);
  await expectNoDiscoveryPreviewLabel(page, multiSpaceFixture.spaces.demo.expected.label);
});

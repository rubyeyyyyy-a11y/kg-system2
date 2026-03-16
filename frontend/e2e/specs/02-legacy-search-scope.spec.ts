import { test, expect } from "@playwright/test";

import {
  expectDiscoveryCandidatesContain,
  fillDiscoverySearch,
  gotoApp,
  multiSpaceFixture,
  switchSpace,
} from "../helpers";

test("@smoke discovery candidate search stays scoped to the selected space", async ({ page }) => {
  await gotoApp(page);

  await switchSpace(page, multiSpaceFixture.spaces.demo);
  await fillDiscoverySearch(page, multiSpaceFixture.spaces.demo.searchTerm);
  await page.getByTestId("discovery-search-submit").click();
  await expectDiscoveryCandidatesContain(page, multiSpaceFixture.spaces.demo);

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await expect(page.locator(`[data-testid="discovery-candidate-item"][data-label="${multiSpaceFixture.spaces.demo.expected.label}"]`)).toHaveCount(0);
  await fillDiscoverySearch(page, multiSpaceFixture.spaces.small.searchTerm);
  await page.getByTestId("discovery-search-submit").click();
  await expectDiscoveryCandidatesContain(page, multiSpaceFixture.spaces.small);
  await expect(page.locator(`[data-testid="discovery-candidate-item"][data-label="${multiSpaceFixture.spaces.demo.expected.label}"]`)).toHaveCount(0);
});

import { test, expect } from "@playwright/test";

import {
  expectLegacySearchResultContains,
  fillLegacySearch,
  goToLegacy,
  gotoApp,
  multiSpaceFixture,
  switchSpace,
} from "../helpers";

test("@smoke legacy search results stay scoped to the selected space", async ({ page }) => {
  await gotoApp(page);

  await switchSpace(page, multiSpaceFixture.spaces.demo);
  await goToLegacy(page);
  await fillLegacySearch(page, multiSpaceFixture.spaces.demo.searchTerm);
  await page.getByTestId("legacy-search-submit").click();
  await expectLegacySearchResultContains(page, multiSpaceFixture.spaces.demo);

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await goToLegacy(page);
  await expect(page.locator(`[data-testid="legacy-search-result-item"][data-label="${multiSpaceFixture.spaces.demo.expected.label}"]`)).toHaveCount(0);
  await fillLegacySearch(page, multiSpaceFixture.spaces.small.searchTerm);
  await page.getByTestId("legacy-search-submit").click();
  await expectLegacySearchResultContains(page, multiSpaceFixture.spaces.small);
  await expect(page.locator(`[data-testid="legacy-search-result-item"][data-label="${multiSpaceFixture.spaces.demo.expected.label}"]`)).toHaveCount(0);
});

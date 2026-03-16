import { test } from "@playwright/test";

import {
  expectDiscoveryCandidatesContain,
  expectDiscoveryPreviewContains,
  expectNoDiscoveryCandidateLabel,
  expectNoDiscoveryPreviewLabel,
  fillDiscoverySearch,
  goToDiscovery,
  gotoApp,
  multiSpaceFixture,
  switchSpace,
} from "../helpers";

test("discovery preview and candidate list reset on space switch", async ({ page }) => {
  await gotoApp(page);

  await switchSpace(page, multiSpaceFixture.spaces.demo);
  await goToDiscovery(page);
  await fillDiscoverySearch(page, multiSpaceFixture.spaces.demo.searchTerm);
  await expectDiscoveryPreviewContains(page, multiSpaceFixture.spaces.demo);
  await page.getByTestId("discovery-search-submit").click();
  await expectDiscoveryCandidatesContain(page, multiSpaceFixture.spaces.demo);

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await goToDiscovery(page);
  await expectNoDiscoveryPreviewLabel(page, multiSpaceFixture.spaces.demo.expected.label);
  await expectNoDiscoveryCandidateLabel(page, multiSpaceFixture.spaces.demo.expected.label);
  await fillDiscoverySearch(page, multiSpaceFixture.spaces.small.searchTerm);
  await expectDiscoveryPreviewContains(page, multiSpaceFixture.spaces.small);
  await page.getByTestId("discovery-search-submit").click();
  await expectDiscoveryCandidatesContain(page, multiSpaceFixture.spaces.small);
});

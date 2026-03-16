import { test } from "@playwright/test";

import {
  expectDiscoveryCandidatesContain,
  expectDiscoveryPreviewContains,
  expectNoDiscoveryCandidateLabel,
  expectNoDiscoveryPreviewLabel,
  fillDiscoveryRawId,
  fillDiscoverySearch,
  gotoApp,
  multiSpaceFixture,
  switchSpace,
} from "../helpers";

test("discovery preview stays in the active space after switching", async ({ page }) => {
  await gotoApp(page);

  await switchSpace(page, multiSpaceFixture.spaces.demo);
  await fillDiscoverySearch(page, multiSpaceFixture.spaces.demo.suggestTerm);
  await expectDiscoveryPreviewContains(page, multiSpaceFixture.spaces.demo);

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await expectNoDiscoveryPreviewLabel(page, multiSpaceFixture.spaces.demo.expected.label);
  await fillDiscoverySearch(page, multiSpaceFixture.spaces.small.suggestTerm);
  await expectDiscoveryPreviewContains(page, multiSpaceFixture.spaces.small);
  await expectNoDiscoveryPreviewLabel(page, multiSpaceFixture.spaces.demo.expected.label);
});

test("discovery raw_id search stays in the active space after switching", async ({ page }) => {
  await gotoApp(page);

  await switchSpace(page, multiSpaceFixture.spaces.demo);
  await fillDiscoveryRawId(page, multiSpaceFixture.spaces.demo.rawIdTerm);
  await page.getByTestId("discovery-search-submit").click();
  await expectDiscoveryCandidatesContain(page, multiSpaceFixture.spaces.demo);

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await expectNoDiscoveryCandidateLabel(page, multiSpaceFixture.spaces.demo.expected.label);
  await fillDiscoveryRawId(page, multiSpaceFixture.spaces.small.rawIdTerm);
  await page.getByTestId("discovery-search-submit").click();
  await expectDiscoveryCandidatesContain(page, multiSpaceFixture.spaces.small);
  await expectNoDiscoveryCandidateLabel(page, multiSpaceFixture.spaces.demo.expected.label);
});

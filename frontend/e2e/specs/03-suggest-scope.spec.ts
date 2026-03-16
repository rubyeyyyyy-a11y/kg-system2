import { test } from "@playwright/test";

import {
  expectLegacyRawIdSuggestContains,
  expectLegacySuggestContains,
  expectNoLegacyRawId,
  expectNoLegacySuggestLabel,
  fillLegacyRawId,
  fillLegacySearch,
  goToLegacy,
  gotoApp,
  multiSpaceFixture,
  switchSpace,
} from "../helpers";

test("name suggest stays in the active space after switching", async ({ page }) => {
  await gotoApp(page);

  await switchSpace(page, multiSpaceFixture.spaces.demo);
  await goToLegacy(page);
  await fillLegacySearch(page, multiSpaceFixture.spaces.demo.suggestTerm);
  await expectLegacySuggestContains(page, multiSpaceFixture.spaces.demo);

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await goToLegacy(page);
  await expectNoLegacySuggestLabel(page, multiSpaceFixture.spaces.demo.expected.label);
  await fillLegacySearch(page, multiSpaceFixture.spaces.small.suggestTerm);
  await expectLegacySuggestContains(page, multiSpaceFixture.spaces.small);
  await expectNoLegacySuggestLabel(page, multiSpaceFixture.spaces.demo.expected.label);
});

test("raw_id suggest stays in the active space after switching", async ({ page }) => {
  await gotoApp(page);

  await switchSpace(page, multiSpaceFixture.spaces.demo);
  await goToLegacy(page);
  await fillLegacyRawId(page, multiSpaceFixture.spaces.demo.rawIdTerm);
  await expectLegacyRawIdSuggestContains(page, multiSpaceFixture.spaces.demo);

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await goToLegacy(page);
  await expectNoLegacyRawId(page, multiSpaceFixture.spaces.demo.expected.rawId);
  await fillLegacyRawId(page, multiSpaceFixture.spaces.small.rawIdTerm);
  await expectLegacyRawIdSuggestContains(page, multiSpaceFixture.spaces.small);
  await expectNoLegacyRawId(page, multiSpaceFixture.spaces.demo.expected.rawId);
});

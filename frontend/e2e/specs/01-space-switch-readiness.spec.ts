import { test, expect } from "@playwright/test";

import { gotoApp, multiSpaceFixture, switchSpace } from "../helpers";

test("@smoke switches current space and readiness without regressing canonical status", async ({ page }) => {
  await gotoApp(page);

  await switchSpace(page, multiSpaceFixture.spaces.demo);
  await expect(page.getByTestId("current-space-display")).toHaveAttribute("data-registry-status", "ready");
  await expect(page.getByTestId("current-space-readiness-display")).toHaveAttribute("data-index-status", "verified_nonempty");

  await switchSpace(page, multiSpaceFixture.spaces.small);
  await expect(page.getByTestId("current-space-display")).toHaveAttribute("data-registry-status", "ready");
  await expect(page.getByTestId("current-space-readiness-display")).toHaveAttribute("data-index-status", "verified_nonempty");
});

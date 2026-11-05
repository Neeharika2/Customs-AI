import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

const SEED = path.resolve(process.cwd(), "../seed/output");

function ref(prefix = "SHP") {
  return `${prefix}-${Date.now().toString().slice(-7)}`;
}

async function login(page: Page, role: "Executive" | "Manager") {
  await page.goto("/login");
  await page.getByRole("button", { name: role }).click();
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/shipments$/);
}

async function createShipment(
  page: Page,
  shipmentRef: string,
  supplier = "Company C (SE)",
  currency = "USD",
  incoterm = "FOB",
) {
  await page.getByRole("button", { name: "New shipment" }).click();
  await page.getByLabel("Shipment reference").fill(shipmentRef);
  await page.getByLabel("Supplier").selectOption({ label: supplier });
  await page.getByLabel("Invoice currency").selectOption(currency);
  await page.getByLabel("Incoterm").selectOption(incoterm);
  await page.getByRole("button", { name: "Create shipment" }).click();
  await expect(page.getByRole("heading", { name: shipmentRef })).toBeVisible();
}

async function upload(page: Page, index: number, file: string) {
  const slot = page.locator(".doc-slot").nth(index);
  await slot.locator('input[type="file"]').setInputFiles(path.join(SEED, file));
}

test("executive uploads, reviews and submits; manager approves and exports", async ({ browser, page }) => {
  const shipmentRef = ref("SHP-E2E");

  await login(page, "Executive");
  await createShipment(page, shipmentRef, "Company C (SE)", "EUR", "CIF");

  await upload(page, 0, "SHP-24812/invoice.pdf");
  await upload(page, 1, "SHP-24812/packing.pdf");
  await upload(page, 2, "SHP-24812/bl.pdf");

  await expect(page.getByText(/3 extracted/)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: /Review shipment|Open review/ }).click();
  await expect(page.locator(".review")).toBeVisible();
  await expect(page.getByText("Extracted data")).toBeVisible();

  // Correct a line item and prove the checks rerun.
  await page.locator(".line-edit-btn").first().click();
  const lineModal = page.locator(".modal");
  await lineModal.getByLabel("Quantity").fill("181");
  await lineModal.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByText(/open issues/)).toBeVisible({ timeout: 15_000 });

  await page.locator(".line-edit-btn").first().click();
  await lineModal.getByLabel("Quantity").fill("180");
  await lineModal.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByText("All checks clear")).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: "History" }).click();
  await expect(page.getByText(/line 1 corrected/i).first()).toBeVisible();
  await page.getByTitle("Close").click();

  await expect(page.getByRole("button", { name: /Confirm high-confidence/ })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: /Confirm high-confidence/ }).click();
  await expect(page.getByText("All checks clear")).toBeVisible({ timeout: 20_000 });

  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByText("Submitted for approval")).toBeVisible();
  await expect(page.locator(".pill-awaiting")).toBeVisible();

  const managerContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const managerPage = await managerContext.newPage();
  await login(managerPage, "Manager");
  await managerPage.getByPlaceholder("Search reference or supplier").fill(shipmentRef);
  await expect(managerPage.getByText(shipmentRef)).toBeVisible();
  await managerPage.getByText(shipmentRef).first().click();
  await managerPage.getByRole("button", { name: /Open review/ }).click();
  await expect(managerPage.locator(".pill-awaiting")).toBeVisible();

  await managerPage.getByRole("button", { name: "Approve shipment" }).click();
  await expect(managerPage.locator(".modal")).toBeVisible();
  await managerPage.locator(".modal").getByRole("button", { name: "Approve", exact: true }).click();
  await expect(managerPage.getByText("Shipment approved")).toBeVisible();
  await expect(managerPage.locator(".pill-ready")).toBeVisible();

  await managerPage.getByRole("button", { name: "Export" }).click();
  await expect(managerPage).toHaveURL(/\/export$/);

  const [download] = await Promise.all([
    managerPage.waitForEvent("download"),
    managerPage.getByRole("button", { name: "Generate CSV" }).click(),
  ]);
  const csvPath = await download.path();
  const content = await fs.readFile(csvPath, "utf-8");

  expect(content.charCodeAt(0)).toBe(0xfeff);
  expect(content).toContain("Invoice No");
  expect(content).toContain("INV-24812");
  expect(content).toContain("Steel ball valve DN50");
  expect(download.suggestedFilename()).toMatch(/\.csv$/);

  // Reopen voids the approval and returns the shipment to review.
  await managerPage.goto(managerPage.url().replace("/export", "/review"));
  await expect(managerPage.getByRole("button", { name: "Reopen" })).toBeVisible();
  await managerPage.getByRole("button", { name: "Reopen" }).click();
  await expect(managerPage.locator(".modal")).toBeVisible();
  await managerPage.locator(".modal").getByRole("button", { name: "Reopen", exact: true }).click();
  await expect(managerPage.getByText("Shipment reopened for review")).toBeVisible();
  await expect(managerPage.locator(".pill-review")).toBeVisible();

  await managerContext.close();
});

test("manual entry recovers an unreadable document", async ({ page }) => {
  const shipmentRef = ref("SHP-MAN");

  await login(page, "Executive");
  await createShipment(page, shipmentRef, "Company E (IN)");

  await upload(page, 0, "SHP-24816/invoice.pdf");
  await upload(page, 1, "SHP-24816/packing.pdf");
  await upload(page, 2, "SHP-24816/bl-illegible.pdf");

  await expect(page.getByText("Manual entry", { exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: /Review shipment|Open review/ }).click();

  await expect(page.getByText("needs manual entry")).toBeVisible();
  await page.getByLabel("B/L number").fill("BL-24816");
  await page.getByLabel("B/L date").fill("22/10/2026");
  await page.getByLabel("Shipper").fill("Company E");
  await page.getByLabel("Consignee").fill("Mumbai Electricals Pvt Ltd");
  await page.getByLabel("Containers").fill("MSCU1234566, MSCU7654329");
  await page.getByLabel("Packages").fill("40");
  await page.getByLabel("Gross weight kg").fill("761.00");
  await page.getByRole("button", { name: "Save manual entry" }).click();

  await expect(page.getByText("Manual entry saved")).toBeVisible();
  await expect(page.getByText("needs manual entry")).toBeHidden();
  await expect(page.getByText("B/L number", { exact: true })).toBeVisible();
});

test("export is blocked while a shipment is unresolved", async ({ page }) => {
  await login(page, "Executive");
  await page.getByText("SHP-24811").first().click();
  await expect(page.getByRole("heading", { name: "SHP-24811" })).toBeVisible();
  const url = page.url();
  await page.goto(`${url}/export`);

  await expect(page.getByText(/blocked/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate CSV" })).toBeDisabled();
  await expect(page.getByText(/needs confirmation/).first()).toBeVisible();
});

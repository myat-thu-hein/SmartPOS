import { expect, test, type Page } from "@playwright/test";

// Demo accounts from the development seed. The password is DEMO_PASSWORD.
const PASSWORD = process.env.E2E_PASSWORD ?? process.env.DEMO_PASSWORD ?? "";

async function signIn(page: Page, email: string) {
  test.skip(!PASSWORD, "Set E2E_PASSWORD (the DEMO_PASSWORD used when seeding) to run UI smoke tests.");
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

test("unauthenticated visitors are sent to the sign-in page", async ({ page }) => {
  await page.goto("/inventory");
  await expect(page).toHaveURL(/\/login\?next=%2Finventory/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("cashier sells, kitchen prepares", async ({ page, browser }) => {
  await signIn(page, "cashier@smartpos.demo");
  await page.goto("/pos");
  await page.getByRole("button", { name: /Add Drinking Water/ }).click();
  await page.getByRole("button", { name: /Add Pad Thai Goong/ }).click();
  const options = page.getByRole("dialog");
  await options.getByRole("button", { name: /^Add/ }).click();
  await expect(page.getByText("Subtotal")).toBeVisible();

  await page.locator("#pos-pay-button").click();
  const pay = page.getByRole("dialog");
  await pay.getByRole("radio", { name: /Cash/ }).click();
  await page.locator("#pay-tendered").fill("1000");
  await pay.getByRole("button", { name: /^Record/ }).click();
  const paid = page.getByRole("heading", { name: /paid$/ });
  await expect(paid).toBeVisible();
  const orderNumber = ((await paid.textContent()) ?? "").match(/#(\S+)/)?.[1];
  expect(orderNumber).toBeTruthy();

  const kitchenContext = await browser.newContext();
  const kitchen = await kitchenContext.newPage();
  await signIn(kitchen, "kitchen@smartpos.demo");
  await expect(kitchen).toHaveURL(/\/kitchen/);
  const ticket = kitchen.locator("article", { hasText: `#${orderNumber}` });
  await expect(ticket).toBeVisible();
  await ticket.getByRole("button", { name: "Start preparing" }).click();
  await expect(kitchen.getByRole("region", { name: /Preparing/ }).getByText(`#${orderNumber}`)).toBeVisible();
  await kitchenContext.close();
});

test("cashier cannot open manager pages; manager sees analytics", async ({ page, browser }) => {
  await signIn(page, "cashier@smartpos.demo");
  await expect(page.getByRole("link", { name: "Inventory" })).toHaveCount(0);
  await page.goto("/inventory");
  await expect(page.getByText("Your role does not include access to this page.")).toBeVisible();

  const managerContext = await browser.newContext();
  const manager = await managerContext.newPage();
  await signIn(manager, "manager@smartpos.demo");
  await manager.goto("/analytics");
  await expect(manager.getByText("Net sales")).toBeVisible();
  await manager.getByRole("group", { name: "Sales by day view" }).getByRole("button", { name: "table" }).click();
  await expect(manager.getByRole("columnheader", { name: "Total billed" })).toBeVisible();
  await managerContext.close();
});

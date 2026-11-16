import { expect, test, type Browser, type Page } from "@playwright/test";

// Real-time sync, smart POS suggestions, navigation and demo sign-in, against a
// running stack seeded with the demo restaurant (see playwright.config.ts).
const PASSWORD = process.env.E2E_PASSWORD ?? process.env.DEMO_PASSWORD ?? "";

async function signedInPage(browser: Browser, email: string, path: string): Promise<Page> {
  test.skip(!PASSWORD, "Set E2E_PASSWORD (the DEMO_PASSWORD used when seeding) to run UI tests.");
  const page = await (await browser.newContext()).newPage();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await page.goto(path);
  return page;
}

test("a cashier's order reaches the kitchen live, and the cashier hears when it is ready", async ({ browser }) => {
  // Open the kitchen and dashboard first: they must update without reloading.
  const kitchen = await signedInPage(browser, "kitchen@smartpos.demo", "/kitchen");
  await expect(kitchen.getByRole("status").filter({ hasText: /^Live/ })).toBeVisible({ timeout: 20_000 });
  const manager = await signedInPage(browser, "manager@smartpos.demo", "/dashboard");
  await expect(manager.getByRole("status").filter({ hasText: /^Live/ })).toBeVisible({ timeout: 20_000 });
  const dashboardRefetches: number[] = [];
  manager.on("request", (r) => {
    if (r.url().includes("/api/v1/analytics/dashboard")) dashboardRefetches.push(Date.now());
  });

  const cashier = await signedInPage(browser, "cashier@smartpos.demo", "/pos");
  await cashier.getByRole("button", { name: /^Add Drinking Water/ }).click();
  await cashier.getByRole("radio", { name: "Takeaway" }).click();
  const [created] = await Promise.all([
    cashier.waitForResponse((r) => r.url().endsWith("/api/v1/orders") && r.request().method() === "POST"),
    cashier.getByRole("button", { name: "Send to kitchen" }).click(),
  ]);
  const order = (await created.json()) as { display_number: string };
  const sentAt = Date.now();

  const ticket = kitchen.locator("article", { hasText: `#${order.display_number}` });
  await expect(ticket).toBeVisible({ timeout: 10_000 });
  await expect.poll(() => dashboardRefetches.some((t) => t >= sentAt - 100), { timeout: 10_000 }).toBe(true);

  await ticket.getByRole("button", { name: "Start preparing" }).click();
  await ticket.getByRole("button", { name: "Mark ready" }).click();
  await expect(cashier.getByText(`Order #${order.display_number} is ready`)).toBeVisible({ timeout: 10_000 });
});

test("the POS suggests what guests order together, and the suggestion adds it", async ({ browser }) => {
  const pos = await signedInPage(browser, "cashier@smartpos.demo", "/pos");
  const suggestions = pos.getByRole("region", { name: "Suggestions" });
  await expect(suggestions).toBeVisible({ timeout: 20_000 }); // empty cart: popular items
  await pos.getByRole("button", { name: /^Add Green Curry Chicken/ }).click();
  const options = pos.getByRole("dialog");
  if (await options.isVisible().catch(() => false)) await options.getByRole("button", { name: /^Add/ }).click();
  await expect(suggestions.getByText("Often ordered together")).toBeVisible({ timeout: 10_000 });
  const rice = suggestions.getByRole("button", { name: /Suggested: add Steamed Jasmine Rice/ });
  await expect(rice).toContainText(/In \d+% of orders with Green Curry Chicken/);
  await rice.click();
  // The product card now shows it in the cart, and it is no longer suggested.
  await expect(pos.getByRole("button", { name: /^Add Steamed Jasmine Rice.*1 in cart$/ })).toBeVisible();
  await expect(suggestions.getByRole("button", { name: /Suggested: add Steamed Jasmine Rice/ })).toHaveCount(0);
});

test("the command palette jumps to a page", async ({ browser }) => {
  const page = await signedInPage(browser, "manager@smartpos.demo", "/dashboard");
  // The shortcut is registered once the app shell has loaded the session.
  await expect(page.getByRole("button", { name: "Search pages and actions" })).toBeVisible();
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox", { name: "Search pages and actions" }).fill("invent");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/inventory$/);
  await expect(page.getByRole("columnheader", { name: "Lasts" })).toBeVisible();
});

test("one-click demo sign-in, when the server enables it", async ({ page, request }) => {
  const demo = (await (await request.get("/api/v1/auth/demo")).json()) as { enabled: boolean };
  test.skip(!demo.enabled, "Demo sign-in is off (set DEMO_LOGIN_ENABLED=true on the backend to test it).");
  await page.goto("/login");
  await page.getByRole("button", { name: /^Kitchen/ }).click();
  await expect(page).toHaveURL(/\/kitchen/);
  await expect(page.getByRole("heading", { name: /Kitchen Display/ })).toBeVisible();
});

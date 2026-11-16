import { expect, test } from "@playwright/test";

// Sign-in, sign-out and password-reset journeys against a running stack with demo data.
const PASSWORD = process.env.E2E_PASSWORD ?? process.env.DEMO_PASSWORD ?? "";

test.beforeEach(() => {
  test.skip(!PASSWORD, "Set E2E_PASSWORD (the DEMO_PASSWORD used when seeding) to run UI tests.");
});

test("a wrong password is explained, then the right one signs in", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("manager@smartpos.demo");
  await page.getByLabel("Password", { exact: true }).fill("definitely-wrong-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  // (Next.js's route announcer is also role="alert", so match the message itself.)
  await expect(page.getByRole("alert").filter({ hasText: "Email or password is incorrect" })).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();

  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard/);
});

test("signing out explains where you are, and the sign-in page knows who was signed in", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("cashier@smartpos.demo");
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);

  // Back on /login while signed in: continue or switch account, no empty form.
  await page.goto("/login");
  await expect(page.getByText("You're already signed in")).toBeVisible();
  await page.getByRole("button", { name: "Use another account" }).click();
  await expect(page).toHaveURL(/reason=signedout/);
  await expect(page.getByRole("status").filter({ hasText: "You're signed out" })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("an incomplete reset link explains what to do", async ({ page }) => {
  await page.goto("/reset-password");
  await expect(page.getByRole("heading", { name: "This link can't be used" })).toBeVisible();
  await page.getByRole("link", { name: "Request a new link" }).click();
  await expect(page).toHaveURL(/\/forgot-password/);
  await page.getByLabel("Email").fill("someone@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("heading", { name: "Check your inbox" })).toBeVisible();
});

import { describe, expect, it } from "vitest";

import { homePath, visibleNavItems } from "@/lib/navigation";

// Mirrors ROLE_PERMISSIONS in backend/app/core/permissions.py for the roles shown.
const CASHIER = [
  "menu:read",
  "tables:read",
  "tables:operate",
  "orders:read",
  "orders:create",
  "orders:complete",
  "orders:cancel_draft",
  "payments:record",
  "discounts:apply",
  "kitchen:read",
  "customers:read",
  "customers:create",
  "settings:read",
];
const KITCHEN = ["menu:read", "kitchen:read", "kitchen:update"];

describe("navigation by role", () => {
  it("shows cashiers front-of-house pages only", () => {
    const labels = visibleNavItems(CASHIER).map((i) => i.label);
    expect(labels).toEqual(["Dashboard", "POS", "Orders", "Tables", "Kitchen Display", "Customers"]);
    expect(labels).not.toContain("Inventory");
    expect(labels).not.toContain("Settings");
  });

  it("sends kitchen staff straight to the kitchen display", () => {
    expect(visibleNavItems(KITCHEN).map((i) => i.href)).toEqual(["/kitchen"]);
    expect(homePath(KITCHEN)).toBe("/kitchen");
  });

  it("shows administration only with the platform permission", () => {
    expect(visibleNavItems(["platform:admin"]).map((i) => i.href)).toEqual(["/admin"]);
    expect(homePath([])).toBe("/no-access");
  });
});

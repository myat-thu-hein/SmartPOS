import { describe, expect, it } from "vitest";

import { loginSchema } from "@/app/login/login-form";
import { productSchema, toProductPayload } from "@/features/menu/product-form";
import { estimateLineMinor, priceDeviation, unitFactor } from "@/features/purchasing/units";
import { passwordProblems } from "@/lib/password";

describe("login form", () => {
  it("requires a valid email and a password", () => {
    expect(loginSchema.safeParse({ email: "manager@smartpos.demo", password: "x" }).success).toBe(true);
    const bad = loginSchema.safeParse({ email: "not-an-email", password: "" });
    expect(bad.success).toBe(false);
    expect(bad.error?.issues.map((i) => i.message)).toEqual(["Enter a valid email address", "Enter your password"]);
  });
});

describe("product form", () => {
  const base = {
    name: " Pad Thai ",
    category_id: "c1",
    price: "120.50",
    sku: "",
    description: "",
    image_url: "",
    is_available: true,
    modifier_group_ids: [],
  };

  it("converts the price to satang and blanks to null", () => {
    const values = productSchema.parse(base);
    expect(toProductPayload(values)).toEqual({
      name: "Pad Thai",
      category_id: "c1",
      price_minor: 12050,
      sku: null,
      description: null,
      image_url: null,
      is_available: true,
    });
  });

  it("rejects bad prices, SKUs and image URLs", () => {
    const result = productSchema.safeParse({ ...base, price: "12.345", sku: "a b", image_url: "javascript:alert(1)" });
    expect(result.success).toBe(false);
    expect(result.error?.issues.map((i) => i.path[0]).sort()).toEqual(["image_url", "price", "sku"]);
  });
});

describe("password rules", () => {
  it("matches the backend policy", () => {
    expect(passwordProblems("Strong-pass-42")).toEqual([]);
    expect(passwordProblems("short1")).toContain("At least 8 characters.");
    expect(passwordProblems("12345678")).toContain("Mix letters with numbers or symbols.");
    expect(passwordProblems("onlyletters")).toContain("Mix letters with numbers or symbols.");
    expect(passwordProblems("รหัสผ่านไทยยาว")).toContain("Mix letters with numbers or symbols.");
    expect(passwordProblems("รหัสผ่าน2026")).toEqual([]);
  });
});

describe("purchase order estimates", () => {
  const rice = { base_unit: "g" as const, units: [{ id: "u", unit_name: "sack", factor_to_base: 25000 }] };

  it("knows standard and custom units", () => {
    expect(unitFactor(rice, "kg")).toBe(1000);
    expect(unitFactor(rice, "Sack")).toBe(25000);
    expect(unitFactor(rice, "ml")).toBeNull();
    expect(estimateLineMinor(2.5, 4000)).toBe(10000);
  });

  it("flags prices far from the expected price", () => {
    expect(priceDeviation(100, 100)).toBeNull();
    expect(priceDeviation(1000, 18)).toBeCloseTo(55.6, 1);
    expect(priceDeviation(5, 18)).toBeCloseTo(0.28, 2);
    expect(priceDeviation(10, 0)).toBeNull();
  });
});

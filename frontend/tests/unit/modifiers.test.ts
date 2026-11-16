import { describe, expect, it } from "vitest";

import { activeGroups, defaultSelection, needsModifierDialog, selectionErrors } from "@/features/pos/modifiers";
import type { ModifierGroup, ModifierOption, Product } from "@/types/api";

function option(id: string, extra: Partial<ModifierOption> = {}): ModifierOption {
  return {
    id,
    group_id: "g",
    name: id,
    price_delta_minor: 0,
    is_default: false,
    is_active: true,
    display_order: 0,
    ingredient_id: null,
    ingredient_quantity: null,
    ...extra,
  };
}

function group(id: string, extra: Partial<ModifierGroup>): ModifierGroup {
  return {
    id,
    name: id,
    description: null,
    selection_type: "SINGLE",
    min_select: 0,
    max_select: 1,
    display_order: 0,
    is_active: true,
    options: [],
    ...extra,
  };
}

function product(groups: ModifierGroup[]): Product {
  return {
    id: "p",
    category_id: "c",
    category_name: null,
    name: "Pad Thai",
    description: null,
    sku: null,
    image_url: null,
    price_minor: 12000,
    is_available: true,
    is_active: true,
    has_recipe: false,
    modifier_groups: groups,
    created_at: "",
    updated_at: "",
  };
}

const spice = group("Spice", { min_select: 1, options: [option("mild", { is_default: true }), option("hot")] });
const toppings = group("Toppings", {
  selection_type: "MULTIPLE",
  max_select: 2,
  options: [option("egg"), option("shrimp"), option("tofu"), option("old", { is_active: false })],
});
const hidden = group("Hidden", { is_active: false, options: [option("x")] });

describe("modifier selection", () => {
  it("ignores inactive groups and options", () => {
    const groups = activeGroups(product([spice, toppings, hidden]));
    expect(groups.map((g) => g.id)).toEqual(["Spice", "Toppings"]);
    expect(groups[1].options.map((o) => o.id)).toEqual(["egg", "shrimp", "tofu"]);
    expect(needsModifierDialog(product([hidden]))).toBe(false);
  });

  it("pre-selects defaults and enforces minimum and maximum choices", () => {
    const p = product([spice, toppings]);
    const selection = defaultSelection(p);
    expect(selection).toEqual({ Spice: ["mild"], Toppings: [] });
    expect(selectionErrors(p, selection)).toEqual([]);
    expect(selectionErrors(p, { Spice: [], Toppings: [] })).toEqual(["Choose at least 1 for Spice."]);
    expect(selectionErrors(p, { Spice: ["mild"], Toppings: ["egg", "shrimp", "tofu"] })).toEqual([
      "Choose at most 2 for Toppings.",
    ]);
  });
});

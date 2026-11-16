import { describe, expect, it } from "vitest";

import { cartReducer, estimatedSubtotal, itemCount, MAX_QUANTITY, toOrderItems, unitPrice, type CartLine } from "@/features/pos/cart";

const padThai = { productId: "p1", name: "Pad Thai", basePriceMinor: 12000, quantity: 1, modifiers: [], notes: "" };
const large = { optionId: "o-large", groupName: "Size", name: "Large", priceDeltaMinor: 2000 };

function add(lines: CartLine[], line: Omit<CartLine, "lineId">, lineId?: string) {
  return cartReducer(lines, { type: "add", line, lineId });
}

describe("cartReducer", () => {
  it("merges identical lines and keeps different modifiers or notes apart", () => {
    let lines = add([], padThai, "a");
    lines = add(lines, padThai);
    expect(lines).toHaveLength(1);
    expect(lines[0].quantity).toBe(2);

    lines = add(lines, { ...padThai, modifiers: [large] }, "b");
    lines = add(lines, { ...padThai, notes: "no peanuts" }, "c");
    expect(lines.map((l) => l.lineId)).toEqual(["a", "b", "c"]);
  });

  it("removes a line when its quantity reaches zero and caps large quantities", () => {
    let lines = add([], padThai, "a");
    lines = cartReducer(lines, { type: "setQuantity", lineId: "a", quantity: 5000 });
    expect(lines[0].quantity).toBe(MAX_QUANTITY);
    lines = cartReducer(lines, { type: "setQuantity", lineId: "a", quantity: 2.7 });
    expect(lines[0].quantity).toBe(2);
    lines = cartReducer(lines, { type: "increment", lineId: "a", by: -2 });
    expect(lines).toEqual([]);
  });

  it("limits notes to 300 characters and supports clear", () => {
    let lines = add([], padThai, "a");
    lines = cartReducer(lines, { type: "setNotes", lineId: "a", notes: "x".repeat(400) });
    expect(lines[0].notes).toHaveLength(300);
    expect(cartReducer(lines, { type: "clear" })).toEqual([]);
  });
});

describe("cart totals", () => {
  it("adds modifier price deltas to the unit price", () => {
    const lines = add(add([], { ...padThai, modifiers: [large] }, "a"), { ...padThai, quantity: 2 }, "b");
    expect(unitPrice(lines[0])).toBe(14000);
    expect(estimatedSubtotal(lines)).toBe(14000 + 2 * 12000);
    expect(itemCount(lines)).toBe(3);
  });

  it("builds the API payload without client prices", () => {
    const lines = add([], { ...padThai, modifiers: [large], notes: "  extra lime " }, "a");
    expect(toOrderItems(lines)).toEqual([
      { product_id: "p1", quantity: 1, modifier_option_ids: ["o-large"], notes: "extra lime" },
    ]);
    expect(JSON.stringify(toOrderItems(lines))).not.toContain("12000");
  });
});

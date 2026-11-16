import { describe, expect, it } from "vitest";

import {
  bahtToMinorString,
  formatMoney,
  formatMoneyCompact,
  formatPct,
  formatQty,
  formatUnitCost,
  humanize,
  minutesSince,
  parseMoney,
} from "@/lib/format";

describe("money", () => {
  it("formats satang as Thai baht", () => {
    expect(formatMoney(12050)).toBe("฿120.50");
    expect(formatMoney(0)).toBe("฿0.00");
    expect(formatMoney(null)).toBe("฿0.00");
    expect(formatMoneyCompact(1_250_000)).toBe("฿12.5K");
  });

  it("parses typed amounts exactly, without floating point", () => {
    expect(parseMoney("120")).toBe(12000);
    expect(parseMoney("120.5")).toBe(12050);
    expect(parseMoney("1,234.56")).toBe(123456);
    expect(parseMoney("0.29")).toBe(29);
    expect(parseMoney("12.345")).toBeNull();
    expect(parseMoney("-5")).toBeNull();
    expect(parseMoney("abc")).toBeNull();
  });

  it("converts fractional per-unit prices to minor-unit strings", () => {
    expect(bahtToMinorString("0.18")).toBe("18");
    expect(bahtToMinorString("0.0123")).toBe("1.23");
    expect(bahtToMinorString("1.1")).toBe("110");
    expect(bahtToMinorString("-1")).toBeNull();
    expect(bahtToMinorString("x")).toBeNull();
  });

  it("shows gram and millilitre costs per kg and litre", () => {
    expect(formatUnitCost(18, "g")).toBe("฿180.00/kg");
    expect(formatUnitCost(6, "ml")).toBe("฿60.00/L");
    expect(formatUnitCost(500, "piece")).toBe("฿5.00/piece");
    expect(formatUnitCost(null, "g")).toBe("—");
  });
});

describe("other formatters", () => {
  it("formats quantities in readable units", () => {
    expect(formatQty(2500, "g")).toBe("2.5 kg");
    expect(formatQty(750, "ml")).toBe("750 ml");
    expect(formatQty(3, "piece")).toBe("3 piece");
  });

  it("formats signed percentages and labels", () => {
    expect(formatPct(12.345)).toBe("+12.3%");
    expect(formatPct(-4)).toBe("-4.0%");
    expect(formatPct(null)).toBe("—");
    expect(humanize("PARTIALLY_RECEIVED")).toBe("Partially received");
  });

  it("never reports negative elapsed minutes", () => {
    const now = Date.parse("2026-10-25T10:00:00Z");
    expect(minutesSince("2026-10-25T09:45:30Z", now)).toBe(14);
    expect(minutesSince("2026-10-25T10:05:00Z", now)).toBe(0);
  });
});

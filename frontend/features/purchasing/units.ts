import type { Ingredient } from "@/types/api";

// Mirrors backend/app/services/units.py. The server stays authoritative; these
// are only used for on-screen estimates before a purchase order is saved.
const STANDARD: Record<string, Record<string, number>> = {
  g: { g: 1, kg: 1000 },
  ml: { ml: 1, l: 1000 },
  piece: { piece: 1, pcs: 1 },
};

/** How many base units one `unit` holds for this ingredient, or null if unknown. */
export function unitFactor(ingredient: Pick<Ingredient, "base_unit" | "units">, unit: string): number | null {
  const name = unit.trim().toLowerCase();
  const standard = STANDARD[ingredient.base_unit]?.[name];
  if (standard !== undefined) return standard;
  const custom = ingredient.units.find((u) => u.unit_name.toLowerCase() === name);
  return custom ? Number(custom.factor_to_base) : null;
}

/** Estimated line total in minor units from a quantity and a price, both in `unit`. */
export function estimateLineMinor(quantity: number, pricePerUnitMinor: number): number {
  if (!Number.isFinite(quantity) || !Number.isFinite(pricePerUnitMinor)) return 0;
  return Math.round(quantity * pricePerUnitMinor);
}

/** Ratio of an entered price to the expected one when it is suspiciously far off (≥2× or ≤½), else null. */
export function priceDeviation(enteredMinor: number, expectedMinor: number): number | null {
  if (!(expectedMinor > 0) || !(enteredMinor > 0)) return null;
  const ratio = enteredMinor / expectedMinor;
  return ratio >= 2 || ratio <= 0.5 ? ratio : null;
}

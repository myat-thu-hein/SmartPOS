import type { ModifierGroup, Product } from "@/types/api";

/** Groups and options a cashier can choose from (active only). */
export function activeGroups(product: Product): ModifierGroup[] {
  return product.modifier_groups
    .filter((g) => g.is_active)
    .map((g) => ({ ...g, options: g.options.filter((o) => o.is_active) }))
    .filter((g) => g.options.length > 0);
}

export function defaultSelection(product: Product): Record<string, string[]> {
  const selection: Record<string, string[]> = {};
  for (const group of activeGroups(product)) {
    selection[group.id] = group.options.filter((o) => o.is_default).map((o) => o.id);
  }
  return selection;
}

/** Validation messages mirroring the backend's selection rules. */
export function selectionErrors(product: Product, selection: Record<string, string[]>): string[] {
  const errors: string[] = [];
  for (const group of activeGroups(product)) {
    const chosen = selection[group.id] ?? [];
    const max = group.selection_type === "SINGLE" ? 1 : group.max_select;
    if (chosen.length < group.min_select) errors.push(`Choose at least ${group.min_select} for ${group.name}.`);
    if (max !== null && chosen.length > max) errors.push(`Choose at most ${max} for ${group.name}.`);
  }
  return errors;
}

export function needsModifierDialog(product: Product): boolean {
  return activeGroups(product).length > 0;
}

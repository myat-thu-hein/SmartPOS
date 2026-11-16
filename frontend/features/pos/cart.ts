// Pure cart state for the POS. Prices here are only for display while the
// server quote loads; the backend always recalculates authoritative totals.

export interface CartModifier {
  optionId: string;
  groupName: string;
  name: string;
  priceDeltaMinor: number;
}

export interface CartLine {
  lineId: string;
  productId: string;
  name: string;
  basePriceMinor: number;
  quantity: number;
  modifiers: CartModifier[];
  notes: string;
}

export type CartAction =
  | { type: "add"; line: Omit<CartLine, "lineId">; lineId?: string }
  | { type: "setQuantity"; lineId: string; quantity: number }
  | { type: "increment"; lineId: string; by: number }
  | { type: "remove"; lineId: string }
  | { type: "setNotes"; lineId: string; notes: string }
  | { type: "replace"; lines: CartLine[] }
  | { type: "clear" };

export const MAX_QUANTITY = 999;

function signature(line: Pick<CartLine, "productId" | "modifiers" | "notes">): string {
  const mods = line.modifiers.map((m) => m.optionId).sort().join(",");
  return `${line.productId}|${mods}|${line.notes.trim()}`;
}

let counter = 0;
export function newLineId(): string {
  counter += 1;
  return `line-${Date.now().toString(36)}-${counter}`;
}

export function cartReducer(lines: CartLine[], action: CartAction): CartLine[] {
  switch (action.type) {
    case "add": {
      const existing = lines.find((l) => signature(l) === signature(action.line));
      if (existing) {
        return lines.map((l) =>
          l.lineId === existing.lineId
            ? { ...l, quantity: Math.min(MAX_QUANTITY, l.quantity + action.line.quantity) }
            : l,
        );
      }
      return [...lines, { ...action.line, lineId: action.lineId ?? newLineId() }];
    }
    case "setQuantity": {
      if (action.quantity <= 0) return lines.filter((l) => l.lineId !== action.lineId);
      const quantity = Math.min(MAX_QUANTITY, Math.floor(action.quantity));
      return lines.map((l) => (l.lineId === action.lineId ? { ...l, quantity } : l));
    }
    case "increment": {
      const line = lines.find((l) => l.lineId === action.lineId);
      if (!line) return lines;
      return cartReducer(lines, { type: "setQuantity", lineId: action.lineId, quantity: line.quantity + action.by });
    }
    case "remove":
      return lines.filter((l) => l.lineId !== action.lineId);
    case "setNotes":
      return lines.map((l) => (l.lineId === action.lineId ? { ...l, notes: action.notes.slice(0, 300) } : l));
    case "replace":
      return action.lines;
    case "clear":
      return [];
  }
}

export function unitPrice(line: CartLine): number {
  return line.basePriceMinor + line.modifiers.reduce((sum, m) => sum + m.priceDeltaMinor, 0);
}

export function estimatedSubtotal(lines: CartLine[]): number {
  return lines.reduce((sum, l) => sum + unitPrice(l) * l.quantity, 0);
}

export function itemCount(lines: CartLine[]): number {
  return lines.reduce((sum, l) => sum + l.quantity, 0);
}

export function toOrderItems(lines: CartLine[]) {
  return lines.map((l) => ({
    product_id: l.productId,
    quantity: l.quantity,
    modifier_option_ids: l.modifiers.map((m) => m.optionId),
    notes: l.notes.trim() || null,
  }));
}

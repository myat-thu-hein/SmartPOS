"use client";

import { Minus, Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Product } from "@/types/api";

import type { CartLine } from "./cart";
import { activeGroups, defaultSelection, selectionErrors } from "./modifiers";

export function ModifierDialog({
  product,
  onClose,
  onAdd,
}: {
  product: Product;
  onClose: () => void;
  onAdd: (line: Omit<CartLine, "lineId">) => void;
}) {
  const groups = activeGroups(product);
  const [selection, setSelection] = useState<Record<string, string[]>>(() => defaultSelection(product));
  const [quantity, setQuantity] = useState(1);
  const [notes, setNotes] = useState("");
  const errors = selectionErrors(product, selection);
  const options = groups.flatMap((g) => g.options.map((o) => ({ group: g, option: o })));
  const chosen = options.filter(({ group, option }) => selection[group.id]?.includes(option.id));
  const unit = product.price_minor + chosen.reduce((s, c) => s + c.option.price_delta_minor, 0);

  function toggle(groupId: string, optionId: string, single: boolean) {
    setSelection((prev) => {
      const current = prev[groupId] ?? [];
      if (single) return { ...prev, [groupId]: [optionId] };
      return {
        ...prev,
        [groupId]: current.includes(optionId) ? current.filter((id) => id !== optionId) : [...current, optionId],
      };
    });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{product.name}</DialogTitle>
          <DialogDescription>{product.description || "Choose options"}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-5">
          {groups.map((group) => {
            const single = group.selection_type === "SINGLE";
            const rule = single
              ? group.min_select > 0
                ? "Required · choose 1"
                : "Optional · choose up to 1"
              : `${group.min_select > 0 ? `Choose at least ${group.min_select}` : "Optional"}${group.max_select ? ` · up to ${group.max_select}` : ""}`;
            return (
              <fieldset key={group.id} className="grid gap-2">
                <legend className="mb-1 flex w-full items-baseline justify-between text-sm font-medium">
                  {group.name}
                  <span className="text-xs font-normal text-muted-foreground">{rule}</span>
                </legend>
                <div className="grid gap-2 sm:grid-cols-2" role={single ? "radiogroup" : undefined}>
                  {group.options.map((option) => {
                    const checked = selection[group.id]?.includes(option.id) ?? false;
                    const id = `opt-${option.id}`;
                    return (
                      <label
                        key={option.id}
                        htmlFor={id}
                        className={cn(
                          "flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 text-sm hover:bg-accent",
                          checked && "border-primary bg-accent",
                        )}
                      >
                        {single ? (
                          <input
                            id={id}
                            type="radio"
                            name={group.id}
                            className="size-4 accent-[var(--primary)]"
                            checked={checked}
                            onChange={() => toggle(group.id, option.id, true)}
                          />
                        ) : (
                          <Checkbox id={id} checked={checked} onCheckedChange={() => toggle(group.id, option.id, false)} />
                        )}
                        <span className="flex-1">{option.name}</span>
                        {option.price_delta_minor ? (
                          <span className="text-xs text-muted-foreground tabular">
                            {option.price_delta_minor > 0 ? "+" : ""}
                            {formatMoney(option.price_delta_minor)}
                          </span>
                        ) : null}
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            );
          })}
          <div className="grid gap-1.5">
            <Label htmlFor="item-notes">Notes for the kitchen</Label>
            <Input id="item-notes" value={notes} maxLength={300} placeholder="e.g. no peanuts" onChange={(e) => setNotes(e.target.value)} />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Quantity</span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="icon-sm" aria-label="Decrease quantity" onClick={() => setQuantity((q) => Math.max(1, q - 1))}>
                <Minus />
              </Button>
              <span className="w-8 text-center font-semibold tabular" aria-live="polite">
                {quantity}
              </span>
              <Button variant="outline" size="icon-sm" aria-label="Increase quantity" onClick={() => setQuantity((q) => Math.min(999, q + 1))}>
                <Plus />
              </Button>
            </div>
          </div>
          {errors.length ? (
            <p role="alert" className="text-sm text-status-critical">
              {errors[0]}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={errors.length > 0}
            onClick={() =>
              onAdd({
                productId: product.id,
                name: product.name,
                basePriceMinor: product.price_minor,
                quantity,
                notes,
                modifiers: chosen.map(({ group, option }) => ({
                  optionId: option.id,
                  groupName: group.name,
                  name: option.name,
                  priceDeltaMinor: option.price_delta_minor,
                })),
              })
            }
          >
            Add · {formatMoney(unit * quantity)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

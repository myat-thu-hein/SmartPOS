"use client";

import { Loader2, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";

import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { bahtToMinorString, formatMoney, formatUnitCost } from "@/lib/format";
import type { Ingredient, PurchaseOrder, Supplier, SupplierIngredient } from "@/types/api";

import { estimateLineMinor, unitFactor } from "./units";

interface Line {
  key: string;
  ingredient_id: string;
  quantity: string;
  unit: string;
  /** Baht per `unit`; blank means "use the supplier price list". */
  price: string;
}

let lineCounter = 0;
const newLine = (partial: Partial<Line> = {}): Line => ({
  key: `line-${++lineCounter}`,
  ingredient_id: "",
  quantity: "",
  unit: "",
  price: "",
  ...partial,
});

const toBaht = (minor: number) => String(Math.round(minor * 100) / 10_000);

/** Create a draft purchase order, or edit the lines of an existing draft. */
export function PurchaseOrderEditor({
  initial,
  presetSupplierId,
  onSaved,
  onCancel,
}: {
  initial?: PurchaseOrder;
  presetSupplierId?: string;
  onSaved: (po: PurchaseOrder) => void;
  onCancel: () => void;
}) {
  const suppliers = useApi<Supplier[]>(["suppliers"], "/suppliers");
  const ingredients = useApi<Ingredient[]>(["ingredients"], "/ingredients");
  const [supplierId, setSupplierId] = useState(initial?.supplier_id ?? presetSupplierId ?? "");
  const links = useApi<SupplierIngredient[]>(["suppliers", supplierId, "ingredients"], supplierId ? `/suppliers/${supplierId}/ingredients` : null);
  const [expected, setExpected] = useState(initial?.expected_delivery_date ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [lines, setLines] = useState<Line[]>(() =>
    initial
      ? initial.items.map((i) =>
          newLine({
            ingredient_id: i.ingredient_id,
            quantity: String(i.input_quantity),
            unit: i.input_unit,
            // Stored per base unit; show it per the unit the line was entered in.
            price: toBaht(i.unit_cost_minor * (i.quantity_ordered / (i.input_quantity || 1))),
          }),
        )
      : [newLine()],
  );

  const ingredientById = new Map((ingredients.data ?? []).map((i) => [i.id, i]));
  const linkByIngredient = new Map((links.data ?? []).map((l) => [l.ingredient_id, l]));
  const update = (key: string, patch: Partial<Line>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  /** Price per entered unit in minor units: typed price, else supplier list price. */
  const priceMinor = (line: Line): number | null => {
    if (line.price.trim()) {
      const typed = bahtToMinorString(line.price);
      return typed === null ? null : Number(typed);
    }
    const ingredient = ingredientById.get(line.ingredient_id);
    const link = linkByIngredient.get(line.ingredient_id);
    if (!ingredient || link?.unit_cost_minor == null) return null;
    const factor = unitFactor(ingredient, line.unit || ingredient.base_unit);
    return factor === null ? null : link.unit_cost_minor * factor;
  };

  const filled = lines.filter((l) => l.ingredient_id);
  const invalid = filled.some((l) => !(Number(l.quantity) > 0) || (l.price.trim() !== "" && bahtToMinorString(l.price) === null));
  const duplicate = new Set(filled.map((l) => l.ingredient_id)).size !== filled.length;
  const estimate = filled.reduce((sum, l) => sum + estimateLineMinor(Number(l.quantity), priceMinor(l) ?? 0), 0);

  const save = useApiMutation(
    () => {
      const items = filled.map((l) => ({
        ingredient_id: l.ingredient_id,
        quantity: l.quantity,
        unit: l.unit || undefined,
        unit_cost_minor: l.price.trim() ? bahtToMinorString(l.price) : null,
      }));
      const body = { expected_delivery_date: expected || null, notes: notes.trim() || null, items };
      return initial
        ? api<PurchaseOrder>(`/purchase-orders/${initial.id}`, { method: "PATCH", body })
        : api<PurchaseOrder>("/purchase-orders", { method: "POST", body: { ...body, supplier_id: supplierId } });
    },
    {
      invalidate: ["purchase-orders", "suppliers"],
      success: (po) => `Saved draft ${po.display_number}`,
      onSuccess: onSaved,
    },
  );

  // Ingredients the supplier lists come first so the common case is quick.
  const sortedIngredients = [...(ingredients.data ?? [])].sort(
    (a, b) => Number(linkByIngredient.has(b.id)) - Number(linkByIngredient.has(a.id)) || a.name.localeCompare(b.name),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>{initial ? `Edit draft ${initial.display_number}` : "New purchase order"}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField label="Supplier" htmlFor="po-supplier">
            <NativeSelect
              id="po-supplier"
              value={supplierId}
              disabled={!!initial}
              onChange={(e) => setSupplierId(e.target.value)}
            >
              <option value="">Choose…</option>
              {(suppliers.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          <FormField label="Expected delivery" htmlFor="po-expected">
            <Input id="po-expected" type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />
          </FormField>
          <FormField label="Notes" htmlFor="po-notes">
            <Textarea id="po-notes" rows={1} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </FormField>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-48">Ingredient</TableHead>
              <TableHead className="w-28">Quantity</TableHead>
              <TableHead className="w-28">Unit</TableHead>
              <TableHead className="w-36">Price / unit (฿)</TableHead>
              <TableHead className="text-right">Est. line total</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {lines.map((line) => {
              const ingredient = ingredientById.get(line.ingredient_id);
              const link = linkByIngredient.get(line.ingredient_id);
              const price = priceMinor(line);
              return (
                <TableRow key={line.key}>
                  <TableCell>
                    <NativeSelect
                      aria-label="Ingredient"
                      value={line.ingredient_id}
                      onChange={(e) => {
                        const next = ingredientById.get(e.target.value);
                        update(line.key, { ingredient_id: e.target.value, unit: next?.base_unit ?? "", price: "" });
                      }}
                    >
                      <option value="">Choose…</option>
                      {sortedIngredients.map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.name}
                          {linkByIngredient.has(i.id) ? "" : " (not on price list)"}
                        </option>
                      ))}
                    </NativeSelect>
                  </TableCell>
                  <TableCell>
                    <Input aria-label="Quantity" inputMode="decimal" value={line.quantity} onChange={(e) => update(line.key, { quantity: e.target.value })} />
                  </TableCell>
                  <TableCell>
                    <NativeSelect aria-label="Unit" disabled={!ingredient} value={line.unit} onChange={(e) => update(line.key, { unit: e.target.value })}>
                      {(ingredient?.allowed_units ?? [line.unit]).map((u) => (
                        <option key={u} value={u}>
                          {u}
                        </option>
                      ))}
                    </NativeSelect>
                  </TableCell>
                  <TableCell>
                    <Input
                      aria-label="Price per unit"
                      inputMode="decimal"
                      placeholder={link?.unit_cost_minor != null && price !== null ? `List: ${toBaht(price)}` : "Price"}
                      value={line.price}
                      onChange={(e) => update(line.key, { price: e.target.value })}
                    />
                    {link?.unit_cost_minor != null ? (
                      <p className="mt-1 text-xs text-muted-foreground">List {formatUnitCost(link.unit_cost_minor, link.base_unit)}</p>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-right tabular">
                    {price !== null && Number(line.quantity) > 0 ? formatMoney(estimateLineMinor(Number(line.quantity), price)) : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Remove line"
                      disabled={lines.length === 1}
                      onClick={() => setLines((ls) => ls.filter((l) => l.key !== line.key))}
                    >
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button variant="outline" size="sm" onClick={() => setLines((ls) => [...ls, newLine()])}>
            <Plus /> Add line
          </Button>
          <p className="text-sm">
            Estimated total <span className="font-semibold tabular">{formatMoney(estimate)}</span>
          </p>
        </div>
        {invalid ? <p className="text-sm text-status-critical">Every line needs a positive quantity and a valid price.</p> : null}
        {duplicate ? <p className="text-sm text-status-critical">Each ingredient may appear only once.</p> : null}
      </CardContent>
      <CardFooter className="justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button disabled={!supplierId || !filled.length || invalid || duplicate || save.isPending} onClick={() => save.mutate(undefined)}>
          {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save draft
        </Button>
      </CardFooter>
    </Card>
  );
}

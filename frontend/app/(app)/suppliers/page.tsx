"use client";

import { Link2, Pencil, Plus, Trash2, Truck } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { QueryState } from "@/components/shared/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { bahtToMinorString, formatQty, formatUnitCost } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Ingredient, Supplier, SupplierIngredient } from "@/types/api";

export default function SuppliersPage() {
  const { t } = useI18n();
  const { can } = useAuth();
  const [showInactive, setShowInactive] = useState(false);
  const [editing, setEditing] = useState<Supplier | "new" | null>(null);
  const [pricing, setPricing] = useState<Supplier | null>(null);
  const query = useApi<Supplier[]>(["suppliers"], "/suppliers", { include_inactive: showInactive });
  const writable = can("suppliers:write");
  return (
    <>
      <PageHeader
        title={t("Suppliers")}
        description="Supplier contacts, lead times and ingredient price lists used by purchase orders and reorder suggestions."
        actions={
          writable ? (
            <Button onClick={() => setEditing("new")}>
              <Plus /> New supplier
            </Button>
          ) : null
        }
      />
      <Card>
        <CardContent className="grid gap-4">
          <Label className="font-normal">
            <Switch checked={showInactive} onCheckedChange={setShowInactive} /> Show inactive
          </Label>
          <QueryState query={query}>
            {(list) =>
              list.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Supplier</TableHead>
                      <TableHead>Contact</TableHead>
                      <TableHead className="text-right">Lead time</TableHead>
                      <TableHead className="text-right">Ingredients</TableHead>
                      <TableHead className="text-right">Open POs</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {list.map((s) => (
                      <TableRow key={s.id} className={s.is_active ? undefined : "opacity-60"}>
                        <TableCell>
                          <p className="font-medium">{s.name}</p>
                          {s.notes ? <p className="max-w-72 truncate text-xs text-muted-foreground">{s.notes}</p> : null}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {[s.contact_name, s.phone, s.email].filter(Boolean).join(" · ") || "—"}
                        </TableCell>
                        <TableCell className="text-right tabular">{s.lead_time_days === 1 ? "1 day" : `${s.lead_time_days} days`}</TableCell>
                        <TableCell className="text-right tabular">{s.ingredient_count}</TableCell>
                        <TableCell className="text-right tabular">{s.open_purchase_orders}</TableCell>
                        <TableCell className="text-right whitespace-nowrap">
                          <Button variant="ghost" size="sm" onClick={() => setPricing(s)}>
                            <Link2 /> Price list
                          </Button>
                          {writable ? (
                            <Button variant="ghost" size="icon-sm" aria-label={`Edit ${s.name}`} onClick={() => setEditing(s)}>
                              <Pencil />
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState icon={Truck} title="No suppliers yet" description="Add the vendors you buy ingredients from." />
              )
            }
          </QueryState>
        </CardContent>
      </Card>
      {editing ? <SupplierDialog supplier={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
      {pricing ? <PriceListDialog supplier={pricing} onClose={() => setPricing(null)} /> : null}
    </>
  );
}

function SupplierDialog({ supplier, onClose }: { supplier: Supplier | null; onClose: () => void }) {
  const [form, setForm] = useState({
    name: supplier?.name ?? "",
    contact_name: supplier?.contact_name ?? "",
    phone: supplier?.phone ?? "",
    email: supplier?.email ?? "",
    address: supplier?.address ?? "",
    notes: supplier?.notes ?? "",
    lead_time_days: String(supplier?.lead_time_days ?? 2),
    is_active: supplier?.is_active ?? true,
  });
  const set = (k: keyof typeof form, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));
  const save = useApiMutation(
    () => {
      const body = {
        name: form.name.trim(),
        contact_name: form.contact_name.trim() || null,
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        address: form.address.trim() || null,
        notes: form.notes.trim() || null,
        lead_time_days: Number(form.lead_time_days) || 0,
      };
      return supplier
        ? api(`/suppliers/${supplier.id}`, { method: "PATCH", body: { ...body, is_active: form.is_active } })
        : api("/suppliers", { method: "POST", body });
    },
    { invalidate: ["suppliers"], success: "Supplier saved", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{supplier ? `Edit ${supplier.name}` : "New supplier"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Name" htmlFor="s-name" className="sm:col-span-2">
            <Input id="s-name" value={form.name} onChange={(e) => set("name", e.target.value)} autoFocus />
          </FormField>
          <FormField label="Contact person" htmlFor="s-contact">
            <Input id="s-contact" value={form.contact_name} onChange={(e) => set("contact_name", e.target.value)} />
          </FormField>
          <FormField label="Phone" htmlFor="s-phone">
            <Input id="s-phone" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
          </FormField>
          <FormField label="Email" htmlFor="s-email">
            <Input id="s-email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
          </FormField>
          <FormField label="Lead time (days)" htmlFor="s-lead" hint="Order-to-delivery time used in reorder suggestions.">
            <Input id="s-lead" type="number" min={0} max={365} value={form.lead_time_days} onChange={(e) => set("lead_time_days", e.target.value)} />
          </FormField>
          <FormField label="Address" htmlFor="s-address" className="sm:col-span-2">
            <Textarea id="s-address" rows={2} value={form.address} onChange={(e) => set("address", e.target.value)} />
          </FormField>
          <FormField label="Notes" htmlFor="s-notes" className="sm:col-span-2">
            <Textarea id="s-notes" rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
          </FormField>
          {supplier ? (
            <Label className="font-normal">
              <Switch checked={form.is_active} onCheckedChange={(v) => set("is_active", v)} /> Active
            </Label>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!form.name.trim() || save.isPending} onClick={() => save.mutate(undefined)}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PriceListDialog({ supplier, onClose }: { supplier: Supplier; onClose: () => void }) {
  const { can } = useAuth();
  const links = useApi<SupplierIngredient[]>(["suppliers", supplier.id, "ingredients"], `/suppliers/${supplier.id}/ingredients`);
  const ingredients = useApi<Ingredient[]>(["ingredients"], "/ingredients");
  const [ingredientId, setIngredientId] = useState("");
  const [sku, setSku] = useState("");
  const [cost, setCost] = useState("");
  const [unit, setUnit] = useState("");
  const [moq, setMoq] = useState("");
  const ingredient = ingredients.data?.find((i) => i.id === ingredientId);
  const add = useApiMutation(
    () =>
      api(`/suppliers/${supplier.id}/ingredients`, {
        method: "POST",
        body: {
          ingredient_id: ingredientId,
          supplier_sku: sku.trim() || null,
          unit_cost_minor: cost ? bahtToMinorString(cost) : null,
          unit: unit || undefined,
          min_order_quantity: moq || null,
        },
      }),
    {
      invalidate: ["suppliers", "ingredients"],
      success: "Ingredient linked",
      onSuccess: () => {
        setIngredientId("");
        setSku("");
        setCost("");
        setMoq("");
      },
    },
  );
  const remove = useApiMutation((linkId: string) => api(`/suppliers/${supplier.id}/ingredients/${linkId}`, { method: "DELETE" }), {
    invalidate: ["suppliers"],
    success: "Link removed",
  });
  const linked = new Set(links.data?.map((l) => l.ingredient_id));
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{supplier.name} · price list</DialogTitle>
          <DialogDescription>Prices are stored per base unit; minimum order quantities round reorder suggestions up.</DialogDescription>
        </DialogHeader>
        <QueryState query={links}>
          {(list) =>
            list.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ingredient</TableHead>
                    <TableHead>Supplier SKU</TableHead>
                    <TableHead className="text-right">Price</TableHead>
                    <TableHead className="text-right">Min. order</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell>{l.ingredient_name}</TableCell>
                      <TableCell className="text-muted-foreground">{l.supplier_sku ?? "—"}</TableCell>
                      <TableCell className="text-right tabular">
                        {formatUnitCost(l.unit_cost_minor, l.base_unit)}
                      </TableCell>
                      <TableCell className="text-right tabular">{l.min_order_quantity ? formatQty(l.min_order_quantity, l.base_unit) : "—"}</TableCell>
                      <TableCell className="text-right">
                        {can("suppliers:write") ? (
                          <Button variant="ghost" size="icon-sm" aria-label={`Unlink ${l.ingredient_name}`} onClick={() => remove.mutate(l.id)}>
                            <Trash2 />
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">No ingredients linked yet.</p>
            )
          }
        </QueryState>
        {can("suppliers:write") ? (
          <div className="grid gap-3 rounded-lg border p-3 sm:grid-cols-6">
            <FormField label="Ingredient" htmlFor="pl-ing" className="sm:col-span-2">
              <NativeSelect
                id="pl-ing"
                value={ingredientId}
                onChange={(e) => {
                  setIngredientId(e.target.value);
                  setUnit(ingredients.data?.find((i) => i.id === e.target.value)?.base_unit ?? "");
                }}
              >
                <option value="">Choose…</option>
                {(ingredients.data ?? [])
                  .filter((i) => !linked.has(i.id))
                  .map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name}
                    </option>
                  ))}
              </NativeSelect>
            </FormField>
            <FormField label="Unit" htmlFor="pl-unit">
              <NativeSelect id="pl-unit" value={unit} disabled={!ingredient} onChange={(e) => setUnit(e.target.value)}>
                {(ingredient?.allowed_units ?? []).map((u) => (
                  <option key={u} value={u}>
                    {u}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
            <FormField label={`Price / ${unit || "unit"} (฿)`} htmlFor="pl-cost">
              <Input id="pl-cost" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
            </FormField>
            <FormField label={`Min. order (${unit || "unit"})`} htmlFor="pl-moq">
              <Input id="pl-moq" inputMode="decimal" value={moq} onChange={(e) => setMoq(e.target.value)} />
            </FormField>
            <FormField label="Supplier SKU" htmlFor="pl-sku">
              <Input id="pl-sku" value={sku} onChange={(e) => setSku(e.target.value)} />
            </FormField>
            <div className="sm:col-span-6">
              <Button size="sm" disabled={!ingredientId || add.isPending} onClick={() => add.mutate(undefined)}>
                <Plus /> Link ingredient
              </Button>
            </div>
          </div>
        ) : null}
        <DialogFooter>
          {!supplier.is_active ? <Badge variant="secondary">Inactive supplier</Badge> : null}
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

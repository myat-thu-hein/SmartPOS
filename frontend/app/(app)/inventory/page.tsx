"use client";

import { AlertTriangle, ArrowDownUp, Boxes, ClipboardCheck, Pencil, Plus, Search } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { QueryState } from "@/components/shared/query-state";
import { StatCard } from "@/components/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { bahtToMinorString, formatDateTime, formatMoney, formatNumber, formatQty, formatUnitCost, humanize } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type {
  BaseUnit,
  Ingredient,
  InventorySummary,
  Movement,
  MovementType,
  Page,
  StockRisk,
  StockRiskLevel,
  Supplier,
} from "@/types/api";

const MOVEMENT_TYPES: MovementType[] = ["OPENING", "RECEIPT", "PURCHASE_RECEIPT", "ISSUE", "ADJUSTMENT", "WASTE", "SALE", "SALE_REVERSAL"];

export default function InventoryPage() {
  const { t } = useI18n();
  const summary = useApi<InventorySummary>(["ingredients", "summary"], "/inventory/summary");
  return (
    <>
      <PageHeader title={t("Inventory")} description="Every stock change is an immutable movement; balances are never edited directly." />
      {summary.data ? (
        <div className="mb-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Active ingredients" value={summary.data.ingredient_count} />
          <StatCard
            label="At or below reorder level"
            value={summary.data.low_stock_count}
            icon={summary.data.low_stock_count ? <AlertTriangle className="size-4 text-status-serious" /> : undefined}
          />
          <StatCard label="Out of stock" value={summary.data.out_of_stock_count} />
          <StatCard
            label="Stock value (moving avg. cost)"
            value={formatMoney(summary.data.total_value_minor)}
            hint={summary.data.unvalued_ingredient_count ? `${summary.data.unvalued_ingredient_count} without cost data` : undefined}
          />
        </div>
      ) : null}
      <Tabs defaultValue="ingredients">
        <TabsList>
          <TabsTrigger value="ingredients">Ingredients</TabsTrigger>
          <TabsTrigger value="movements">Movement history</TabsTrigger>
        </TabsList>
        <TabsContent value="ingredients">
          <IngredientsTab />
        </TabsContent>
        <TabsContent value="movements">
          <MovementsTab />
        </TabsContent>
      </Tabs>
    </>
  );
}

function IngredientsTab() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [editing, setEditing] = useState<Ingredient | "new" | null>(null);
  const [moving, setMoving] = useState<Ingredient | null>(null);
  const [counting, setCounting] = useState<Ingredient | null>(null);
  const query = useApi<Ingredient[]>(["ingredients"], "/ingredients", { low_stock_only: lowOnly, search: search.trim() || undefined });
  const risks = useApi<StockRisk[]>(["inventory", "stock-risk"], "/inventory/stock-risk");
  const riskById = new Map((risks.data ?? []).map((r) => [r.ingredient_id, r]));
  const writable = can("inventory:write");
  return (
    <Card>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" aria-hidden />
            <Input aria-label="Search ingredients" placeholder="Search ingredients" className="pl-8" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Label className="font-normal">
            <Switch checked={lowOnly} onCheckedChange={setLowOnly} /> Low stock only
          </Label>
          {writable ? (
            <Button className="ml-auto" onClick={() => setEditing("new")}>
              <Plus /> New ingredient
            </Button>
          ) : null}
        </div>
        <QueryState query={query}>
          {(list) =>
            list.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ingredient</TableHead>
                    <TableHead className="text-right">In stock</TableHead>
                    <TableHead className="text-right" title="How long stock lasts at the expected daily use">
                      Lasts
                    </TableHead>
                    <TableHead className="text-right">Reorder at</TableHead>
                    <TableHead className="text-right">Safety</TableHead>
                    <TableHead className="text-right">Avg. cost</TableHead>
                    <TableHead className="text-right">Value</TableHead>
                    <TableHead>Supplier</TableHead>
                    {writable ? <TableHead className="text-right">Actions</TableHead> : null}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.map((i) => (
                    <TableRow key={i.id}>
                      <TableCell>
                        <p className="font-medium">{i.name}</p>
                        <p className="text-xs text-muted-foreground">
                          Base unit {i.base_unit}
                          {i.units.length ? ` · packs: ${i.units.map((u) => `${u.unit_name}=${formatNumber(u.factor_to_base)}${i.base_unit}`).join(", ")}` : ""}
                        </p>
                      </TableCell>
                      <TableCell className="text-right tabular">
                        <span className="inline-flex items-center gap-1.5">
                          {i.is_low_stock ? (
                            <Badge variant={i.current_stock <= 0 ? "danger" : "warning"}>
                              <AlertTriangle aria-hidden /> {i.current_stock <= 0 ? "Out" : "Low"}
                            </Badge>
                          ) : null}
                          {formatQty(i.current_stock, i.base_unit)}
                        </span>
                      </TableCell>
                      <TableCell className="text-right tabular">
                        <CoverCell risk={riskById.get(i.id)} />
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground tabular">{formatQty(i.reorder_level, i.base_unit)}</TableCell>
                      <TableCell className="text-right text-muted-foreground tabular">{formatQty(i.safety_stock, i.base_unit)}</TableCell>
                      <TableCell className="text-right text-muted-foreground tabular">
                        {i.average_cost_minor ? formatUnitCost(i.average_cost_minor, i.base_unit) : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular">{formatMoney(i.stock_value_minor)}</TableCell>
                      <TableCell className="text-muted-foreground">{i.default_supplier_name ?? "—"}</TableCell>
                      {writable ? (
                        <TableCell className="text-right whitespace-nowrap">
                          <Button variant="ghost" size="sm" onClick={() => setMoving(i)}>
                            <ArrowDownUp /> Stock
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setCounting(i)}>
                            <ClipboardCheck /> Count
                          </Button>
                          <Button variant="ghost" size="icon-sm" aria-label={`Edit ${i.name}`} onClick={() => setEditing(i)}>
                            <Pencil />
                          </Button>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState icon={Boxes} title={lowOnly ? "Nothing is low on stock" : "No ingredients yet"} description="Add ingredients, then link them to products on the Recipes page." />
            )
          }
        </QueryState>
      </CardContent>
      {editing ? <IngredientDialog ingredient={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
      {moving ? <MovementDialog ingredient={moving} onClose={() => setMoving(null)} /> : null}
      {counting ? <CountDialog ingredient={counting} onClose={() => setCounting(null)} /> : null}
    </Card>
  );
}

const COVER_TONE: Record<StockRiskLevel, string> = {
  out: "text-status-critical font-semibold",
  critical: "text-status-critical font-semibold",
  warning: "text-foreground font-medium",
  ok: "text-muted-foreground",
};

/** Days of cover against the supplier lead time; the reason explains the numbers. */
function CoverCell({ risk }: { risk: StockRisk | undefined }) {
  if (!risk) return <span className="text-muted-foreground">—</span>;
  const label =
    risk.level === "out" ? "Out" : risk.days_of_cover === null ? "—" : `${formatNumber(risk.days_of_cover, 1)} days`;
  return (
    <span className="inline-flex items-center justify-end gap-1.5 whitespace-nowrap" title={risk.reason}>
      {risk.level === "critical" || risk.level === "warning" ? (
        <span
          className={cn("size-2 rounded-full", risk.level === "critical" ? "bg-status-critical" : "bg-status-warning")}
          aria-hidden
        />
      ) : null}
      <span className={COVER_TONE[risk.level]}>{label}</span>
      <span className="sr-only">. {risk.reason}</span>
    </span>
  );
}

function IngredientDialog({ ingredient, onClose }: { ingredient: Ingredient | null; onClose: () => void }) {
  const suppliers = useApi<Supplier[]>(["suppliers"], "/suppliers");
  const [name, setName] = useState(ingredient?.name ?? "");
  const [sku, setSku] = useState(ingredient?.sku ?? "");
  const [unit, setUnit] = useState<BaseUnit>(ingredient?.base_unit ?? "g");
  const [reorder, setReorder] = useState(String(ingredient?.reorder_level ?? 0));
  const [safety, setSafety] = useState(String(ingredient?.safety_stock ?? 0));
  const [supplierId, setSupplierId] = useState(ingredient?.default_supplier_id ?? "");
  const [opening, setOpening] = useState("");
  const [openingCost, setOpeningCost] = useState("");
  const [packName, setPackName] = useState("");
  const [packFactor, setPackFactor] = useState("");
  const save = useApiMutation(
    () => {
      const common = {
        name: name.trim(),
        sku: sku.trim() || null,
        reorder_level: reorder || "0",
        safety_stock: safety || "0",
      };
      if (ingredient) {
        return api(`/ingredients/${ingredient.id}`, {
          method: "PATCH",
          body: { ...common, default_supplier_id: supplierId || null, clear_default_supplier: !supplierId },
        });
      }
      return api("/ingredients", {
        method: "POST",
        body: {
          ...common,
          base_unit: unit,
          default_supplier_id: supplierId || null,
          opening_stock: opening || null,
          opening_unit_cost_minor: openingCost ? bahtToMinorString(openingCost) : null,
          units: packName && packFactor ? [{ unit_name: packName.trim(), factor_to_base: packFactor }] : [],
        },
      });
    },
    { invalidate: ["ingredients", "recipes"], success: ingredient ? "Ingredient updated" : "Ingredient added", onSuccess: onClose },
  );
  const addPack = useApiMutation(
    () => api(`/ingredients/${ingredient!.id}/units`, { method: "POST", body: { unit_name: packName.trim(), factor_to_base: packFactor } }),
    { invalidate: ["ingredients"], success: "Pack unit added", onSuccess: () => { setPackName(""); setPackFactor(""); } },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{ingredient ? `Edit ${ingredient.name}` : "New ingredient"}</DialogTitle>
          <DialogDescription>Quantities are stored in the base unit. Define pack units (e.g. tray = 30 pieces) for receiving.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Name" htmlFor="i-name" className="sm:col-span-2">
            <Input id="i-name" value={name} maxLength={150} onChange={(e) => setName(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Base unit" htmlFor="i-unit" hint={ingredient ? "Cannot be changed after creation." : undefined}>
            <NativeSelect id="i-unit" value={unit} disabled={!!ingredient} onChange={(e) => setUnit(e.target.value as BaseUnit)}>
              <option value="g">grams (g)</option>
              <option value="ml">millilitres (ml)</option>
              <option value="piece">pieces</option>
            </NativeSelect>
          </FormField>
          <FormField label="SKU (optional)" htmlFor="i-sku">
            <Input id="i-sku" value={sku} onChange={(e) => setSku(e.target.value)} />
          </FormField>
          <FormField label={`Reorder level (${unit})`} htmlFor="i-reorder">
            <Input id="i-reorder" inputMode="decimal" value={reorder} onChange={(e) => setReorder(e.target.value)} />
          </FormField>
          <FormField label={`Safety stock (${unit})`} htmlFor="i-safety">
            <Input id="i-safety" inputMode="decimal" value={safety} onChange={(e) => setSafety(e.target.value)} />
          </FormField>
          <FormField label="Default supplier" htmlFor="i-supplier" className="sm:col-span-2">
            <NativeSelect id="i-supplier" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
              <option value="">None</option>
              {(suppliers.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          {!ingredient ? (
            <>
              <FormField label={`Opening stock (${unit})`} htmlFor="i-open" hint="Recorded as an OPENING movement.">
                <Input id="i-open" inputMode="decimal" value={opening} onChange={(e) => setOpening(e.target.value)} />
              </FormField>
              <FormField label={`Cost per ${unit} (฿)`} htmlFor="i-cost" hint="Optional, for stock valuation.">
                <Input id="i-cost" inputMode="decimal" value={openingCost} onChange={(e) => setOpeningCost(e.target.value)} />
              </FormField>
            </>
          ) : null}
          <FormField label="Pack unit name" htmlFor="i-pack" hint="e.g. tray, bottle, sack">
            <Input id="i-pack" value={packName} onChange={(e) => setPackName(e.target.value)} />
          </FormField>
          <FormField label={`${unit} per pack`} htmlFor="i-pack-f">
            <div className="flex gap-2">
              <Input id="i-pack-f" inputMode="decimal" value={packFactor} onChange={(e) => setPackFactor(e.target.value)} />
              {ingredient ? (
                <Button type="button" variant="outline" disabled={!packName || !(Number(packFactor) > 0)} onClick={() => addPack.mutate(undefined)}>
                  Add
                </Button>
              ) : null}
            </div>
          </FormField>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!name.trim() || save.isPending} onClick={() => save.mutate(undefined)}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MovementDialog({ ingredient, onClose }: { ingredient: Ingredient; onClose: () => void }) {
  const [type, setType] = useState<"RECEIPT" | "ISSUE" | "WASTE" | "ADJUSTMENT">("RECEIPT");
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState<string>(ingredient.base_unit);
  const [cost, setCost] = useState("");
  const [reason, setReason] = useState("");
  const record = useApiMutation(
    () =>
      api<Movement>("/inventory/movements", {
        method: "POST",
        body: {
          ingredient_id: ingredient.id,
          movement_type: type,
          quantity,
          unit,
          unit_cost_minor: type === "RECEIPT" && cost ? bahtToMinorString(cost) : null,
          reason,
        },
      }),
    {
      invalidate: ["ingredients", "movements", "dashboard"],
      success: (m) => `Recorded. New balance ${formatQty(m.balance_after, ingredient.base_unit)}`,
      onSuccess: onClose,
    },
  );
  const qty = Number(quantity);
  const valid = quantity !== "" && qty !== 0 && (type === "ADJUSTMENT" || qty > 0) && reason.trim().length >= 3;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Stock movement · {ingredient.name}</DialogTitle>
          <DialogDescription>Current balance {formatQty(ingredient.current_stock, ingredient.base_unit)}. Sales and purchase-order deliveries are recorded automatically.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <FormField label="Type" htmlFor="m-type">
            <NativeSelect id="m-type" value={type} onChange={(e) => setType(e.target.value as typeof type)}>
              <option value="RECEIPT">Receipt (stock in)</option>
              <option value="ISSUE">Issue (used outside sales)</option>
              <option value="WASTE">Waste / spoilage</option>
              <option value="ADJUSTMENT">Adjustment (signed, + or −)</option>
            </NativeSelect>
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Quantity" htmlFor="m-qty" hint={type === "ADJUSTMENT" ? "Use − to reduce" : undefined}>
              <Input id="m-qty" inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </FormField>
            <FormField label="Unit" htmlFor="m-unit">
              <NativeSelect id="m-unit" value={unit} onChange={(e) => setUnit(e.target.value)}>
                {ingredient.allowed_units.map((u) => (
                  <option key={u} value={u}>
                    {u}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
          </div>
          {type === "RECEIPT" ? (
            <FormField label={`Cost per ${unit} (฿, optional)`} htmlFor="m-cost" hint="Updates the moving-average cost.">
              <Input id="m-cost" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
            </FormField>
          ) : null}
          <FormField label="Reason" htmlFor="m-reason">
            <Input id="m-reason" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!valid || record.isPending} onClick={() => record.mutate(undefined)}>
            Record movement
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CountDialog({ ingredient, onClose }: { ingredient: Ingredient; onClose: () => void }) {
  const [counted, setCounted] = useState("");
  const [unit, setUnit] = useState<string>(ingredient.base_unit);
  const count = useApiMutation(
    () =>
      api<Movement | null>("/inventory/stock-count", {
        method: "POST",
        body: { ingredient_id: ingredient.id, counted_quantity: counted, unit, reason: "Physical stock count" },
      }),
    {
      invalidate: ["ingredients", "movements"],
      success: (m) => (m ? `Adjusted by ${formatQty(m.quantity, ingredient.base_unit)}` : "Count matches the recorded balance"),
      onSuccess: onClose,
    },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Stock count · {ingredient.name}</DialogTitle>
          <DialogDescription>
            System balance {formatQty(ingredient.current_stock, ingredient.base_unit)}. Any difference is recorded as an adjustment.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Counted quantity" htmlFor="cnt-qty">
            <Input id="cnt-qty" inputMode="decimal" value={counted} onChange={(e) => setCounted(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Unit" htmlFor="cnt-unit">
            <NativeSelect id="cnt-unit" value={unit} onChange={(e) => setUnit(e.target.value)}>
              {ingredient.allowed_units.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </NativeSelect>
          </FormField>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={counted === "" || Number(counted) < 0 || count.isPending} onClick={() => count.mutate(undefined)}>
            Save count
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MovementsTab() {
  const ingredients = useApi<Ingredient[]>(["ingredients", "options"], "/ingredients", { include_inactive: true });
  const [ingredientId, setIngredientId] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const query = useApi<Page<Movement>>(["movements"], "/inventory/movements", {
    ingredient_id: ingredientId || undefined,
    movement_type: type || undefined,
    page,
    page_size: 50,
  });
  return (
    <Card>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap gap-2">
          <NativeSelect aria-label="Ingredient" className="w-56" value={ingredientId} onChange={(e) => { setIngredientId(e.target.value); setPage(1); }}>
            <option value="">All ingredients</option>
            {(ingredients.data ?? []).map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect aria-label="Movement type" className="w-48" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }}>
            <option value="">All types</option>
            {MOVEMENT_TYPES.map((m) => (
              <option key={m} value={m}>
                {humanize(m)}
              </option>
            ))}
          </NativeSelect>
        </div>
        <QueryState query={query}>
          {(data) =>
            data.items.length ? (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Ingredient</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead className="text-right">Change</TableHead>
                      <TableHead className="text-right">Balance</TableHead>
                      <TableHead>Reason</TableHead>
                      <TableHead>By</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((m) => (
                      <TableRow key={m.id}>
                        <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(m.created_at)}</TableCell>
                        <TableCell>{m.ingredient_name}</TableCell>
                        <TableCell>
                          <Badge variant={m.quantity > 0 ? "success" : m.movement_type === "WASTE" ? "danger" : "outline"}>{humanize(m.movement_type)}</Badge>
                        </TableCell>
                        <TableCell className="text-right font-medium tabular">
                          {m.quantity > 0 ? "+" : ""}
                          {formatQty(m.quantity, m.base_unit)}
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground tabular">{formatQty(m.balance_after, m.base_unit)}</TableCell>
                        <TableCell className="max-w-64 truncate text-muted-foreground" title={m.reason ?? ""}>
                          {m.reason}
                        </TableCell>
                        <TableCell className="text-muted-foreground">{m.actor_name ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
              </>
            ) : (
              <EmptyState title="No movements" description="Stock movements appear here as you receive, sell and adjust stock." />
            )
          }
        </QueryState>
      </CardContent>
    </Card>
  );
}

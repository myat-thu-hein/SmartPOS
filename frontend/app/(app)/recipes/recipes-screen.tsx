"use client";

import { CookingPot, History, Loader2, Plus, Save, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingRows, QueryState } from "@/components/shared/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatMoney, formatNumber, formatQty } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Ingredient, Recipe, RecipeSummary } from "@/types/api";

interface Row {
  key: string;
  ingredient_id: string;
  quantity: string;
  unit: string;
  waste_pct: string;
}

let rowCounter = 0;
const newRow = (partial: Partial<Row> = {}): Row => ({
  key: `row-${++rowCounter}`,
  ingredient_id: "",
  quantity: "",
  unit: "",
  waste_pct: "0",
  ...partial,
});

export function RecipesScreen() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const summaries = useApi<RecipeSummary[]>(["recipes"], "/recipes");
  const selectedId = params.get("product") ?? summaries.data?.[0]?.product_id ?? null;

  return (
    <>
      <PageHeader
        title={t("Recipes")}
        description="Link products to ingredients. Confirmed orders deduct these quantities from stock. Saving a change creates a new version; past orders keep the version they used."
      />
      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="py-3">
          <CardContent className="px-2">
            <QueryState query={summaries} loading={<LoadingRows rows={8} />}>
              {(list) =>
                list.length ? (
                  <ul className="grid gap-0.5" aria-label="Products">
                    {list.map((s) => (
                      <li key={s.product_id}>
                        <button
                          type="button"
                          onClick={() => router.replace(`/recipes?product=${s.product_id}`)}
                          aria-current={s.product_id === selectedId ? "true" : undefined}
                          className={cn(
                            "flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-accent",
                            s.product_id === selectedId && "bg-accent font-medium",
                          )}
                        >
                          <span className="min-w-0">
                            <span className="block truncate">{s.product_name}</span>
                            <span className="text-xs text-muted-foreground">{s.category_name}</span>
                          </span>
                          {s.recipe_id ? (
                            <Badge variant="success">v{s.version}</Badge>
                          ) : (
                            <Badge variant="outline">No recipe</Badge>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState title="No products" description="Create products on the Menu page first." />
                )
              }
            </QueryState>
          </CardContent>
        </Card>
        {selectedId ? <RecipeEditor key={selectedId} productId={selectedId} /> : null}
      </div>
    </>
  );
}

function RecipeEditor({ productId }: { productId: string }) {
  const { can } = useAuth();
  const ingredients = useApi<Ingredient[]>(["ingredients"], "/ingredients");
  // The API answers null when the product has no recipe yet.
  const recipe = useApi<Recipe | null>(["recipe", productId], `/recipes/products/${productId}`);
  const versions = useApi<Recipe[]>(["recipe", productId, "versions"], `/recipes/products/${productId}/versions`);
  const missing = recipe.data === null;
  const [rows, setRows] = useState<Row[] | null>(null);
  const [notes, setNotes] = useState<string | null>(null);

  // Initialise the editable rows from the loaded recipe once.
  const current: Row[] =
    rows ??
    (recipe.data
      ? recipe.data.items.map((i) =>
          newRow({
            ingredient_id: i.ingredient_id,
            quantity: String(i.input_quantity),
            unit: i.input_unit,
            waste_pct: String(Math.round(i.waste_factor * 10000) / 100),
          }),
        )
      : missing
        ? [newRow()]
        : []);

  const save = useApiMutation(
    () =>
      api<Recipe>(`/recipes/products/${productId}`, {
        method: "PUT",
        body: {
          notes: (notes ?? recipe.data?.notes ?? "") || null,
          items: current
            .filter((r) => r.ingredient_id)
            .map((r) => ({
              ingredient_id: r.ingredient_id,
              quantity: r.quantity,
              unit: r.unit || undefined,
              waste_factor: String(Number(r.waste_pct || 0) / 100),
            })),
        },
      }),
    {
      invalidate: ["recipe", "recipes", "products"],
      success: (r) => `Saved recipe version ${r.version}`,
      onSuccess: () => setRows(null),
    },
  );

  if (recipe.isPending) return <LoadingRows rows={6} />;
  if (recipe.isError) return <QueryState query={recipe}>{() => null}</QueryState>;

  const ingredientById = new Map((ingredients.data ?? []).map((i) => [i.id, i]));
  const update = (key: string, patch: Partial<Row>) =>
    setRows(current.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const used = new Set(current.map((r) => r.ingredient_id));
  const invalid = current.some(
    (r) => r.ingredient_id && (!(Number(r.quantity) > 0) || Number(r.waste_pct) < 0 || Number(r.waste_pct) >= 100),
  );
  const editable = can("recipes:write");

  return (
    <div className="grid content-start gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CookingPot className="size-4" aria-hidden />
            {recipe.data?.product_name ?? "New recipe"}
          </CardTitle>
          <CardDescription>
            {recipe.data
              ? `Version ${recipe.data.version} · saved ${formatDateTime(recipe.data.created_at)}`
              : "This product has no recipe yet, so selling it does not deduct any stock."}
          </CardDescription>
          {recipe.data ? (
            <CardAction className="text-right text-sm">
              <p className="font-semibold">{formatMoney(recipe.data.estimated_cost_minor)} / serving</p>
              <p className="text-xs text-muted-foreground">
                {recipe.data.estimated_margin_bps !== null
                  ? `Est. gross margin ${formatNumber(recipe.data.estimated_margin_bps / 100, 1)}% on ${formatMoney(recipe.data.selling_price_minor)}`
                  : "Margin unknown: some ingredients have no cost"}
              </p>
            </CardAction>
          ) : null}
        </CardHeader>
        <CardContent className="grid gap-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-48">Ingredient</TableHead>
                <TableHead className="w-28">Quantity</TableHead>
                <TableHead className="w-28">Unit</TableHead>
                <TableHead className="w-24">Waste %</TableHead>
                <TableHead className="text-right">Per serving</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {current.map((row) => {
                const ingredient = ingredientById.get(row.ingredient_id);
                const saved = recipe.data?.items.find((i) => i.ingredient_id === row.ingredient_id);
                return (
                  <TableRow key={row.key}>
                    <TableCell>
                      <NativeSelect
                        aria-label="Ingredient"
                        disabled={!editable}
                        value={row.ingredient_id}
                        onChange={(e) => {
                          const next = ingredientById.get(e.target.value);
                          update(row.key, { ingredient_id: e.target.value, unit: next?.base_unit ?? "" });
                        }}
                      >
                        <option value="">Choose…</option>
                        {(ingredients.data ?? []).map((i) => (
                          <option key={i.id} value={i.id} disabled={used.has(i.id) && i.id !== row.ingredient_id}>
                            {i.name}
                          </option>
                        ))}
                      </NativeSelect>
                    </TableCell>
                    <TableCell>
                      <Input aria-label="Quantity" inputMode="decimal" disabled={!editable} value={row.quantity} onChange={(e) => update(row.key, { quantity: e.target.value })} />
                    </TableCell>
                    <TableCell>
                      <NativeSelect aria-label="Unit" disabled={!editable || !ingredient} value={row.unit} onChange={(e) => update(row.key, { unit: e.target.value })}>
                        {(ingredient?.allowed_units ?? [row.unit]).map((u) => (
                          <option key={u} value={u}>
                            {u}
                          </option>
                        ))}
                      </NativeSelect>
                    </TableCell>
                    <TableCell>
                      <Input aria-label="Waste percent" inputMode="decimal" disabled={!editable} value={row.waste_pct} onChange={(e) => update(row.key, { waste_pct: e.target.value })} />
                    </TableCell>
                    <TableCell className="text-right text-xs whitespace-nowrap text-muted-foreground tabular">
                      {saved && !rows ? (
                        <>
                          {formatQty(saved.effective_quantity, saved.base_unit)}
                          <br />
                          {formatMoney(saved.estimated_cost_minor)}
                        </>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {editable ? (
                        <Button variant="ghost" size="icon-sm" aria-label="Remove ingredient" onClick={() => setRows(current.filter((r) => r.key !== row.key))}>
                          <Trash2 />
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {editable ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Button variant="outline" size="sm" onClick={() => setRows([...current, newRow()])}>
                <Plus /> Add ingredient
              </Button>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  aria-label="Recipe notes"
                  placeholder="Version note (optional)"
                  className="w-full sm:w-56"
                  value={notes ?? recipe.data?.notes ?? ""}
                  onChange={(e) => setNotes(e.target.value)}
                />
                <Button
                  onClick={() => save.mutate(undefined)}
                  disabled={save.isPending || invalid || !current.some((r) => r.ingredient_id)}
                >
                  {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save recipe
                </Button>
              </div>
            </div>
          ) : null}
          {invalid ? <p className="text-sm text-status-critical">Quantities must be positive and waste below 100%.</p> : null}
          {!ingredients.isPending && !ingredients.data?.length ? (
            <p className="text-sm text-muted-foreground">Add ingredients on the Inventory page to build recipes.</p>
          ) : null}
        </CardContent>
      </Card>
      {versions.data && versions.data.length > 1 ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <History className="size-4" aria-hidden /> Version history
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-2 text-sm">
              {versions.data.map((v) => (
                <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2">
                  <span>
                    <span className="font-medium">v{v.version}</span>
                    {v.is_active ? <Badge variant="success" className="ml-2">active</Badge> : null}
                    <span className="ml-2 text-muted-foreground">{v.items.map((i) => `${i.ingredient_name} ${formatQty(i.input_quantity)} ${i.input_unit}`).join(", ")}</span>
                  </span>
                  <span className="text-xs text-muted-foreground">{formatDateTime(v.created_at)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

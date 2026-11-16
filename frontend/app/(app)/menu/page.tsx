"use client";

import { Archive, CookingPot, FolderPlus, Pencil, Plus, Search, Trash2, UtensilsCrossed } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { QueryState } from "@/components/shared/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ProductDialog } from "@/features/menu/product-form";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { formatMoney, parseMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Category, Ingredient, ModifierGroup, ModifierOption, Product } from "@/types/api";

export default function MenuPage() {
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t("Menu")} description="Products, categories and modifier groups shown at the POS." />
      <Tabs defaultValue="products">
        <TabsList>
          <TabsTrigger value="products">Products</TabsTrigger>
          <TabsTrigger value="categories">Categories</TabsTrigger>
          <TabsTrigger value="modifiers">Modifiers</TabsTrigger>
        </TabsList>
        <TabsContent value="products">
          <ProductsTab />
        </TabsContent>
        <TabsContent value="categories">
          <CategoriesTab />
        </TabsContent>
        <TabsContent value="modifiers">
          <ModifiersTab />
        </TabsContent>
      </Tabs>
    </>
  );
}

// ---------------------------------------------------------------- products

function ProductsTab() {
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const [removing, setRemoving] = useState<Product | null>(null);
  const products = useApi<Product[]>(["products", "menu"], "/products", { include_inactive: showArchived });
  const categories = useApi<Category[]>(["categories"], "/categories", { include_inactive: true });
  const groups = useApi<ModifierGroup[]>(["modifiers"], "/modifiers/groups");
  const toggle = useApiMutation(
    ({ id, ...body }: { id: string; is_available?: boolean; is_active?: boolean }) =>
      api<Product>(`/products/${id}`, { method: "PATCH", body }),
    { invalidate: ["products"], success: (p) => `${p.name} is now ${p.is_available ? "available" : "unavailable"}` },
  );
  const remove = useApiMutation((p: Product) => api<{ message: string }>(`/products/${p.id}`, { method: "DELETE" }), {
    invalidate: ["products", "categories"],
    success: (r) => r.message,
  });

  const term = search.trim().toLowerCase();
  return (
    <Card>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" aria-hidden />
            <Input aria-label="Search products" placeholder="Search name or SKU" className="pl-8" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <NativeSelect aria-label="Category" className="w-48" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">All categories</option>
            {(categories.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </NativeSelect>
          <Label className="font-normal">
            <Switch checked={showArchived} onCheckedChange={setShowArchived} /> Show archived
          </Label>
          <Button className="ml-auto" onClick={() => setEditing("new")} disabled={!categories.data?.length}>
            <Plus /> New product
          </Button>
        </div>
        {!categories.isPending && !categories.data?.length ? (
          <EmptyState icon={FolderPlus} title="Create a category first" description="Products belong to a category (e.g. Noodles, Drinks)." />
        ) : (
          <QueryState query={products}>
            {(list) => {
              const rows = list.filter(
                (p) =>
                  (!categoryId || p.category_id === categoryId) &&
                  (!term || p.name.toLowerCase().includes(term) || (p.sku ?? "").toLowerCase().includes(term)),
              );
              return rows.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Product</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead className="text-right">Price</TableHead>
                      <TableHead>Recipe</TableHead>
                      <TableHead>Available</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((p) => (
                      <TableRow key={p.id} className={p.is_active ? undefined : "opacity-60"}>
                        <TableCell>
                          <p className="font-medium">{p.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {p.sku ?? "No SKU"}
                            {p.modifier_groups.length ? ` · ${p.modifier_groups.map((g) => g.name).join(", ")}` : ""}
                          </p>
                        </TableCell>
                        <TableCell className="text-muted-foreground">{p.category_name}</TableCell>
                        <TableCell className="text-right tabular">{formatMoney(p.price_minor)}</TableCell>
                        <TableCell>
                          {p.has_recipe ? (
                            <Badge variant="success">
                              <CookingPot aria-hidden /> Linked
                            </Badge>
                          ) : (
                            <Button asChild variant="link" size="sm" className="h-auto p-0">
                              <Link href={`/recipes?product=${p.id}`}>Add recipe</Link>
                            </Button>
                          )}
                        </TableCell>
                        <TableCell>
                          {p.is_active ? (
                            <Switch
                              aria-label={`${p.name} available`}
                              checked={p.is_available}
                              onCheckedChange={(v) => toggle.mutate({ id: p.id, is_available: v })}
                            />
                          ) : (
                            <Badge variant="secondary">
                              <Archive aria-hidden /> Archived
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" size="icon-sm" aria-label={`Edit ${p.name}`} onClick={() => setEditing(p)}>
                            <Pencil />
                          </Button>
                          {p.is_active ? (
                            <Button variant="ghost" size="icon-sm" aria-label={`Remove ${p.name}`} onClick={() => setRemoving(p)}>
                              <Trash2 />
                            </Button>
                          ) : (
                            <Button variant="ghost" size="sm" onClick={() => toggle.mutate({ id: p.id, is_active: true, is_available: true })}>
                              Restore
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState icon={UtensilsCrossed} title="No products found" description="Add your first menu item or change the filters." />
              );
            }}
          </QueryState>
        )}
      </CardContent>
      {editing && categories.data ? (
        <ProductDialog
          product={editing === "new" ? null : editing}
          categories={categories.data}
          groups={groups.data ?? []}
          onClose={() => setEditing(null)}
        />
      ) : null}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Remove ${removing?.name}?`}
        description="Products that were ever sold are archived (hidden from the POS) so historical orders and reports stay correct. Never-sold products are deleted."
        confirmLabel="Remove"
        destructive
        onConfirm={() => remove.mutateAsync(removing!)}
      />
    </Card>
  );
}

// ---------------------------------------------------------------- categories

function CategoriesTab() {
  const categories = useApi<Category[]>(["categories"], "/categories", { include_inactive: true });
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const [removing, setRemoving] = useState<Category | null>(null);
  const remove = useApiMutation((c: Category) => api(`/categories/${c.id}`, { method: "DELETE" }), {
    invalidate: ["categories"],
    success: "Category deleted",
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Categories</CardTitle>
        <CardDescription>Shown as tabs at the POS in display order.</CardDescription>
        <CardAction>
          <Button onClick={() => setEditing("new")}>
            <Plus /> New category
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <QueryState query={categories}>
          {(list) =>
            list.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead className="text-right">Order</TableHead>
                    <TableHead className="text-right">Products</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell>
                        <p className="font-medium">{c.name}</p>
                        {c.description ? <p className="text-xs text-muted-foreground">{c.description}</p> : null}
                      </TableCell>
                      <TableCell className="text-right tabular">{c.display_order}</TableCell>
                      <TableCell className="text-right tabular">{c.product_count}</TableCell>
                      <TableCell>{c.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="secondary">Hidden</Badge>}</TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="icon-sm" aria-label={`Edit ${c.name}`} onClick={() => setEditing(c)}>
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Delete ${c.name}`}
                          disabled={c.product_count > 0}
                          title={c.product_count > 0 ? "Move or archive its products first" : undefined}
                          onClick={() => setRemoving(c)}
                        >
                          <Trash2 />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState icon={FolderPlus} title="No categories yet" action={<Button onClick={() => setEditing("new")}>New category</Button>} />
            )
          }
        </QueryState>
      </CardContent>
      {editing ? <CategoryDialog category={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Delete ${removing?.name}?`}
        confirmLabel="Delete"
        destructive
        onConfirm={() => remove.mutateAsync(removing!)}
      />
    </Card>
  );
}

function CategoryDialog({ category, onClose }: { category: Category | null; onClose: () => void }) {
  const [name, setName] = useState(category?.name ?? "");
  const [description, setDescription] = useState(category?.description ?? "");
  const [order, setOrder] = useState(String(category?.display_order ?? 0));
  const [active, setActive] = useState(category?.is_active ?? true);
  const save = useApiMutation(
    () =>
      api(category ? `/categories/${category.id}` : "/categories", {
        method: category ? "PATCH" : "POST",
        body: { name: name.trim(), description: description.trim() || null, display_order: Number(order) || 0, is_active: active },
      }),
    { invalidate: ["categories", "products"], success: "Category saved", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{category ? "Edit category" : "New category"}</DialogTitle>
        </DialogHeader>
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          <FormField label="Name" htmlFor="cat-name">
            <Input id="cat-name" required maxLength={150} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Description" htmlFor="cat-desc">
            <Textarea id="cat-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </FormField>
          <FormField label="Display order" htmlFor="cat-order">
            <Input id="cat-order" type="number" min={0} value={order} onChange={(e) => setOrder(e.target.value)} />
          </FormField>
          <Label className="font-normal">
            <Switch checked={active} onCheckedChange={setActive} /> Show at the POS
          </Label>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || save.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------- modifiers

function ModifiersTab() {
  const groups = useApi<ModifierGroup[]>(["modifiers", "all"], "/modifiers/groups", { include_inactive: true });
  const [editingGroup, setEditingGroup] = useState<ModifierGroup | "new" | null>(null);
  const [addingTo, setAddingTo] = useState<ModifierGroup | null>(null);
  const toggleOption = useApiMutation(
    (o: ModifierOption) => api(`/modifiers/options/${o.id}`, { method: "PATCH", body: { is_active: !o.is_active } }),
    { invalidate: ["modifiers", "products"], success: "Option updated" },
  );
  return (
    <div className="grid gap-4">
      <div className="flex justify-end">
        <Button onClick={() => setEditingGroup("new")}>
          <Plus /> New modifier group
        </Button>
      </div>
      <QueryState query={groups}>
        {(list) =>
          list.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {list.map((g) => (
                <Card key={g.id} className={g.is_active ? undefined : "opacity-60"}>
                  <CardHeader>
                    <CardTitle>{g.name}</CardTitle>
                    <CardDescription>
                      {g.selection_type === "SINGLE" ? "Single choice" : "Multiple choice"} · min {g.min_select}
                      {g.max_select ? ` · max ${g.max_select}` : ""}
                      {g.is_active ? "" : " · inactive"}
                    </CardDescription>
                    <CardAction className="flex gap-1">
                      <Button variant="ghost" size="icon-sm" aria-label={`Edit ${g.name}`} onClick={() => setEditingGroup(g)}>
                        <Pencil />
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => setAddingTo(g)}>
                        <Plus /> Option
                      </Button>
                    </CardAction>
                  </CardHeader>
                  <CardContent>
                    <ul className="divide-y text-sm">
                      {g.options.map((o) => (
                        <li key={o.id} className="flex items-center justify-between gap-2 py-2">
                          <span className={o.is_active ? undefined : "text-muted-foreground line-through"}>
                            {o.name}
                            {o.is_default ? <Badge variant="secondary" className="ml-2">default</Badge> : null}
                            {o.ingredient_id ? <Badge variant="outline" className="ml-2">uses stock</Badge> : null}
                          </span>
                          <span className="flex items-center gap-3">
                            <span className="text-muted-foreground tabular">
                              {o.price_delta_minor ? `${o.price_delta_minor > 0 ? "+" : ""}${formatMoney(o.price_delta_minor)}` : "—"}
                            </span>
                            <Switch aria-label={`${o.name} active`} checked={o.is_active} onCheckedChange={() => toggleOption.mutate(o)} />
                          </span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <EmptyState title="No modifier groups" description="Add groups such as Size, Spiciness or Extras, then attach them to products." />
          )
        }
      </QueryState>
      {editingGroup ? <GroupDialog group={editingGroup === "new" ? null : editingGroup} onClose={() => setEditingGroup(null)} /> : null}
      {addingTo ? <OptionDialog group={addingTo} onClose={() => setAddingTo(null)} /> : null}
    </div>
  );
}

function GroupDialog({ group, onClose }: { group: ModifierGroup | null; onClose: () => void }) {
  const [name, setName] = useState(group?.name ?? "");
  const [type, setType] = useState<"SINGLE" | "MULTIPLE">(group?.selection_type ?? "SINGLE");
  const [min, setMin] = useState(String(group?.min_select ?? 0));
  const [max, setMax] = useState(group?.max_select ? String(group.max_select) : "");
  const [active, setActive] = useState(group?.is_active ?? true);
  const save = useApiMutation(
    () => {
      const body = {
        name: name.trim(),
        selection_type: type,
        min_select: Number(min) || 0,
        max_select: type === "SINGLE" ? 1 : max ? Number(max) : null,
      };
      return group
        ? api(`/modifiers/groups/${group.id}`, {
            method: "PATCH",
            body: { ...body, is_active: active, clear_max_select: type === "MULTIPLE" && !max },
          })
        : api("/modifiers/groups", { method: "POST", body });
    },
    { invalidate: ["modifiers", "products"], success: "Modifier group saved", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{group ? "Edit modifier group" : "New modifier group"}</DialogTitle>
          <DialogDescription>Selection rules are enforced at the POS and by the server.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <FormField label="Name" htmlFor="g-name">
            <Input id="g-name" value={name} maxLength={150} onChange={(e) => setName(e.target.value)} placeholder="e.g. Spiciness" />
          </FormField>
          <FormField label="Selection" htmlFor="g-type">
            <NativeSelect id="g-type" value={type} onChange={(e) => setType(e.target.value as "SINGLE" | "MULTIPLE")}>
              <option value="SINGLE">Single choice (e.g. size)</option>
              <option value="MULTIPLE">Multiple choice (e.g. toppings)</option>
            </NativeSelect>
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Minimum" htmlFor="g-min" hint="1 = required">
              <Input id="g-min" type="number" min={0} max={type === "SINGLE" ? 1 : 20} value={min} onChange={(e) => setMin(e.target.value)} />
            </FormField>
            {type === "MULTIPLE" ? (
              <FormField label="Maximum" htmlFor="g-max" hint="Empty = no limit">
                <Input id="g-max" type="number" min={1} max={20} value={max} onChange={(e) => setMax(e.target.value)} />
              </FormField>
            ) : null}
          </div>
          {group ? (
            <Label className="font-normal">
              <Switch checked={active} onCheckedChange={setActive} /> Active
            </Label>
          ) : null}
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

function OptionDialog({ group, onClose }: { group: ModifierGroup; onClose: () => void }) {
  const ingredients = useApi<Ingredient[]>(["ingredients"], "/ingredients");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("0");
  const [isDefault, setIsDefault] = useState(false);
  const [ingredientId, setIngredientId] = useState("");
  const [qty, setQty] = useState("");
  const ingredient = ingredients.data?.find((i) => i.id === ingredientId);
  const priceMinor = price.trim().startsWith("-") ? -(parseMoney(price.trim().slice(1)) ?? 0) : parseMoney(price);
  const save = useApiMutation(
    () =>
      api(`/modifiers/groups/${group.id}/options`, {
        method: "POST",
        body: {
          name: name.trim(),
          price_delta_minor: priceMinor ?? 0,
          is_default: isDefault,
          ingredient_id: ingredientId || null,
          ingredient_quantity: ingredientId ? qty : null,
        },
      }),
    { invalidate: ["modifiers", "products"], success: "Option added", onSuccess: onClose },
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add option to {group.name}</DialogTitle>
          <DialogDescription>Optionally deduct an extra ingredient when this option is sold (e.g. extra egg).</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <FormField label="Name" htmlFor="o-name">
            <Input id="o-name" value={name} maxLength={150} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label="Price change (฿)" htmlFor="o-price" hint="0 for no change; negative for a cheaper option">
            <Input id="o-price" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
          </FormField>
          <Label className="font-normal">
            <Checkbox checked={isDefault} onCheckedChange={(v) => setIsDefault(v === true)} /> Selected by default
          </Label>
          <FormField label="Uses ingredient (optional)" htmlFor="o-ing">
            <NativeSelect id="o-ing" value={ingredientId} onChange={(e) => setIngredientId(e.target.value)}>
              <option value="">None</option>
              {(ingredients.data ?? []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name} ({i.base_unit})
                </option>
              ))}
            </NativeSelect>
          </FormField>
          {ingredient ? (
            <FormField label={`Quantity per serving (${ingredient.base_unit})`} htmlFor="o-qty">
              <Input id="o-qty" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
            </FormField>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!name.trim() || priceMinor === null || (!!ingredientId && !(Number(qty) > 0)) || save.isPending}
            onClick={() => save.mutate(undefined)}
          >
            Add option
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


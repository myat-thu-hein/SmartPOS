"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, useApiMutation } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { minorToInput, parseMoney } from "@/lib/format";
import type { Category, ModifierGroup, Product } from "@/types/api";

export const productSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(150),
  category_id: z.string().min(1, "Choose a category"),
  price: z
    .string()
    .trim()
    .refine((v) => parseMoney(v) !== null, "Enter a price such as 120 or 120.50"),
  sku: z
    .string()
    .trim()
    .max(64)
    .regex(/^[A-Za-z0-9\-_.]*$/, "Use letters, numbers, - _ or ."),
  description: z.string().max(5000),
  image_url: z.union([z.literal(""), z.url({ protocol: /^https?$/, error: "Enter a full URL starting with https://" })]),
  is_available: z.boolean(),
  modifier_group_ids: z.array(z.string()),
});
export type ProductFormValues = z.infer<typeof productSchema>;

export function toProductPayload(values: ProductFormValues) {
  return {
    name: values.name.trim(),
    category_id: values.category_id,
    price_minor: parseMoney(values.price),
    sku: values.sku.trim() || null,
    description: values.description.trim() || null,
    image_url: values.image_url || null,
    is_available: values.is_available,
  };
}

export function ProductDialog({
  product,
  categories,
  groups,
  onClose,
}: {
  product: Product | null;
  categories: Category[];
  groups: ModifierGroup[];
  onClose: () => void;
}) {
  const form = useForm<ProductFormValues>({
    resolver: zodResolver(productSchema),
    defaultValues: {
      name: product?.name ?? "",
      category_id: product?.category_id ?? categories[0]?.id ?? "",
      price: product ? minorToInput(product.price_minor) : "",
      sku: product?.sku ?? "",
      description: product?.description ?? "",
      image_url: product?.image_url ?? "",
      is_available: product?.is_available ?? true,
      modifier_group_ids: product?.modifier_groups.map((g) => g.id) ?? [],
    },
  });
  const { register, handleSubmit, setValue, setError, formState, control } = form;
  const selected = useWatch({ control, name: "modifier_group_ids" });
  const available = useWatch({ control, name: "is_available" });

  const save = useApiMutation(
    async (values: ProductFormValues) => {
      const payload = toProductPayload(values);
      if (product) {
        await api(`/products/${product.id}`, { method: "PATCH", body: payload });
        return api<Product>(`/products/${product.id}/modifier-groups`, {
          method: "PUT",
          body: { modifier_group_ids: values.modifier_group_ids },
        });
      }
      return api<Product>("/products", { method: "POST", body: { ...payload, modifier_group_ids: values.modifier_group_ids } });
    },
    {
      silent: true,
      invalidate: ["products", "categories", "recipes"],
      success: product ? "Product updated" : "Product created",
      onSuccess: onClose,
    },
  );

  function onSubmit(values: ProductFormValues) {
    save.mutate(values, {
      onError: (error) => {
        if (error instanceof ApiError) {
          const fields = error.fieldErrors;
          if (fields.price_minor) setError("price", { message: fields.price_minor });
          setError("root", { message: error.message });
        }
      },
    });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{product ? `Edit ${product.name}` : "New product"}</DialogTitle>
          <DialogDescription>Prices are in baht. Changing a price does not alter past orders or receipts.</DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Name" htmlFor="p-name" error={formState.errors.name?.message} className="sm:col-span-2">
              <Input id="p-name" aria-invalid={!!formState.errors.name} {...register("name")} autoFocus />
            </FormField>
            <FormField label="Category" htmlFor="p-category" error={formState.errors.category_id?.message}>
              <NativeSelect id="p-category" {...register("category_id")}>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
            </FormField>
            <FormField label="Price (฿)" htmlFor="p-price" error={formState.errors.price?.message}>
              <Input id="p-price" inputMode="decimal" aria-invalid={!!formState.errors.price} {...register("price")} />
            </FormField>
            <FormField label="SKU (optional)" htmlFor="p-sku" error={formState.errors.sku?.message}>
              <Input id="p-sku" {...register("sku")} />
            </FormField>
            <FormField label="Image URL (optional)" htmlFor="p-image" error={formState.errors.image_url?.message}>
              <Input id="p-image" type="url" {...register("image_url")} />
            </FormField>
            <FormField label="Description" htmlFor="p-desc" className="sm:col-span-2">
              <Textarea id="p-desc" rows={2} {...register("description")} />
            </FormField>
          </div>
          <Label className="font-normal">
            <Switch checked={available} onCheckedChange={(v) => setValue("is_available", v)} /> Available for sale
          </Label>
          {groups.length ? (
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-medium">Modifier groups</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {groups.map((g) => (
                  <Label key={g.id} className="rounded-md border px-3 py-2 font-normal">
                    <Checkbox
                      checked={selected.includes(g.id)}
                      onCheckedChange={(checked) =>
                        setValue(
                          "modifier_group_ids",
                          checked ? [...selected, g.id] : selected.filter((id) => id !== g.id),
                        )
                      }
                    />
                    {g.name}
                  </Label>
                ))}
              </div>
            </fieldset>
          ) : null}
          {formState.errors.root ? (
            <p role="alert" className="text-sm text-status-critical">
              {formState.errors.root.message}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? <Loader2 className="animate-spin" /> : null} Save product
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

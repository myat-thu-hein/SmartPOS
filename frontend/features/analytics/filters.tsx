"use client";

import { X } from "lucide-react";

import { DateRangeFilter, rangeForPreset, type DateRange } from "@/components/shared/date-range-filter";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/select";
import { useApi } from "@/hooks/use-api";
import type { Category, PaymentMethod, Product } from "@/types/api";

export interface AnalyticsFilterState {
  range: DateRange;
  categoryId: string;
  productId: string;
  paymentMethod: string;
  orderType: string;
}

export function defaultFilters(timeZone?: string): AnalyticsFilterState {
  return { range: rangeForPreset("30d", timeZone), categoryId: "", productId: "", paymentMethod: "", orderType: "" };
}

/** Query parameters understood by every /analytics/* and /reports/* endpoint. */
export function filterQuery(f: AnalyticsFilterState): Record<string, string | undefined> {
  return {
    start_date: f.range.start,
    end_date: f.range.end,
    category_id: f.categoryId || undefined,
    product_id: f.productId || undefined,
    payment_method: f.paymentMethod || undefined,
    order_type: f.orderType || undefined,
  };
}

export function AnalyticsFilters({
  value,
  onChange,
  timeZone,
  showDimensions = true,
}: {
  value: AnalyticsFilterState;
  onChange: (next: AnalyticsFilterState) => void;
  timeZone?: string;
  showDimensions?: boolean;
}) {
  const categories = useApi<Category[]>(["categories"], showDimensions ? "/categories" : null);
  const products = useApi<Product[]>(["products"], showDimensions ? "/products" : null, { include_inactive: true });
  const methods = useApi<PaymentMethod[]>(["payment-methods"], showDimensions ? "/payments/methods" : null, { include_inactive: true });
  const productOptions = (products.data ?? []).filter((p) => !value.categoryId || p.category_id === value.categoryId);
  const set = (patch: Partial<AnalyticsFilterState>) => onChange({ ...value, ...patch });
  const filtered = value.categoryId || value.productId || value.paymentMethod || value.orderType;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <DateRangeFilter value={value.range} onChange={(range) => set({ range })} timeZone={timeZone} />
      {showDimensions ? (
        <>
          <NativeSelect
            aria-label="Category"
            className="w-40"
            value={value.categoryId}
            onChange={(e) => set({ categoryId: e.target.value, productId: "" })}
          >
            <option value="">All categories</option>
            {(categories.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect aria-label="Product" className="w-44" value={value.productId} onChange={(e) => set({ productId: e.target.value })}>
            <option value="">All products</option>
            {productOptions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect aria-label="Payment method" className="w-40" value={value.paymentMethod} onChange={(e) => set({ paymentMethod: e.target.value })}>
            <option value="">All payments</option>
            {(methods.data ?? []).map((m) => (
              <option key={m.id} value={m.code}>
                {m.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect aria-label="Order type" className="w-36" value={value.orderType} onChange={(e) => set({ orderType: e.target.value })}>
            <option value="">All order types</option>
            <option value="DINE_IN">Dine-in</option>
            <option value="TAKEAWAY">Takeaway</option>
          </NativeSelect>
          {filtered ? (
            <Button variant="ghost" size="sm" onClick={() => set({ categoryId: "", productId: "", paymentMethod: "", orderType: "" })}>
              <X /> Clear filters
            </Button>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

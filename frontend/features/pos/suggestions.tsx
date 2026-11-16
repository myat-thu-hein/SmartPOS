"use client";

import { keepPreviousData } from "@tanstack/react-query";
import { Plus, Sparkles } from "lucide-react";

import { useApi } from "@/hooks/use-api";
import { formatMoney } from "@/lib/format";
import type { Product, ProductSuggestion } from "@/types/api";

const HEADING: Record<ProductSuggestion["kind"], string> = {
  ordered_together: "Often ordered together",
  customer_usual: "Customer's usual",
  popular_now: "Popular now",
};

/**
 * Add-on suggestions mined from this restaurant's own sales history (see
 * backend/app/services/suggestions.py). Each chip explains why it is shown.
 */
export function SuggestionStrip({
  cartProductIds,
  customerId,
  products,
  onAdd,
}: {
  cartProductIds: string[];
  customerId: string | null;
  products: Product[];
  onAdd: (product: Product) => void;
}) {
  const ids = [...new Set(cartProductIds)].sort();
  const query = useApi<ProductSuggestion[]>(
    ["suggestions", ids.join(","), customerId],
    "/products/suggestions",
    { product_id: ids, customer_id: customerId ?? undefined },
    { staleTime: 60_000, placeholderData: keepPreviousData },
  );
  const byId = new Map(products.map((p) => [p.id, p]));
  const inCart = new Set(ids);
  const items = (query.data ?? [])
    // Previous suggestions stay on screen while new ones load; never offer what is already in the cart.
    .filter((s) => !inCart.has(s.product_id))
    .map((s) => ({ suggestion: s, product: byId.get(s.product_id) }))
    .filter((x): x is { suggestion: ProductSuggestion; product: Product } => !!x.product?.is_available);
  if (!items.length) return null;
  const kinds = new Set(items.map((x) => x.suggestion.kind));
  const heading = kinds.size === 1 ? HEADING[items[0].suggestion.kind] : "Suggested for this order";

  return (
    <section aria-label="Suggestions" className="grid min-w-0 gap-2 border-t py-3">
      <p className="flex items-center gap-1.5 px-4 text-xs font-medium text-muted-foreground">
        <Sparkles className="size-3.5 text-primary" aria-hidden /> {heading}
      </p>
      {/* One scrolling row, so suggestions never squeeze the cart lines above. */}
      <ul className="flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:thin]">
        {items.map(({ suggestion, product }) => (
          <li key={product.id} className="w-56 max-w-[80%] shrink-0">
            <button
              type="button"
              onClick={() => onAdd(product)}
              title={suggestion.reason}
              aria-label={`Suggested: add ${product.name}, ${formatMoney(product.price_minor)}. ${suggestion.reason}`}
              className="group flex w-full items-center gap-2 rounded-full border bg-background py-1 pr-3 pl-1 text-left text-xs transition-colors hover:border-primary/50 hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <Plus className="size-3.5" aria-hidden />
              </span>
              <span className="min-w-0">
                <span className="block truncate font-medium">{product.name.split(" (")[0]}</span>
                <span className="block truncate text-[11px] text-muted-foreground">{suggestion.reason}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

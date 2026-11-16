"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChefHat,
  Loader2,
  Minus,
  PackageX,
  Plus,
  Printer,
  Save,
  Search,
  ShoppingCart,
  Trash2,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState, LoadingRows } from "@/components/shared/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { PaymentDialog } from "@/features/orders/payment-dialog";
import {
  cartReducer,
  estimatedSubtotal,
  itemCount,
  toOrderItems,
  unitPrice,
  type CartLine,
} from "@/features/pos/cart";
import {
  CustomerPicker,
  type SelectedCustomer,
} from "@/features/pos/customer-picker";
import { ModifierDialog } from "@/features/pos/modifier-dialog";
import { needsModifierDialog } from "@/features/pos/modifiers";
import { SuggestionStrip } from "@/features/pos/suggestions";
import { useApi, useApiMutation } from "@/hooks/use-api";
import { api, ApiError, errorMessage, newIdempotencyKey } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatMoney, formatPercentBps } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type {
  Category,
  DiningTable,
  Discount,
  Order,
  OrderDraftInput,
  OrderQuote,
  OrderType,
  Product,
} from "@/types/api";

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export function PosScreen() {
  const { t } = useI18n();
  const { restaurantId, can } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const editOrderId = searchParams.get("order");
  const presetTable = searchParams.get("table");

  const products = useApi<Product[]>(["products", "pos"], "/products");
  const categories = useApi<Category[]>(["categories"], "/categories");
  const tables = useApi<DiningTable[]>(["tables"], "/tables");
  const discounts = useApi<Discount[]>(["discounts"], "/discounts");
  const editing = useApi<Order>(
    ["order", editOrderId],
    editOrderId ? `/orders/${editOrderId}` : null,
  );

  const [lines, dispatch] = useReducer(cartReducer, []);
  const [orderType, setOrderType] = useState<OrderType>(
    presetTable ? "DINE_IN" : "TAKEAWAY",
  );
  const [tableId, setTableId] = useState<string>(presetTable ?? "");
  const [customer, setCustomer] = useState<SelectedCustomer | null>(null);
  const [discountId, setDiscountId] = useState("");
  const [points, setPoints] = useState(0);
  const [notes, setNotes] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("all");
  const [modifierProduct, setModifierProduct] = useState<Product | null>(null);
  const [paymentOrder, setPaymentOrder] = useState<Order | null>(null);
  const [doneOrder, setDoneOrder] = useState<Order | null>(null);
  const [orderKey, setOrderKey] = useState(() => newIdempotencyKey("order"));
  const searchRef = useRef<HTMLInputElement>(null);

  // Load an existing order into the cart when editing (e.g. adding items to a table).
  const loadedOrder = useRef<string | null>(null);
  useEffect(() => {
    const order = editing.data;
    if (!order || loadedOrder.current === order.id) return;
    loadedOrder.current = order.id;
    dispatch({
      type: "replace",
      lines: order.items.map((item) => ({
        lineId: item.id,
        productId: item.product_id,
        name: item.product_name,
        basePriceMinor: item.base_price_minor,
        quantity: item.quantity,
        notes: item.notes ?? "",
        modifiers: item.modifiers
          .filter((m) => m.modifier_option_id)
          .map((m) => ({
            optionId: m.modifier_option_id as string,
            groupName: m.group_name,
            name: m.option_name,
            priceDeltaMinor: m.price_delta_minor,
          })),
      })),
    });
    setOrderType(order.order_type);
    setTableId(order.table_id ?? "");
    setNotes(order.notes ?? "");
  }, [editing.data]);

  // Keyboard shortcuts: "/" search, Escape clear search, Ctrl/Cmd+Enter confirm & pay.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
      if (event.key === "/" && !typing) {
        event.preventDefault();
        searchRef.current?.focus();
      } else if (event.key === "Escape" && target === searchRef.current) {
        setSearch("");
      } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        // Not while a dialog (modifiers, payment, receipt) is open: Enter belongs to it.
        if (document.querySelector('[role="dialog"], [role="alertdialog"]'))
          return;
        document.getElementById("pos-pay-button")?.click();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const visibleProducts = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (products.data ?? []).filter(
      (p) =>
        (category === "all" || p.category_id === category) &&
        (!term ||
          p.name.toLowerCase().includes(term) ||
          (p.sku ?? "").toLowerCase().includes(term)),
    );
  }, [products.data, search, category]);

  const quantityInCart = useMemo(() => {
    const counts = new Map<string, number>();
    for (const line of lines)
      counts.set(
        line.productId,
        (counts.get(line.productId) ?? 0) + line.quantity,
      );
    return counts;
  }, [lines]);

  const editingOrder = editing.data;
  const isEditing = !!editingOrder;
  const draft: OrderDraftInput | null = lines.length
    ? {
        order_type: orderType,
        table_id: orderType === "DINE_IN" ? tableId || null : null,
        customer_id: customer?.id ?? null,
        notes: notes.trim() || null,
        items: toOrderItems(lines),
        discount: discountId ? { discount_id: discountId } : null,
        loyalty_points_to_redeem: customer ? points : 0,
      }
    : null;
  const quotePayload = useDebounced(draft);
  const canQuote =
    !!quotePayload &&
    (quotePayload.order_type === "TAKEAWAY" || !!quotePayload.table_id);
  const quote = useQuery({
    queryKey: [restaurantId, "quote", quotePayload],
    queryFn: () =>
      api<OrderQuote>("/orders/quote", { method: "POST", body: quotePayload }),
    enabled: canQuote,
    retry: false,
    placeholderData: (prev) => prev,
  });

  function resetCart() {
    dispatch({ type: "clear" });
    setCustomer(null);
    setDiscountId("");
    setPoints(0);
    setNotes("");
    setOrderKey(newIdempotencyKey("order"));
    if (orderType === "DINE_IN") setTableId("");
  }

  const createOrder = useApiMutation(
    ({ confirm }: { confirm: boolean }) =>
      api<Order>("/orders", {
        method: "POST",
        idempotencyKey: orderKey,
        body: { ...draft, confirm },
      }),
    {
      invalidate: ["orders", "tables", "dashboard", "kitchen", "ingredients"],
      onSuccess: (order, { confirm }) => {
        if (!confirm) toast.success(`Draft #${order.display_number} saved`);
        resetCart();
      },
    },
  );

  const updateOrder = useApiMutation(
    () =>
      api<Order>(`/orders/${editingOrder!.id}`, {
        method: "PATCH",
        body: { items: toOrderItems(lines), notes: notes.trim() || null },
      }),
    {
      invalidate: ["orders", "order", "tables", "kitchen", "ingredients"],
      success: (o) => `Order #${o.display_number} updated`,
      onSuccess: (o) => router.push(`/orders/${o.id}`),
    },
  );

  async function submit(mode: "kitchen" | "pay" | "draft") {
    if (!draft) return;
    if (orderType === "DINE_IN" && !tableId) {
      toast.error("Choose a table for dine-in orders.");
      return;
    }
    if (isEditing) {
      updateOrder.mutate(undefined);
      return;
    }
    const order = await createOrder
      .mutateAsync({ confirm: mode !== "draft" })
      .catch(() => null);
    if (!order) return;
    if (mode === "kitchen")
      toast.success(`Order #${order.display_number} sent to the kitchen`);
    if (mode === "pay") {
      if (order.payment_status === "PAID") setDoneOrder(order);
      else setPaymentOrder(order);
    }
  }

  function addProduct(product: Product) {
    if (!product.is_available) return;
    if (needsModifierDialog(product)) {
      setModifierProduct(product);
      return;
    }
    dispatch({
      type: "add",
      line: {
        productId: product.id,
        name: product.name,
        basePriceMinor: product.price_minor,
        quantity: 1,
        modifiers: [],
        notes: "",
      },
    });
  }

  const busy = createOrder.isPending || updateOrder.isPending;
  const tableOptions = (tables.data ?? []).filter(
    (tbl) =>
      tbl.status === "AVAILABLE" ||
      tbl.status === "RESERVED" ||
      tbl.id === tableId,
  );
  const quoteError =
    quote.error instanceof ApiError
      ? quote.error.message
      : quote.error
        ? errorMessage(quote.error)
        : null;
  const totals = canQuote && quote.data && !quote.isError ? quote.data : null;

  if (products.isError)
    return (
      <ErrorState error={products.error} onRetry={() => products.refetch()} />
    );

  return (
    <div className={cn("grid gap-4 lg:grid-cols-[minmax(0,1fr)_400px]", lines.length && "pb-20 lg:pb-0")}>
      {/* ------------------------------------------------ product browser */}
      <section aria-label="Products" className="min-w-0">
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground"
              aria-hidden
            />
            <Input
              ref={searchRef}
              aria-label={t("Search products")}
              placeholder={`${t("Search products")}  ( / )`}
              className="h-10 pl-9"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {isEditing ? (
            <Badge variant="info" className="h-8 px-3 text-sm">
              Editing order #{editingOrder.display_number}
            </Badge>
          ) : null}
        </div>
        <div
          className="mb-4 flex gap-2 overflow-x-auto pb-1"
          role="tablist"
          aria-label="Categories"
        >
          {[{ id: "all", name: t("All") }, ...(categories.data ?? [])].map(
            (c) => (
              <Button
                key={c.id}
                role="tab"
                aria-selected={category === c.id}
                variant={category === c.id ? "default" : "outline"}
                size="sm"
                className="shrink-0"
                onClick={() => setCategory(c.id)}
              >
                {c.name}
              </Button>
            ),
          )}
        </div>
        {products.isPending ? (
          <LoadingRows rows={6} />
        ) : visibleProducts.length ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
            {visibleProducts.map((product) => {
              const inCart = quantityInCart.get(product.id) ?? 0;
              return (
                <button
                  key={product.id}
                  type="button"
                  onClick={() => addProduct(product)}
                  disabled={!product.is_available}
                  aria-label={`Add ${product.name}, ${formatMoney(product.price_minor)}${inCart ? `, ${inCart} in cart` : ""}`}
                  className={cn(
                    "group relative flex min-h-28 flex-col justify-between rounded-xl border bg-card p-3 text-left shadow-card transition duration-150 hover:-translate-y-0.5 hover:border-primary/60 hover:shadow-raised focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none active:translate-y-0 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:translate-y-0 disabled:hover:shadow-card motion-reduce:transform-none",
                    inCart > 0 && "border-primary/50 bg-accent/40",
                  )}
                >
                  {inCart > 0 ? (
                    <span
                      key={inCart}
                      aria-hidden
                      className="absolute -top-2 -right-2 flex min-w-6 animate-pop items-center justify-center rounded-full bg-primary px-1.5 text-xs leading-6 font-semibold text-primary-foreground shadow-card tabular"
                    >
                      {inCart}
                    </span>
                  ) : null}
                  <span className="line-clamp-3 text-sm font-medium leading-snug">
                    {product.name}
                  </span>
                  <span className="mt-3 flex items-center justify-between gap-2">
                    <span className="font-semibold tabular">
                      {formatMoney(product.price_minor)}
                    </span>
                    {!product.is_available ? (
                      <Badge variant="danger">
                        <PackageX aria-hidden /> Sold out
                      </Badge>
                    ) : (
                      <Plus
                        className="size-4 text-muted-foreground group-hover:text-primary"
                        aria-hidden
                      />
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <EmptyState
            icon={Search}
            title={
              products.data?.length ? "No products match" : "No products yet"
            }
            description={
              products.data?.length
                ? "Try another search or category."
                : "A manager can add products on the Menu page."
            }
            action={
              !products.data?.length && can("menu:write") ? (
                <Button asChild>
                  <Link href="/menu">Open menu</Link>
                </Button>
              ) : undefined
            }
          />
        )}
      </section>

      {/* ------------------------------------------------ cart */}
      <aside
        id="pos-cart"
        aria-label={t("Cart")}
        className="scroll-mt-20 lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)]"
      >
        <div className="flex h-full flex-col rounded-xl border bg-card shadow-xs">
          <div className="grid gap-3 border-b p-4">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-semibold">
                <ShoppingCart className="size-4" aria-hidden /> {t("Cart")}
                {lines.length ? (
                  <Badge variant="secondary">{itemCount(lines)}</Badge>
                ) : null}
              </h2>
              {lines.length && !isEditing ? (
                <Button variant="ghost" size="sm" onClick={resetCart}>
                  <Trash2 /> {t("Clear")}
                </Button>
              ) : null}
            </div>
            {!isEditing ? (
              <>
                <div
                  className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1"
                  role="radiogroup"
                  aria-label="Order type"
                >
                  {(["DINE_IN", "TAKEAWAY"] as const).map((type) => (
                    <button
                      key={type}
                      type="button"
                      role="radio"
                      aria-checked={orderType === type}
                      onClick={() => setOrderType(type)}
                      className={cn(
                        "rounded-md py-1.5 text-sm font-medium text-muted-foreground",
                        orderType === type &&
                          "bg-card text-foreground shadow-sm",
                      )}
                    >
                      {type === "DINE_IN" ? t("Dine-in") : t("Takeaway")}
                    </button>
                  ))}
                </div>
                {orderType === "DINE_IN" ? (
                  <NativeSelect
                    aria-label={t("Table")}
                    value={tableId}
                    onChange={(e) => setTableId(e.target.value)}
                  >
                    <option value="">{t("Table")}…</option>
                    {tableOptions.map((tbl) => (
                      <option key={tbl.id} value={tbl.id}>
                        {tbl.name} · {tbl.capacity} seats
                        {tbl.status === "RESERVED" ? " · reserved" : ""}
                      </option>
                    ))}
                  </NativeSelect>
                ) : null}
                <CustomerPicker
                  value={customer}
                  onChange={(c) => {
                    setCustomer(c);
                    setPoints(0);
                  }}
                />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {editingOrder.table_name
                  ? `Table ${editingOrder.table_name}`
                  : t("Takeaway")}{" "}
                · changes are re-priced and stock is reconciled on save.
              </p>
            )}
          </div>

          <div className="min-h-32 flex-1 overflow-y-auto p-2">
            {lines.length ? (
              <ul className="divide-y">
                {lines.map((line) => (
                  <CartRow key={line.lineId} line={line} dispatch={dispatch} />
                ))}
              </ul>
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 py-10 text-center text-sm text-muted-foreground">
                <ShoppingCart className="size-6" aria-hidden />
                {t("Empty cart")}
              </div>
            )}
          </div>
          {can("orders:create") ? (
            <SuggestionStrip
              cartProductIds={lines.map((l) => l.productId)}
              customerId={customer?.id ?? null}
              products={products.data ?? []}
              onAdd={addProduct}
            />
          ) : null}

          <div className="grid gap-3 border-t p-4">
            {!isEditing && lines.length ? (
              <div className="grid grid-cols-2 gap-2">
                <NativeSelect
                  aria-label={t("Discount")}
                  value={discountId}
                  onChange={(e) => setDiscountId(e.target.value)}
                >
                  <option value="">{t("Discount")}: none</option>
                  {(discounts.data ?? []).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                      {d.requires_manager ? " (manager)" : ""}
                    </option>
                  ))}
                </NativeSelect>
                {customer && customer.loyaltyBalance > 0 ? (
                  <Input
                    type="number"
                    min={0}
                    max={
                      totals?.max_redeemable_points ?? customer.loyaltyBalance
                    }
                    aria-label="Loyalty points to redeem"
                    placeholder="Redeem points"
                    value={points || ""}
                    onChange={(e) =>
                      setPoints(
                        Math.max(0, Math.floor(Number(e.target.value) || 0)),
                      )
                    }
                  />
                ) : (
                  <span />
                )}
              </div>
            ) : null}
            {lines.length ? (
              <Textarea
                aria-label={t("Notes")}
                placeholder={`${t("Notes")} (order)`}
                className="min-h-10"
                rows={1}
                value={notes}
                maxLength={500}
                onChange={(e) => setNotes(e.target.value)}
              />
            ) : null}
            <Totals lines={lines} totals={totals} loading={quote.isFetching} />
            {quoteError && lines.length ? (
              <p role="alert" className="text-sm text-status-critical">
                {quoteError}
              </p>
            ) : null}
            {isEditing ? (
              <div className="grid grid-cols-2 gap-2">
                <Button variant="outline" asChild>
                  <Link href={`/orders/${editingOrder.id}`}>{t("Cancel")}</Link>
                </Button>
                <Button
                  onClick={() => submit("kitchen")}
                  disabled={!lines.length || busy}
                >
                  {busy ? <Loader2 className="animate-spin" /> : <Save />}{" "}
                  Update order
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant="outline"
                  onClick={() => submit("draft")}
                  disabled={!lines.length || busy}
                >
                  <Save /> {t("Save draft")}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => submit("kitchen")}
                  disabled={!lines.length || busy}
                >
                  <ChefHat /> {t("Send to kitchen")}
                </Button>
                <Button
                  id="pos-pay-button"
                  size="xl"
                  className="col-span-2"
                  onClick={() => submit("pay")}
                  disabled={!lines.length || busy || !!quoteError}
                >
                  {busy ? <Loader2 className="animate-spin" /> : <Wallet />}
                  {t("Confirm & pay")}
                  {totals ? ` · ${formatMoney(totals.total_minor)}` : ""}
                </Button>
              </div>
            )}
            <p className="text-center text-[11px] text-muted-foreground">
              Shortcuts: <kbd>/</kbd> search · <kbd>Ctrl</kbd>+<kbd>Enter</kbd>{" "}
              confirm &amp; pay
            </p>
          </div>
        </div>
      </aside>

      {/* Phones and tablets: the cart sits below the products, so keep the order one tap away. */}
      {lines.length ? (
        <div className="no-print fixed inset-x-0 bottom-0 z-20 border-t bg-background/95 p-3 shadow-raised backdrop-blur lg:hidden">
          <Button
            size="lg"
            className="w-full justify-between"
            onClick={() => document.getElementById("pos-cart")?.scrollIntoView({ behavior: "smooth", block: "start" })}
          >
            <span className="flex items-center gap-2">
              <ShoppingCart aria-hidden /> {t("Review order")} · {itemCount(lines)}
            </span>
            <span className="tabular">{formatMoney(totals ? totals.total_minor : estimatedSubtotal(lines))}</span>
          </Button>
        </div>
      ) : null}
      {modifierProduct ? (
        <ModifierDialog
          product={modifierProduct}
          onClose={() => setModifierProduct(null)}
          onAdd={(line) => {
            dispatch({ type: "add", line });
            setModifierProduct(null);
          }}
        />
      ) : null}
      {paymentOrder ? (
        <PaymentDialog
          key={paymentOrder.id}
          order={paymentOrder}
          open
          onOpenChange={(open) => {
            if (open) return;
            toast.info(
              `Order #${paymentOrder.display_number} is confirmed but not paid`,
              {
                description:
                  "It is in the kitchen queue. Take payment later from Orders.",
                action: {
                  label: "Open",
                  onClick: () => router.push(`/orders/${paymentOrder.id}`),
                },
              },
            );
            setPaymentOrder(null);
          }}
          onPaid={(order) => {
            setPaymentOrder(null);
            if (order.payment_status === "PAID") setDoneOrder(order);
          }}
        />
      ) : null}
      {doneOrder ? (
        <PaidDialog order={doneOrder} onClose={() => setDoneOrder(null)} />
      ) : null}
    </div>
  );
}

function CartRow({
  line,
  dispatch,
}: {
  line: CartLine;
  dispatch: React.Dispatch<Parameters<typeof cartReducer>[1]>;
}) {
  return (
    <li className="flex gap-3 px-2 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-snug font-medium">{line.name}</p>
        {line.modifiers.length ? (
          <p className="text-xs text-muted-foreground">
            {line.modifiers.map((m) => m.name).join(", ")}
          </p>
        ) : null}
        {line.notes ? (
          <p className="text-xs text-muted-foreground italic">“{line.notes}”</p>
        ) : null}
        <p className="mt-1 text-xs text-muted-foreground tabular">
          {formatMoney(unitPrice(line))} each
        </p>
      </div>
      <div className="flex flex-col items-end gap-2">
        <span className="text-sm font-semibold tabular">
          {formatMoney(unitPrice(line) * line.quantity)}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon-sm"
            aria-label={`Decrease ${line.name}`}
            onClick={() =>
              dispatch({ type: "increment", lineId: line.lineId, by: -1 })
            }
          >
            {line.quantity === 1 ? <Trash2 /> : <Minus />}
          </Button>
          <span
            className="w-7 text-center text-sm font-semibold tabular"
            aria-label="Quantity"
          >
            {line.quantity}
          </span>
          <Button
            variant="outline"
            size="icon-sm"
            aria-label={`Increase ${line.name}`}
            onClick={() =>
              dispatch({ type: "increment", lineId: line.lineId, by: 1 })
            }
          >
            <Plus />
          </Button>
        </div>
      </div>
    </li>
  );
}

function Totals({
  lines,
  totals,
  loading,
}: {
  lines: CartLine[];
  totals: OrderQuote | null;
  loading: boolean;
}) {
  const { t } = useI18n();
  if (!lines.length) return null;
  if (!totals) {
    return (
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{t("Subtotal")} (estimate)</span>
        <span className="tabular">{formatMoney(estimatedSubtotal(lines))}</span>
      </div>
    );
  }
  const rows: [string, number, boolean?][] = [
    [t("Subtotal"), totals.subtotal_minor],
  ];
  if (totals.discount_minor)
    rows.push([
      `${t("Discount")} · ${totals.discount_name ?? ""}`,
      -totals.discount_minor,
    ]);
  if (totals.loyalty_discount_minor)
    rows.push(["Loyalty points", -totals.loyalty_discount_minor]);
  if (totals.service_charge_minor)
    rows.push([
      `${t("Service charge")} ${formatPercentBps(totals.service_charge_bps)}`,
      totals.service_charge_minor,
    ]);
  rows.push([
    `${t("Tax")} ${formatPercentBps(totals.tax_rate_bps)}${totals.prices_include_tax ? " (included)" : ""}`,
    totals.tax_minor,
    totals.prices_include_tax,
  ]);
  return (
    <dl
      className={cn("grid gap-1 text-sm", loading && "opacity-60")}
      aria-live="polite"
    >
      {rows.map(([label, value, included]) => (
        <div key={label} className="flex justify-between text-muted-foreground">
          <dt>{label}</dt>
          <dd className="tabular">
            {included ? `(${formatMoney(value)})` : formatMoney(value)}
          </dd>
        </div>
      ))}
      <div className="mt-1 flex justify-between border-t pt-2 text-base font-semibold">
        <dt>{t("Total")}</dt>
        <dd className="tabular">{formatMoney(totals.total_minor)}</dd>
      </div>
    </dl>
  );
}

function PaidDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  const { t } = useI18n();
  const change = order.payments.reduce((s, p) => s + p.change_minor, 0);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader className="items-center text-center">
          <CheckCircle2 className="size-10 text-status-good-text" aria-hidden />
          <DialogTitle>Order #{order.display_number} paid</DialogTitle>
          <DialogDescription>
            {formatMoney(order.amount_paid_minor)} recorded
            {change > 0 ? ` · give change ${formatMoney(change)}` : ""}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="sm:justify-center">
          <Button variant="outline" asChild>
            <a href={`/receipts/${order.id}`} target="_blank" rel="noopener">
              <Printer /> {t("Print receipt")}
            </a>
          </Button>
          <Button onClick={onClose} autoFocus>
            New order
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

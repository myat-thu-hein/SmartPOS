"use client";

import { ArrowLeft, Ban, CheckCircle2, Info, Pencil, Printer, Send, Undo2, Wallet } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { QueryState } from "@/components/shared/query-state";
import { OrderStatusBadge, PaymentStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { PaymentDialog } from "@/features/orders/payment-dialog";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { newIdempotencyKey } from "@/lib/api";
import { formatDateTime, formatMoney, formatPercentBps, humanize, minorToInput, parseMoney } from "@/lib/format";
import type { Order, OrderStatus, Payment } from "@/types/api";

const NEXT_LABEL: Partial<Record<OrderStatus, { label: string; icon: typeof Send }>> = {
  CONFIRMED: { label: "Confirm & send to kitchen", icon: Send },
  PREPARING: { label: "Start preparing", icon: Send },
  READY: { label: "Mark ready", icon: CheckCircle2 },
  COMPLETED: { label: "Mark completed", icon: CheckCircle2 },
};

const INVALIDATE = ["order", "orders", "tables", "kitchen", "dashboard", "ingredients", "customers"];

export function OrderScreen() {
  const { id } = useParams<{ id: string }>();
  const query = useApi<Order>(["order", id], `/orders/${id}`);
  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
        <Link href="/orders">
          <ArrowLeft /> Orders
        </Link>
      </Button>
      <QueryState query={query}>{(order) => <OrderDetail order={order} />}</QueryState>
    </>
  );
}

function OrderDetail({ order }: { order: Order }) {
  const { can } = useAuth();
  const [paying, setPaying] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [refunding, setRefunding] = useState<Payment | null>(null);

  const transition = useApiMutation(
    (status: OrderStatus) =>
      status === "CONFIRMED"
        ? api<Order>(`/orders/${order.id}/confirm`, { method: "POST" })
        : api<Order>(`/orders/${order.id}/status`, { method: "POST", body: { status } }),
    { invalidate: INVALIDATE, success: (o) => `Order is now ${humanize(o.status).toLowerCase()}` },
  );

  const payable = ["CONFIRMED", "PREPARING", "READY", "COMPLETED"].includes(order.status) && order.balance_due_minor > 0;
  const editable =
    ["DRAFT", "CONFIRMED", "PREPARING"].includes(order.status) && order.payment_status === "UNPAID" && can("orders:create");
  const transitions = order.allowed_transitions.filter((s) => s !== "CANCELLED");
  const canCancel = order.allowed_transitions.includes("CANCELLED");

  const timeline: [string, string | null][] = [
    ["Created", order.created_at],
    ["Confirmed", order.confirmed_at],
    ["Preparing", order.preparing_at],
    ["Ready", order.ready_at],
    ["Completed", order.completed_at],
    ["Paid", order.paid_at],
    ["Cancelled", order.cancelled_at],
  ];

  return (
    <>
      <PageHeader
        title={`Order #${order.display_number}`}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <OrderStatusBadge status={order.status} />
            <PaymentStatusBadge status={order.payment_status} />
            <span>{order.table_name ? `Table ${order.table_name}` : "Takeaway"}</span>
            {order.customer_name ? <span>· {order.customer_name}</span> : null}
          </span>
        }
        actions={
          <>
            {editable ? (
              <Button variant="outline" asChild>
                <Link href={`/pos?order=${order.id}`}>
                  <Pencil /> Edit items
                </Link>
              </Button>
            ) : null}
            {transitions.map((status) => {
              const spec = NEXT_LABEL[status];
              if (!spec) return null;
              const Icon = spec.icon;
              return (
                <Button key={status} variant="secondary" onClick={() => transition.mutate(status)} disabled={transition.isPending}>
                  <Icon /> {spec.label}
                </Button>
              );
            })}
            {payable && can("payments:record") ? (
              <Button onClick={() => setPaying(true)}>
                <Wallet /> Take payment · {formatMoney(order.balance_due_minor)}
              </Button>
            ) : null}
            <Button variant="outline" asChild>
              <a href={`/receipts/${order.id}`} target="_blank" rel="noopener">
                <Printer /> Receipt
              </a>
            </Button>
            {canCancel ? (
              <Button variant="destructive" onClick={() => setCancelling(true)}>
                <Ban /> Cancel order
              </Button>
            ) : null}
          </>
        }
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Items</CardTitle>
            {order.notes ? <CardDescription>Note: {order.notes}</CardDescription> : null}
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Item</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Unit</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {order.items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <p className="font-medium">{item.product_name}</p>
                      {item.modifiers.length ? (
                        <p className="text-xs text-muted-foreground">
                          {item.modifiers.map((m) => `${m.option_name}${m.price_delta_minor ? ` (+${formatMoney(m.price_delta_minor)})` : ""}`).join(", ")}
                        </p>
                      ) : null}
                      {item.notes ? <p className="text-xs text-muted-foreground italic">“{item.notes}”</p> : null}
                    </TableCell>
                    <TableCell className="text-right tabular">{item.quantity}</TableCell>
                    <TableCell className="text-right tabular">{formatMoney(item.unit_price_minor)}</TableCell>
                    <TableCell className="text-right tabular">{formatMoney(item.line_total_minor)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <dl className="mt-4 ml-auto grid max-w-sm gap-1 text-sm">
              <Row label="Subtotal" value={order.subtotal_minor} />
              {order.discount_minor ? <Row label={`Discount · ${order.discount_name ?? ""}`} value={-order.discount_minor} /> : null}
              {order.loyalty_discount_minor ? (
                <Row label={`Loyalty (${order.loyalty_points_redeemed} pts)`} value={-order.loyalty_discount_minor} />
              ) : null}
              {order.service_charge_minor ? (
                <Row label={`Service charge ${formatPercentBps(order.service_charge_bps)}`} value={order.service_charge_minor} />
              ) : null}
              <Row
                label={`VAT ${formatPercentBps(order.tax_rate_bps)}${order.prices_include_tax ? " (included)" : ""}`}
                value={order.tax_minor}
                muted={order.prices_include_tax}
              />
              <div className="flex justify-between border-t pt-2 text-base font-semibold">
                <dt>Total</dt>
                <dd className="tabular">{formatMoney(order.total_minor)}</dd>
              </div>
              <Row label="Paid" value={order.amount_paid_minor} />
              {order.amount_refunded_minor ? <Row label="Refunded" value={-order.amount_refunded_minor} /> : null}
              {order.balance_due_minor ? <Row label="Balance due" value={order.balance_due_minor} strong /> : null}
            </dl>
          </CardContent>
        </Card>
        <div className="grid content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="grid gap-2 text-sm">
                {timeline
                  .filter(([, at]) => at)
                  .map(([label, at]) => (
                    <li key={label} className="flex justify-between gap-2">
                      <span>{label}</span>
                      <span className="text-muted-foreground">{formatDateTime(at)}</span>
                    </li>
                  ))}
              </ol>
              {order.cancel_reason ? <p className="mt-3 text-sm text-muted-foreground">Reason: {order.cancel_reason}</p> : null}
              {order.created_by_name ? <p className="mt-3 text-xs text-muted-foreground">Created by {order.created_by_name}</p> : null}
              <p className="mt-1 text-xs text-muted-foreground">
                Stock {order.stock_committed ? "deducted at confirmation" : "not yet deducted"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Payments</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              {order.payments.length ? (
                order.payments.map((p) => (
                  <div key={p.id} className="rounded-lg border p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{p.method_name}</span>
                      <span className="font-semibold tabular">{formatMoney(p.amount_minor)}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {formatDateTime(p.created_at)}
                      {p.change_minor ? ` · change ${formatMoney(p.change_minor)}` : ""}
                      {p.reference ? ` · ref ${p.reference}` : ""}
                    </p>
                    {p.is_simulated ? (
                      <Badge variant="outline" className="mt-2">
                        <Info aria-hidden /> Simulated · recorded by staff
                      </Badge>
                    ) : null}
                    {p.refunded_minor ? (
                      <p className="mt-1 text-xs text-status-critical">Refunded {formatMoney(p.refunded_minor)}</p>
                    ) : null}
                    {can("refunds:record") && ["PAID", "PARTIALLY_REFUNDED"].includes(order.payment_status) && p.refunded_minor < p.amount_minor ? (
                      <Button variant="outline" size="sm" className="mt-2" onClick={() => setRefunding(p)}>
                        <Undo2 /> Refund
                      </Button>
                    ) : null}
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No payments recorded.</p>
              )}
              {order.refunds.map((r) => (
                <p key={r.id} className="text-xs text-muted-foreground">
                  Refund {formatMoney(r.amount_minor)} · {r.reason} · {formatDateTime(r.created_at)}
                </p>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
      {paying ? <PaymentDialog key={order.id + order.amount_paid_minor} order={order} open onOpenChange={setPaying} /> : null}
      {cancelling ? <CancelDialog order={order} onClose={() => setCancelling(false)} /> : null}
      {refunding ? <RefundDialog order={order} payment={refunding} onClose={() => setRefunding(null)} /> : null}
    </>
  );
}

function Row({ label, value, muted, strong }: { label: string; value: number; muted?: boolean; strong?: boolean }) {
  return (
    <div className={`flex justify-between ${strong ? "font-semibold" : "text-muted-foreground"}`}>
      <dt>{label}</dt>
      <dd className="tabular">{muted ? `(${formatMoney(value)})` : formatMoney(value)}</dd>
    </div>
  );
}

function CancelDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  const { can } = useAuth();
  const [reason, setReason] = useState("");
  const defaultRestock = order.status === "DRAFT" || order.status === "CONFIRMED";
  const [restock, setRestock] = useState(defaultRestock);
  const cancel = useApiMutation(
    () =>
      api(`/orders/${order.id}/cancel`, {
        method: "POST",
        body: { reason, restock_inventory: can("orders:cancel") ? restock : undefined },
      }),
    { invalidate: INVALIDATE, success: "Order cancelled" },
  );
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Cancel order #${order.display_number}?`}
      description="This cannot be undone. Orders with payments must be refunded first."
      confirmLabel="Cancel order"
      destructive
      onConfirm={() => {
        if (reason.trim().length < 3) throw new Error("reason");
        return cancel.mutateAsync(undefined);
      }}
    >
      <div className="grid gap-3">
        <FormField label="Reason" htmlFor="cancel-reason" hint="At least 3 characters.">
          <Textarea id="cancel-reason" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
        </FormField>
        {order.stock_committed && can("orders:cancel") ? (
          <Label className="font-normal">
            <Checkbox checked={restock} onCheckedChange={(v) => setRestock(v === true)} />
            Return deducted ingredients to stock
            {!defaultRestock ? <span className="text-xs text-muted-foreground">(preparation had started)</span> : null}
          </Label>
        ) : null}
      </div>
    </ConfirmDialog>
  );
}

function RefundDialog({ order, payment, onClose }: { order: Order; payment: Payment; onClose: () => void }) {
  const refundable = payment.amount_minor - payment.refunded_minor;
  const [amount, setAmount] = useState(minorToInput(refundable));
  const [reason, setReason] = useState("");
  const [key] = useState(() => newIdempotencyKey("refund"));
  const amountMinor = parseMoney(amount);
  const refund = useApiMutation(
    () =>
      api<Order>(`/orders/${order.id}/refunds`, {
        method: "POST",
        idempotencyKey: key,
        body: { payment_id: payment.id, amount_minor: amountMinor, reason },
      }),
    { invalidate: INVALIDATE, success: "Refund recorded", onSuccess: onClose },
  );
  const valid = amountMinor !== null && amountMinor > 0 && amountMinor <= refundable && reason.trim().length >= 3;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Refund {payment.method_name}</DialogTitle>
          <DialogDescription>
            Up to {formatMoney(refundable)} can be refunded. Return the money to the customer yourself; SmartPOS records
            the refund. Refunds do not return food to stock.
          </DialogDescription>
        </DialogHeader>
        <FormField label="Amount (฿)" htmlFor="refund-amount">
          <Input id="refund-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </FormField>
        <FormField label="Reason" htmlFor="refund-reason">
          <Textarea id="refund-reason" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
        </FormField>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="destructive" disabled={!valid || refund.isPending} onClick={() => refund.mutate(undefined)}>
            Record refund
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

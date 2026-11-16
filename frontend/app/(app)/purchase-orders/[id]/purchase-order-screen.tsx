"use client";

import { AlertTriangle, ArrowLeft, Ban, PackageCheck, Pencil, Send } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { QueryState } from "@/components/shared/query-state";
import { PurchaseOrderStatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { PurchaseOrderEditor } from "@/features/purchasing/po-editor";
import { priceDeviation, unitFactor } from "@/features/purchasing/units";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { newIdempotencyKey } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { bahtToMinorString, formatDate, formatDateTime, formatMoney, formatNumber, formatQty, formatUnitCost } from "@/lib/format";
import type { Ingredient, PurchaseOrder } from "@/types/api";

const INVALIDATE = ["purchase-order", "purchase-orders", "ingredients", "inventory", "movements", "suppliers", "recommendations"];
const OPEN = ["SUBMITTED", "PARTIALLY_RECEIVED"];

export function PurchaseOrderScreen() {
  const { id } = useParams<{ id: string }>();
  const query = useApi<PurchaseOrder>(["purchase-order", id], `/purchase-orders/${id}`);
  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
        <Link href="/purchase-orders">
          <ArrowLeft /> Purchase orders
        </Link>
      </Button>
      <QueryState query={query}>{(po) => <PurchaseOrderDetail po={po} />}</QueryState>
    </>
  );
}

function PurchaseOrderDetail({ po }: { po: PurchaseOrder }) {
  const { can } = useAuth();
  const writable = can("purchasing:write");
  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [receiving, setReceiving] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");

  const submit = useApiMutation(() => api<PurchaseOrder>(`/purchase-orders/${po.id}/submit`, { method: "POST" }), {
    invalidate: INVALIDATE,
    success: "Purchase order submitted",
  });
  const cancel = useApiMutation(
    () => api<PurchaseOrder>(`/purchase-orders/${po.id}/cancel`, { method: "POST", body: { reason: reason.trim() } }),
    { invalidate: INVALIDATE, success: "Purchase order cancelled", onSuccess: () => setCancelling(false) },
  );

  if (editing) {
    return <PurchaseOrderEditor initial={po} onSaved={() => setEditing(false)} onCancel={() => setEditing(false)} />;
  }

  const timeline: [string, string | null][] = [
    ["Created", po.created_at],
    ["Submitted", po.submitted_at],
    ["Fully received", po.received_at],
    ["Cancelled", po.cancelled_at],
  ];

  return (
    <>
      <PageHeader
        title={po.display_number}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <PurchaseOrderStatusBadge status={po.status} /> {po.supplier_name}
            {po.expected_delivery_date ? ` · expected ${formatDate(po.expected_delivery_date)}` : null}
          </span>
        }
        actions={
          writable ? (
            <>
              {po.status === "DRAFT" ? (
                <>
                  <Button variant="outline" onClick={() => setEditing(true)}>
                    <Pencil /> Edit
                  </Button>
                  <Button onClick={() => setSubmitting(true)}>
                    <Send /> Submit
                  </Button>
                </>
              ) : null}
              {OPEN.includes(po.status) ? (
                <Button onClick={() => setReceiving(true)}>
                  <PackageCheck /> Receive delivery
                </Button>
              ) : null}
              {po.status !== "RECEIVED" && po.status !== "CANCELLED" ? (
                <Button variant="outline" onClick={() => setCancelling(true)}>
                  <Ban /> Cancel
                </Button>
              ) : null}
            </>
          ) : null
        }
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="grid content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Lines</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ingredient</TableHead>
                    <TableHead className="text-right">Ordered</TableHead>
                    <TableHead className="text-right">Received</TableHead>
                    <TableHead className="text-right">Outstanding</TableHead>
                    <TableHead className="text-right">Price</TableHead>
                    <TableHead className="text-right">Line total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {po.items.map((i) => (
                    <TableRow key={i.id}>
                      <TableCell>
                        <p className="font-medium">{i.ingredient_name}</p>
                        {i.input_unit !== i.base_unit ? (
                          <p className="text-xs text-muted-foreground">
                            Ordered as {formatQty(i.input_quantity)} {i.input_unit}
                          </p>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-right tabular">{formatQty(i.quantity_ordered, i.base_unit)}</TableCell>
                      <TableCell className="text-right tabular">{formatQty(i.quantity_received, i.base_unit)}</TableCell>
                      <TableCell className="text-right tabular">
                        {po.status === "CANCELLED" ? "—" : formatQty(i.quantity_remaining, i.base_unit)}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground tabular">
                        {i.unit_cost_minor ? formatUnitCost(i.unit_cost_minor, i.base_unit) : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular">{formatMoney(i.line_total_minor)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                <TableFooter>
                  <TableRow>
                    <TableCell colSpan={5}>Estimated total</TableCell>
                    <TableCell className="text-right tabular">{formatMoney(po.estimated_total_minor)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={5}>Received value</TableCell>
                    <TableCell className="text-right tabular">{formatMoney(po.received_total_minor)}</TableCell>
                  </TableRow>
                </TableFooter>
              </Table>
            </CardContent>
          </Card>
          {po.receipts.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Deliveries</CardTitle>
                <CardDescription>Each delivery added stock as a RECEIPT movement.</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="grid gap-2 text-sm">
                  {po.receipts.map((r) => (
                    <li key={r.id} className="rounded-md border px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium">{formatDateTime(r.created_at)}</span>
                        <span className="tabular">{formatMoney(r.total_cost_minor)}</span>
                      </div>
                      <p className="text-muted-foreground">
                        {r.lines
                          .map((l) => {
                            const item = po.items.find((i) => i.id === l.purchase_order_item_id);
                            return `${item?.ingredient_name ?? "Item"} ${formatQty(l.quantity, item?.base_unit)}`;
                          })
                          .join(", ")}
                      </p>
                      {r.notes ? <p className="mt-1 text-xs text-muted-foreground">{r.notes}</p> : null}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>
        <Card className="content-start">
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <ol className="grid gap-2">
              {timeline
                .filter(([, at]) => at)
                .map(([label, at]) => (
                  <li key={label} className="flex justify-between gap-2">
                    <span>{label}</span>
                    <span className="text-muted-foreground">{formatDateTime(at)}</span>
                  </li>
                ))}
            </ol>
            {po.cancel_reason ? <p className="text-muted-foreground">Reason: {po.cancel_reason}</p> : null}
            {po.notes ? (
              <div>
                <p className="font-medium">Notes</p>
                <p className="whitespace-pre-line text-muted-foreground">{po.notes}</p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={submitting}
        onOpenChange={setSubmitting}
        title={`Submit ${po.display_number}?`}
        description={`This marks the order as sent to ${po.supplier_name}. SmartPOS does not transmit orders or payments to suppliers; send it through your usual channel. Lines can no longer be edited.`}
        confirmLabel="Submit"
        onConfirm={() => submit.mutateAsync(undefined)}
      />
      <ConfirmDialog
        open={cancelling}
        onOpenChange={setCancelling}
        title={`Cancel ${po.display_number}?`}
        description={po.receipts.length ? "Stock already received stays in inventory; only the outstanding quantities are cancelled." : undefined}
        confirmLabel="Cancel purchase order"
        destructive
        confirmDisabled={reason.trim().length < 3}
        onConfirm={() => cancel.mutateAsync(undefined)}
      >
        <FormField label="Reason (required)" htmlFor="po-cancel-reason">
          <Textarea id="po-cancel-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </ConfirmDialog>
      {receiving ? <ReceiveDialog po={po} onClose={() => setReceiving(false)} /> : null}
    </>
  );
}

interface ReceiveRow {
  item_id: string;
  quantity: string;
  unit: string;
  price: string;
}

function ReceiveDialog({ po, onClose }: { po: PurchaseOrder; onClose: () => void }) {
  const ingredients = useApi<Ingredient[]>(["ingredients"], "/ingredients");
  // One key per dialog: retries and double clicks replay instead of double-receiving.
  const [idempotencyKey] = useState(newIdempotencyKey);
  const outstanding = po.items.filter((i) => i.quantity_remaining > 0);
  const [rows, setRows] = useState<ReceiveRow[]>(() =>
    outstanding.map((i) => ({ item_id: i.id, quantity: String(i.quantity_remaining), unit: i.base_unit ?? "", price: "" })),
  );
  const [notes, setNotes] = useState("");
  const update = (id: string, patch: Partial<ReceiveRow>) => setRows((rs) => rs.map((r) => (r.item_id === id ? { ...r, ...patch } : r)));
  const lines = rows.filter((r) => Number(r.quantity) > 0);
  const invalid = rows.some(
    (r) => (r.quantity.trim() !== "" && !(Number(r.quantity) >= 0)) || (r.price.trim() !== "" && bahtToMinorString(r.price) === null),
  );

  const receive = useApiMutation(
    () =>
      api<PurchaseOrder>(`/purchase-orders/${po.id}/receive`, {
        method: "POST",
        idempotencyKey,
        body: {
          notes: notes.trim() || null,
          lines: lines.map((r) => ({
            item_id: r.item_id,
            quantity: r.quantity,
            unit: r.unit || undefined,
            unit_cost_minor: r.price.trim() ? bahtToMinorString(r.price) : null,
          })),
        },
      }),
    { invalidate: INVALIDATE, success: (p) => `Delivery recorded · ${p.display_number} is ${p.status === "RECEIVED" ? "fully received" : "partially received"}`, onSuccess: onClose },
  );

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Receive delivery · {po.display_number}</DialogTitle>
          <DialogDescription>
            Enter what actually arrived. Leave a line at 0 if it did not come; it stays outstanding. Leave price blank to use the ordered price.
          </DialogDescription>
        </DialogHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ingredient</TableHead>
              <TableHead className="text-right">Outstanding</TableHead>
              <TableHead className="w-28">Received</TableHead>
              <TableHead className="w-24">Unit</TableHead>
              <TableHead className="w-32">Actual price / unit (฿)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {outstanding.map((item) => {
              const row = rows.find((r) => r.item_id === item.id);
              const ingredient = ingredients.data?.find((i) => i.id === item.ingredient_id);
              if (!row) return null;
              return (
                <TableRow key={item.id}>
                  <TableCell>{item.ingredient_name}</TableCell>
                  <TableCell className="text-right tabular">{formatQty(item.quantity_remaining, item.base_unit)}</TableCell>
                  <TableCell>
                    <Input aria-label={`Received ${item.ingredient_name}`} inputMode="decimal" value={row.quantity} onChange={(e) => update(item.id, { quantity: e.target.value })} />
                  </TableCell>
                  <TableCell>
                    <NativeSelect aria-label="Unit" value={row.unit} onChange={(e) => update(item.id, { unit: e.target.value })}>
                      {(ingredient?.allowed_units ?? [row.unit]).map((u) => (
                        <option key={u} value={u}>
                          {u}
                        </option>
                      ))}
                    </NativeSelect>
                  </TableCell>
                  <TableCell>
                    <Input aria-label={`Price for ${item.ingredient_name}`} inputMode="decimal" placeholder="As ordered" value={row.price} onChange={(e) => update(item.id, { price: e.target.value })} />
                    <PriceDeviation ingredient={ingredient} row={row} orderedPerBaseMinor={item.unit_cost_minor} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <FormField label="Delivery notes" htmlFor="rcv-notes">
          <Textarea id="rcv-notes" rows={2} placeholder="Invoice number, condition, short delivery…" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </FormField>
        {invalid ? <p className="text-sm text-status-critical">Check the quantities and prices.</p> : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!lines.length || invalid || receive.isPending} onClick={() => receive.mutate(undefined)}>
            <PackageCheck /> Record delivery
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Flags typed prices far from the ordered price, e.g. a per-kg price typed into a per-gram field. */
function PriceDeviation({ ingredient, row, orderedPerBaseMinor }: { ingredient?: Ingredient; row: ReceiveRow; orderedPerBaseMinor: number }) {
  const typed = row.price.trim() ? bahtToMinorString(row.price) : null;
  const factor = ingredient ? unitFactor(ingredient, row.unit) : null;
  if (typed === null || factor === null) return null;
  const ratio = priceDeviation(Number(typed), orderedPerBaseMinor * factor);
  if (ratio === null) return null;
  return (
    <p role="alert" className="mt-1 flex items-center gap-1 text-xs">
      <AlertTriangle className="size-3 shrink-0 text-status-warning" aria-hidden />
      {ratio >= 1 ? `${formatNumber(ratio, 1)}× the ordered price` : `${formatNumber(1 / ratio, 1)}× below the ordered price`}: check the unit
    </p>
  );
}

"use client";

import { ArrowLeft, Gift, Heart, Pencil, UserX } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { QueryState } from "@/components/shared/query-state";
import { StatCard } from "@/components/shared/stat-card";
import { OrderStatusBadge, PaymentStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CustomerDialog } from "@/features/customers/customer-dialog";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime, formatMoney, formatRelativeTime } from "@/lib/format";
import type { Customer, CustomerFavourite, LoyaltyTransaction, OrderListItem, Page } from "@/types/api";

export function CustomerScreen() {
  const { id } = useParams<{ id: string }>();
  const query = useApi<Customer>(["customer", id], `/customers/${id}`);
  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
        <Link href="/customers">
          <ArrowLeft /> Customers
        </Link>
      </Button>
      <QueryState query={query}>{(customer) => <CustomerDetail customer={customer} />}</QueryState>
    </>
  );
}

function CustomerDetail({ customer }: { customer: Customer }) {
  const { can } = useAuth();
  const [editing, setEditing] = useState(false);
  const [adjusting, setAdjusting] = useState(false);
  const [anonymising, setAnonymising] = useState(false);
  const orders = useApi<Page<OrderListItem>>(["customer", customer.id, "orders"], `/customers/${customer.id}/orders`, {
    page_size: 20,
  });
  const ledger = useApi<Page<LoyaltyTransaction>>(["customer", customer.id, "loyalty"], `/loyalty/customers/${customer.id}/transactions`, {
    page_size: 30,
  });
  const anonymise = useApiMutation(() => api(`/customers/${customer.id}/anonymise`, { method: "POST" }), {
    invalidate: ["customer", "customers"],
    success: "Personal data erased",
  });

  return (
    <>
      <PageHeader
        title={customer.name}
        description={[customer.phone, customer.email].filter(Boolean).join(" · ") || "No contact details"}
        actions={
          <>
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil /> Edit
            </Button>
            {can("loyalty:adjust") ? (
              <Button variant="outline" onClick={() => setAdjusting(true)}>
                <Gift /> Adjust points
              </Button>
            ) : null}
            <Button variant="ghost" onClick={() => setAnonymising(true)}>
              <UserX /> Erase personal data
            </Button>
          </>
        }
      />
      <div className="mb-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Loyalty balance" value={`${customer.loyalty_balance} pts`} />
        <StatCard label="Paid orders" value={customer.order_count} />
        <StatCard label="Total spent" value={formatMoney(customer.total_spent_minor)} hint="Paid orders minus refunds" />
        <StatCard label="Customer since" value={formatDate(customer.created_at)} hint={customer.last_order_at ? `Last order ${formatDate(customer.last_order_at)}` : undefined} />
      </div>
      <Favourites customerId={customer.id} />
      {customer.notes ? (
        <Card className="mb-4">
          <CardContent className="text-sm">
            <span className="font-medium">Notes: </span>
            {customer.notes}
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Order history</CardTitle>
          </CardHeader>
          <CardContent>
            <QueryState query={orders}>
              {(data) =>
                data.items.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Order</TableHead>
                        <TableHead>Date</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Total</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.items.map((o) => (
                        <TableRow key={o.id}>
                          <TableCell>
                            <Link href={`/orders/${o.id}`} className="text-primary hover:underline">
                              #{o.display_number}
                            </Link>
                          </TableCell>
                          <TableCell className="text-muted-foreground">{formatDateTime(o.created_at)}</TableCell>
                          <TableCell className="space-x-1">
                            <OrderStatusBadge status={o.status} />
                            <PaymentStatusBadge status={o.payment_status} />
                          </TableCell>
                          <TableCell className="text-right tabular">{formatMoney(o.total_minor)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-sm text-muted-foreground">No orders yet.</p>
                )
              }
            </QueryState>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Loyalty ledger</CardTitle>
          </CardHeader>
          <CardContent>
            <QueryState query={ledger}>
              {(data) =>
                data.items.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Reason</TableHead>
                        <TableHead className="text-right">Points</TableHead>
                        <TableHead className="text-right">Balance</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.items.map((tx) => (
                        <TableRow key={tx.id}>
                          <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(tx.created_at)}</TableCell>
                          <TableCell>
                            <Badge variant={tx.points > 0 ? "success" : "outline"}>{tx.transaction_type.toLowerCase()}</Badge>
                          </TableCell>
                          <TableCell className="max-w-48 truncate text-muted-foreground" title={tx.reason ?? ""}>
                            {tx.reason}
                          </TableCell>
                          <TableCell className="text-right font-medium tabular">
                            {tx.points > 0 ? "+" : ""}
                            {tx.points}
                          </TableCell>
                          <TableCell className="text-right tabular">{tx.balance_after}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-sm text-muted-foreground">No loyalty activity yet.</p>
                )
              }
            </QueryState>
          </CardContent>
        </Card>
      </div>
      {editing ? <CustomerDialog customer={customer} onClose={() => setEditing(false)} /> : null}
      {adjusting ? <AdjustDialog customerId={customer.id} onClose={() => setAdjusting(false)} /> : null}
      <ConfirmDialog
        open={anonymising}
        onOpenChange={setAnonymising}
        title="Erase this customer's personal data?"
        description="Name, phone, email and notes are removed. Orders and the loyalty ledger are kept so accounts stay correct. This cannot be undone."
        confirmLabel="Erase data"
        destructive
        onConfirm={() => anonymise.mutateAsync(undefined)}
      />
    </>
  );
}

function AdjustDialog({ customerId, onClose }: { customerId: string; onClose: () => void }) {
  const [points, setPoints] = useState("");
  const [reason, setReason] = useState("");
  const adjust = useApiMutation(
    () => api(`/loyalty/customers/${customerId}/adjust`, { method: "POST", body: { points: Number(points), reason } }),
    { invalidate: ["customer", "customers"], success: "Points adjusted", onSuccess: onClose },
  );
  const valid = Number.isInteger(Number(points)) && Number(points) !== 0 && reason.trim().length >= 3;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Adjust loyalty points</DialogTitle>
          <DialogDescription>Use a negative number to remove points. Every adjustment is recorded in the ledger and audit log.</DialogDescription>
        </DialogHeader>
        <FormField label="Points" htmlFor="adj-points">
          <Input id="adj-points" type="number" step={1} value={points} onChange={(e) => setPoints(e.target.value)} />
        </FormField>
        <FormField label="Reason" htmlFor="adj-reason">
          <Input id="adj-reason" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!valid || adjust.isPending} onClick={() => adjust.mutate(undefined)}>
            Save adjustment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** What this customer orders most, from their paid orders. */
function Favourites({ customerId }: { customerId: string }) {
  const query = useApi<CustomerFavourite[]>(["customer", customerId, "favourites"], `/customers/${customerId}/favourites`);
  if (!query.data?.length) return null;
  const top = query.data[0].orders;
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Heart className="size-4 text-primary" aria-hidden /> Favourite items
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {query.data.map((f) => (
            <li key={f.product_id} className="grid gap-1.5 rounded-lg border p-3">
              <p className="truncate text-sm font-medium" title={f.product_name}>
                {f.product_name.split(" (")[0]}
              </p>
              <div className="h-1.5 rounded-full bg-muted" aria-hidden>
                <div className="h-full rounded-full bg-primary" style={{ width: `${(f.orders / top) * 100}%` }} />
              </div>
              <p className="text-xs text-muted-foreground">
                {f.orders} {f.orders === 1 ? "order" : "orders"} · {f.quantity} total · last {formatRelativeTime(f.last_ordered_at)}
              </p>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

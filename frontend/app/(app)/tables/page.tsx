"use client";

import { DoorOpen, Eye, LayoutGrid, Pencil, Plus, ShoppingCart, Sparkles, Trash2, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { PageHeader } from "@/components/shared/page-header";
import { QueryState } from "@/components/shared/query-state";
import { OrderStatusBadge, PaymentStatusBadge, TableStatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { api, useApi, useApiMutation } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatMoney, minutesSince } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useLiveRefetchInterval } from "@/lib/realtime";
import { cn } from "@/lib/utils";
import type { DiningTable, TableStatus } from "@/types/api";

const BORDER: Record<TableStatus, string> = {
  AVAILABLE: "border-status-good/40",
  OCCUPIED: "border-series-1/50",
  RESERVED: "border-status-warning/60",
  CLEANING: "border-border",
};

export default function TablesPage() {
  const { t } = useI18n();
  const { can } = useAuth();
  const refetchInterval = useLiveRefetchInterval(15_000);
  const query = useApi<DiningTable[]>(["tables"], "/tables", undefined, { refetchInterval });
  const [editing, setEditing] = useState<DiningTable | "new" | null>(null);
  const [deleting, setDeleting] = useState<DiningTable | null>(null);
  const remove = useApiMutation((table: DiningTable) => api<{ message: string }>(`/tables/${table.id}`, { method: "DELETE" }), {
    invalidate: ["tables"],
    success: (r) => r.message,
  });

  return (
    <>
      <PageHeader
        title={t("Tables")}
        description="Floor overview. Start a dine-in order on a free table; close a table once its orders are paid."
        actions={
          can("tables:write") ? (
            <Button onClick={() => setEditing("new")}>
              <Plus /> Add table
            </Button>
          ) : null
        }
      />
      <QueryState query={query}>
        {(tables) => {
          if (!tables.length) {
            return (
              <EmptyState
                icon={LayoutGrid}
                title="No tables yet"
                description="Add your dining tables to take dine-in orders."
                action={can("tables:write") ? <Button onClick={() => setEditing("new")}>Add table</Button> : undefined}
              />
            );
          }
          const counts = tables.reduce<Record<string, number>>((acc, tbl) => ({ ...acc, [tbl.status]: (acc[tbl.status] ?? 0) + 1 }), {});
          const zones = [...new Set(tables.map((tbl) => tbl.zone ?? "Main floor"))];
          return (
            <div className="grid gap-6">
              <div className="flex flex-wrap gap-2 text-sm">
                {(["AVAILABLE", "OCCUPIED", "RESERVED", "CLEANING"] as TableStatus[]).map((s) => (
                  <span key={s} className="flex items-center gap-2 rounded-lg border bg-card px-3 py-1.5">
                    <TableStatusBadge status={s} />
                    <span className="font-semibold tabular">{counts[s] ?? 0}</span>
                  </span>
                ))}
              </div>
              {zones.map((zone) => (
                <section key={zone} aria-label={zone}>
                  <h2 className="mb-3 text-sm font-medium text-muted-foreground">{zone}</h2>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                    {tables
                      .filter((tbl) => (tbl.zone ?? "Main floor") === zone)
                      .map((table) => (
                        <TableCard key={table.id} table={table} onEdit={() => setEditing(table)} onDelete={() => setDeleting(table)} />
                      ))}
                  </div>
                </section>
              ))}
            </div>
          );
        }}
      </QueryState>
      {editing ? <TableDialog table={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && setDeleting(null)}
          title={`Remove table ${deleting.name}?`}
          description="Tables with order history are deactivated instead of deleted, so past orders stay intact."
          confirmLabel="Remove"
          destructive
          onConfirm={() => remove.mutateAsync(deleting)}
        />
      ) : null}
    </>
  );
}

function TableCard({ table, onEdit, onDelete }: { table: DiningTable; onEdit: () => void; onDelete: () => void }) {
  const { can } = useAuth();
  const { t } = useI18n();
  const setStatus = useApiMutation(
    (status: TableStatus) => api<DiningTable>(`/tables/${table.id}/status`, { method: "POST", body: { status } }),
    { invalidate: ["tables"], success: (tbl) => `Table ${tbl.name}: ${tbl.status.toLowerCase()}` },
  );
  const close = useApiMutation(() => api<DiningTable>(`/tables/${table.id}/close`, { method: "POST" }), {
    invalidate: ["tables"],
    success: `Table ${table.name} closed — mark it available after cleaning`,
  });
  const order = table.current_order;
  const editable = order && ["DRAFT", "CONFIRMED", "PREPARING"].includes(order.status) && order.payment_status === "UNPAID";

  return (
    <Card className={cn("gap-3 border-2 py-4", BORDER[table.status])}>
      <div className="flex items-start justify-between gap-2 px-4">
        <div>
          <p className="text-lg font-semibold">{table.name}</p>
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <Users className="size-3.5" aria-hidden /> {table.capacity} seats
          </p>
        </div>
        <div className="flex items-center gap-1">
          <TableStatusBadge status={table.status} />
          {can("tables:write") ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={`Edit table ${table.name}`}>
                  <Pencil />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={onEdit}>
                  <Pencil /> Edit
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={onDelete} disabled={table.status === "OCCUPIED"}>
                  <Trash2 /> Remove
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>
      <CardContent className="grid gap-3 px-4">
        {order ? (
          <Link href={`/orders/${order.id}`} className="rounded-lg border bg-muted/40 p-3 text-sm hover:bg-muted">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">#{order.display_number}</span>
              <span className="font-semibold tabular">{formatMoney(order.total_minor)}</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <OrderStatusBadge status={order.status} />
              <PaymentStatusBadge status={order.payment_status} />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {order.item_count} items · seated {minutesSince(order.created_at)} min
            </p>
          </Link>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {(table.status === "AVAILABLE" || table.status === "RESERVED") && can("orders:create") ? (
            <Button size="sm" asChild>
              <Link href={`/pos?table=${table.id}`}>
                <ShoppingCart /> Start order
              </Link>
            </Button>
          ) : null}
          {editable && can("orders:create") ? (
            <Button size="sm" variant="secondary" asChild>
              <Link href={`/pos?order=${order.id}`}>
                <Plus /> Add items
              </Link>
            </Button>
          ) : null}
          {order ? (
            <Button size="sm" variant="outline" asChild>
              <Link href={`/orders/${order.id}`}>
                <Eye /> Order
              </Link>
            </Button>
          ) : null}
          {can("tables:operate") ? (
            <>
              {table.status === "OCCUPIED" ? (
                <Button size="sm" variant="outline" onClick={() => close.mutate(undefined)} disabled={close.isPending}>
                  <DoorOpen /> Close table
                </Button>
              ) : null}
              {table.status === "AVAILABLE" ? (
                <Button size="sm" variant="ghost" onClick={() => setStatus.mutate("RESERVED")}>
                  {t("Reserved")}
                </Button>
              ) : null}
              {table.status === "RESERVED" ? (
                <Button size="sm" variant="ghost" onClick={() => setStatus.mutate("AVAILABLE")}>
                  Free table
                </Button>
              ) : null}
              {table.status === "CLEANING" ? (
                <Button size="sm" variant="secondary" onClick={() => setStatus.mutate("AVAILABLE")}>
                  <Sparkles /> Mark cleaned
                </Button>
              ) : null}
            </>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function TableDialog({ table, onClose }: { table: DiningTable | null; onClose: () => void }) {
  const [name, setName] = useState(table?.name ?? "");
  const [capacity, setCapacity] = useState(String(table?.capacity ?? 4));
  const [zone, setZone] = useState(table?.zone ?? "");
  const save = useApiMutation(
    () =>
      api<DiningTable>(table ? `/tables/${table.id}` : "/tables", {
        method: table ? "PATCH" : "POST",
        body: { name: name.trim(), capacity: Number(capacity), zone: zone.trim() || null },
      }),
    { invalidate: ["tables"], success: table ? "Table updated" : "Table added", onSuccess: onClose },
  );
  const valid = name.trim() && Number(capacity) >= 1 && Number(capacity) <= 100;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{table ? `Edit table ${table.name}` : "Add table"}</DialogTitle>
        </DialogHeader>
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          <FormField label="Name or number" htmlFor="table-name">
            <Input id="table-name" required maxLength={50} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </FormField>
          <FormField label="Seats" htmlFor="table-capacity">
            <Input id="table-capacity" type="number" min={1} max={100} value={capacity} onChange={(e) => setCapacity(e.target.value)} />
          </FormField>
          <FormField label="Zone (optional)" htmlFor="table-zone" hint="e.g. Indoor, Terrace">
            <Input id="table-zone" maxLength={50} value={zone} onChange={(e) => setZone(e.target.value)} />
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || save.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

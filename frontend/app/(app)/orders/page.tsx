"use client";

import { ReceiptText, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { DateRangeFilter, rangeForPreset, type DateRange } from "@/components/shared/date-range-filter";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { QueryState } from "@/components/shared/query-state";
import { OrderStatusBadge, PaymentStatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { OrderListItem, Page } from "@/types/api";

const STATUSES = ["DRAFT", "CONFIRMED", "PREPARING", "READY", "COMPLETED", "CANCELLED"];
const PAYMENTS = ["UNPAID", "PARTIALLY_PAID", "PAID", "PARTIALLY_REFUNDED", "REFUNDED"];

function startOfDayIso(date: string) {
  // Orders are filtered by creation time; interpret dates in Bangkok time.
  return new Date(`${date}T00:00:00+07:00`).toISOString();
}

export default function OrdersPage() {
  const { t } = useI18n();
  const { can } = useAuth();
  const [range, setRange] = useState<DateRange>(() => rangeForPreset("7d"));
  const [status, setStatus] = useState("");
  const [payment, setPayment] = useState("");
  const [type, setType] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const endExclusive = new Date(new Date(`${range.end}T00:00:00+07:00`).getTime() + 86400000).toISOString();
  const query = useApi<Page<OrderListItem>>(["orders", "list"], "/orders", {
    status: status || undefined,
    payment_status: payment || undefined,
    order_type: type || undefined,
    start: startOfDayIso(range.start),
    end: endExclusive,
    search: search.trim() || undefined,
    page,
    page_size: 25,
  });
  const reset = (fn: () => void) => {
    fn();
    setPage(1);
  };

  return (
    <>
      <PageHeader
        title={t("Orders")}
        description="Order history with status, payment and totals."
        actions={
          can("orders:create") ? (
            <Button asChild>
              <Link href="/pos">New order</Link>
            </Button>
          ) : null
        }
      />
      <Card>
        <CardContent className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <DateRangeFilter value={range} onChange={(r) => reset(() => setRange(r))} />
            <NativeSelect aria-label="Status" className="w-36" value={status} onChange={(e) => reset(() => setStatus(e.target.value))}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.charAt(0) + s.slice(1).toLowerCase()}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect aria-label="Payment" className="w-40" value={payment} onChange={(e) => reset(() => setPayment(e.target.value))}>
              <option value="">All payments</option>
              {PAYMENTS.map((s) => (
                <option key={s} value={s}>
                  {s.replace("_", " ").toLowerCase()}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect aria-label="Order type" className="w-36" value={type} onChange={(e) => reset(() => setType(e.target.value))}>
              <option value="">All types</option>
              <option value="DINE_IN">{t("Dine-in")}</option>
              <option value="TAKEAWAY">{t("Takeaway")}</option>
            </NativeSelect>
            <div className="relative ml-auto w-full sm:w-56">
              <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" aria-hidden />
              <Input
                aria-label="Search orders"
                placeholder="Order number or note"
                className="pl-8"
                value={search}
                onChange={(e) => reset(() => setSearch(e.target.value))}
              />
            </div>
          </div>
          <QueryState query={query}>
            {(data) =>
              data.items.length ? (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Order</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Customer</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Payment</TableHead>
                        <TableHead className="text-right">Items</TableHead>
                        <TableHead className="text-right">Total</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.items.map((o) => (
                        <TableRow key={o.id}>
                          <TableCell>
                            <Link href={`/orders/${o.id}`} className="font-medium text-primary hover:underline">
                              #{o.display_number}
                            </Link>
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(o.created_at)}</TableCell>
                          <TableCell>{o.table_name ? `Table ${o.table_name}` : t("Takeaway")}</TableCell>
                          <TableCell className="text-muted-foreground">{o.customer_name ?? "—"}</TableCell>
                          <TableCell>
                            <OrderStatusBadge status={o.status} />
                          </TableCell>
                          <TableCell>
                            <PaymentStatusBadge status={o.payment_status} />
                          </TableCell>
                          <TableCell className="text-right tabular">{o.item_count}</TableCell>
                          <TableCell className="text-right font-medium tabular">{formatMoney(o.total_minor)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
                </>
              ) : (
                <EmptyState icon={ReceiptText} title="No orders found" description="Try a wider date range or clear the filters." />
              )
            }
          </QueryState>
        </CardContent>
      </Card>
    </>
  );
}

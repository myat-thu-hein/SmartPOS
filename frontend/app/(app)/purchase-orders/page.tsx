"use client";

import { ClipboardList, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { QueryState } from "@/components/shared/query-state";
import { PurchaseOrderStatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime, formatMoney, humanize } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { Page, PurchaseOrderListItem, PurchaseOrderStatus, Supplier } from "@/types/api";

const STATUSES: PurchaseOrderStatus[] = ["DRAFT", "SUBMITTED", "PARTIALLY_RECEIVED", "RECEIVED", "CANCELLED"];

export default function PurchaseOrdersPage() {
  const { t } = useI18n();
  const { can } = useAuth();
  const [status, setStatus] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [page, setPage] = useState(1);
  const suppliers = useApi<Supplier[]>(["suppliers"], "/suppliers", { include_inactive: true });
  const query = useApi<Page<PurchaseOrderListItem>>(["purchase-orders", "list"], "/purchase-orders", {
    status: status || undefined,
    supplier_id: supplierId || undefined,
    page,
    page_size: 25,
  });
  return (
    <>
      <PageHeader
        title={t("Purchase Orders")}
        description="Draft, submit and receive supplier orders. Receiving a delivery adds stock through the inventory ledger."
        actions={
          can("purchasing:write") ? (
            <Button asChild>
              <Link href="/purchase-orders/new">
                <Plus /> New purchase order
              </Link>
            </Button>
          ) : null
        }
      />
      <Card>
        <CardContent className="grid gap-4">
          <div className="flex flex-wrap gap-2">
            <NativeSelect
              aria-label="Status"
              className="w-48"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label="Supplier"
              className="w-56"
              value={supplierId}
              onChange={(e) => {
                setSupplierId(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All suppliers</option>
              {(suppliers.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </NativeSelect>
          </div>
          <QueryState query={query}>
            {(data) =>
              data.items.length ? (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>PO</TableHead>
                        <TableHead>Supplier</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Expected</TableHead>
                        <TableHead className="text-right">Lines</TableHead>
                        <TableHead className="text-right">Est. total</TableHead>
                        <TableHead>Created</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.items.map((po) => (
                        <TableRow key={po.id}>
                          <TableCell>
                            <Link href={`/purchase-orders/${po.id}`} className="font-medium underline-offset-4 hover:underline">
                              {po.display_number}
                            </Link>
                          </TableCell>
                          <TableCell>{po.supplier_name}</TableCell>
                          <TableCell>
                            <PurchaseOrderStatusBadge status={po.status} />
                          </TableCell>
                          <TableCell className="text-muted-foreground">{formatDate(po.expected_delivery_date)}</TableCell>
                          <TableCell className="text-right tabular">{po.item_count}</TableCell>
                          <TableCell className="text-right tabular">{formatMoney(po.estimated_total_minor)}</TableCell>
                          <TableCell className="text-muted-foreground">{formatDateTime(po.created_at)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
                </>
              ) : (
                <EmptyState
                  icon={ClipboardList}
                  title="No purchase orders"
                  description={status || supplierId ? "Nothing matches these filters." : "Create one here, or from an approved reorder suggestion on the Forecasting page."}
                />
              )
            }
          </QueryState>
        </CardContent>
      </Card>
    </>
  );
}

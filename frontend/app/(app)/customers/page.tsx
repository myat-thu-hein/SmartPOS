"use client";

import { Plus, Search, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { QueryState } from "@/components/shared/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CustomerDialog } from "@/features/customers/customer-dialog";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { CustomerAny, Page } from "@/types/api";

export default function CustomersPage() {
  const { t } = useI18n();
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const full = can("customers:write");
  const query = useApi<Page<CustomerAny>>(["customers", "list"], "/customers", {
    search: search.trim() || undefined,
    page,
    page_size: 25,
  });

  return (
    <>
      <PageHeader
        title={t("Customers")}
        description={
          full
            ? "Customer profiles, spending and loyalty balances."
            : "Look up customers for loyalty. Contact details are masked for your role."
        }
        actions={
          can("customers:create") ? (
            <Button onClick={() => setCreating(true)}>
              <Plus /> New customer
            </Button>
          ) : null
        }
      />
      <Card>
        <CardContent className="grid gap-4">
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" aria-hidden />
            <Input
              aria-label="Search customers"
              placeholder="Name or phone"
              className="pl-8"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <QueryState query={query}>
            {(data) =>
              data.items.length ? (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Phone</TableHead>
                        {full ? <TableHead>Email</TableHead> : null}
                        {full ? <TableHead className="text-right">Orders</TableHead> : null}
                        {full ? <TableHead className="text-right">Total spent</TableHead> : null}
                        <TableHead className="text-right">Points</TableHead>
                        {full ? <TableHead>Last visit</TableHead> : null}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.items.map((c) => (
                        <TableRow key={c.id}>
                          <TableCell className="font-medium">
                            {full ? (
                              <Link href={`/customers/${c.id}`} className="text-primary hover:underline">
                                {c.name}
                              </Link>
                            ) : (
                              c.name
                            )}
                          </TableCell>
                          <TableCell className="text-muted-foreground tabular">
                            {"phone_masked" in c ? (c.phone_masked ?? "—") : (c.phone ?? "—")}
                          </TableCell>
                          {"email" in c ? (
                            <>
                              <TableCell className="text-muted-foreground">{c.email ?? "—"}</TableCell>
                              <TableCell className="text-right tabular">{c.order_count}</TableCell>
                              <TableCell className="text-right tabular">{formatMoney(c.total_spent_minor)}</TableCell>
                            </>
                          ) : null}
                          <TableCell className="text-right font-medium tabular">{c.loyalty_balance}</TableCell>
                          {"last_order_at" in c ? (
                            <TableCell className="text-muted-foreground">{c.last_order_at ? formatDate(c.last_order_at) : "—"}</TableCell>
                          ) : null}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
                </>
              ) : (
                <EmptyState
                  icon={Users}
                  title={search ? "No customers match" : "No customers yet"}
                  description="Customers can also be added from the POS when taking an order."
                />
              )
            }
          </QueryState>
        </CardContent>
      </Card>
      {creating ? <CustomerDialog onClose={() => setCreating(false)} /> : null}
    </>
  );
}

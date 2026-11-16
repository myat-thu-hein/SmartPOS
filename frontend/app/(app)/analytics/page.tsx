"use client";

import { AlertTriangle } from "lucide-react";
import { useState } from "react";

import { BarList, ChartCard, ColumnChart, ColumnTable } from "@/components/charts/charts";
import { PageHeader } from "@/components/shared/page-header";
import { ErrorState, QueryState } from "@/components/shared/query-state";
import { StatCard } from "@/components/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AnalyticsFilters, defaultFilters, filterQuery, type AnalyticsFilterState } from "@/features/analytics/filters";
import { useApi } from "@/hooks/use-api";
import { formatMoney, formatMoneyCompact, formatNumber, formatQty, formatShortDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type {
  CategorySales,
  DayBucket,
  HourBucket,
  IngredientUsage,
  PaymentShare,
  PeriodComparison,
  ProductSales,
  SupplierSpend,
} from "@/types/api";

export default function AnalyticsPage() {
  const { t } = useI18n();
  const [filters, setFilters] = useState<AnalyticsFilterState>(() => defaultFilters());
  const q = filterQuery(filters);
  const comparison = useApi<PeriodComparison>(["analytics", "comparison"], "/analytics/comparison", q);
  const byDay = useApi<DayBucket[]>(["analytics", "by-day"], "/analytics/sales-by-day", q);
  const byHour = useApi<HourBucket[]>(["analytics", "by-hour"], "/analytics/sales-by-hour", q);
  const categories = useApi<CategorySales[]>(["analytics", "categories"], "/analytics/sales-by-category", q);
  const payments = useApi<PaymentShare[]>(["analytics", "payments"], "/analytics/payment-distribution", q);
  const top = useApi<ProductSales[]>(["analytics", "top"], "/analytics/top-products", { ...q, limit: 10 });
  const slow = useApi<ProductSales[]>(["analytics", "slow"], "/analytics/slow-products", { ...q, limit: 10 });
  const consumption = useApi<IngredientUsage[]>(["analytics", "consumption"], "/analytics/ingredient-consumption", q);
  const waste = useApi<IngredientUsage[]>(["analytics", "waste"], "/analytics/waste", q);
  const purchases = useApi<SupplierSpend[]>(["analytics", "purchases"], "/analytics/purchases", q);

  const days = (byDay.data ?? []).map((d) => ({
    key: d.date,
    label: formatShortDate(d.date),
    value: d.total_billed_minor,
    secondary: `${d.order_count} orders`,
  }));
  const hours = (byHour.data ?? [])
    .filter((h) => h.order_count > 0 || (h.hour >= 10 && h.hour <= 22))
    .map((h) => ({ key: String(h.hour), label: `${h.hour}:00`, value: h.total_billed_minor, secondary: `${h.order_count} orders` }));

  return (
    <>
      <PageHeader title={t("Analytics")} description="Sales, products, payments and stock usage for the selected period (restaurant local time)." />
      <div className="grid gap-4">
        <Card className="py-4">
          <CardContent>
            <AnalyticsFilters value={filters} onChange={setFilters} />
          </CardContent>
        </Card>

        {comparison.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-28" />
            ))}
          </div>
        ) : comparison.isError ? (
          <ErrorState error={comparison.error} onRetry={() => comparison.refetch()} />
        ) : (
          <Summary data={comparison.data} />
        )}

        <div className="grid gap-4 xl:grid-cols-2">
          <ChartCard
            title="Sales by day"
            description="Total billed per day"
            chart={
              byDay.isPending ? (
                <Skeleton className="h-64" />
              ) : (
                <ColumnChart data={days} valueLabel="Total billed" formatValue={(v) => formatMoney(v)} formatTick={formatMoneyCompact} />
              )
            }
            table={<ColumnTable data={days} labelHeader="Date" valueHeader="Total billed" formatValue={(v) => formatMoney(v)} />}
          />
          <ChartCard
            title="Sales by hour"
            description="Total billed per hour of day, summed over the period"
            chart={
              byHour.isPending ? (
                <Skeleton className="h-64" />
              ) : (
                <ColumnChart data={hours} valueLabel="Total billed" formatValue={(v) => formatMoney(v)} formatTick={formatMoneyCompact} />
              )
            }
            table={<ColumnTable data={hours} labelHeader="Hour" valueHeader="Total billed" formatValue={(v) => formatMoney(v)} />}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Sales by category</CardTitle>
              <CardDescription>Item sales before order-level discounts</CardDescription>
            </CardHeader>
            <CardContent>
              <QueryState query={categories}>
                {(list) => (
                  <BarList
                    items={list.map((c) => ({
                      key: c.category_name,
                      label: c.category_name,
                      value: c.sales_minor,
                      detail: `${formatNumber(c.share_pct, 1)}% · ${formatNumber(c.quantity, 0)} sold`,
                    }))}
                    formatValue={(v) => formatMoney(v)}
                  />
                )}
              </QueryState>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Payment methods</CardTitle>
              <CardDescription>Collected amounts, net of refunds</CardDescription>
            </CardHeader>
            <CardContent>
              <QueryState query={payments}>
                {(list) => (
                  <BarList
                    items={list.map((p) => ({
                      key: p.method_code,
                      label: p.is_simulated && !/simulated/i.test(p.method_name) ? `${p.method_name} (simulated)` : p.method_name,
                      value: p.amount_minor - p.refunded_minor,
                      detail: `${formatNumber(p.share_pct, 1)}% · ${p.payment_count} payments`,
                    }))}
                    formatValue={(v) => formatMoney(v)}
                  />
                )}
              </QueryState>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <ProductTable title="Top products" description="Best sellers by revenue" query={top} />
          <ProductTable title="Slow movers" description="Active products with the lowest sales, including zero" query={slow} />
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <UsageTable title="Ingredient consumption" description="Deducted by sales, net of restocks from cancellations" query={consumption} />
          <UsageTable title="Waste" description="Recorded as WASTE movements" query={waste} emptyText="No waste recorded in this period." />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Purchases by supplier</CardTitle>
            <CardDescription>Value of deliveries received in the period</CardDescription>
          </CardHeader>
          <CardContent>
            <QueryState query={purchases}>
              {(list) =>
                list.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Supplier</TableHead>
                        <TableHead className="text-right">Deliveries</TableHead>
                        <TableHead className="text-right">Received value</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {list.map((s) => (
                        <TableRow key={s.supplier_id}>
                          <TableCell>{s.supplier_name}</TableCell>
                          <TableCell className="text-right tabular">{s.deliveries}</TableCell>
                          <TableCell className="text-right tabular">{formatMoney(s.amount_minor)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="py-6 text-center text-sm text-muted-foreground">No deliveries received in this period.</p>
                )
              }
            </QueryState>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function Summary({ data }: { data: PeriodComparison }) {
  const c = data.current;
  const days = Math.round((Date.parse(c.range.end_date) - Date.parse(c.range.start_date)) / 86_400_000) + 1;
  const cutoff = c.range.cutoff_time?.slice(0, 5);
  const vs = `vs previous ${days} day${days === 1 ? "" : "s"}${cutoff ? `, up to ${cutoff}` : ""}`;
  return (
    <div className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Net sales"
          value={formatMoney(c.net_sales_minor)}
          delta={data.net_sales_change_pct}
          deltaLabel={vs}
          hint={c.prices_include_tax ? "After discounts and refunds; VAT included, service charge excluded" : "After discounts and refunds; before VAT and service charge"}
        />
        <StatCard label="Orders" value={formatNumber(c.order_count, 0)} delta={data.order_count_change_pct} deltaLabel={vs} />
        <StatCard label="Average order value" value={formatMoney(c.average_order_value_minor)} delta={data.aov_change_pct} deltaLabel={vs} />
        <StatCard
          label="Est. gross profit"
          value={c.estimated_gross_profit_minor === null ? "—" : formatMoney(c.estimated_gross_profit_minor)}
          hint={
            c.cost_data_complete ? (
              `Ingredient cost ${formatMoney(c.estimated_ingredient_cost_minor)}`
            ) : (
              <span className="inline-flex items-center gap-1">
                <AlertTriangle className="size-3 text-status-warning" aria-hidden /> Some ingredients have no cost; estimate is incomplete
              </span>
            )
          }
        />
      </div>
      <Card className="py-4">
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4 xl:grid-cols-7">
            {(
              [
                ["Gross sales", c.gross_sales_minor],
                ["Discounts", -c.discounts_minor],
                ["Refunds", -c.refunds_minor],
                [c.prices_include_tax ? "VAT (included)" : "VAT", c.tax_minor],
                ["Service charge", c.service_charge_minor],
                ["Total billed", c.total_billed_minor],
                ["Collected", c.total_collected_minor],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="font-medium tabular">{formatMoney(value)}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">{formatNumber(c.items_sold, 0)} items sold. Cancelled and unpaid draft orders are excluded.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function ProductTable({
  title,
  description,
  query,
}: {
  title: string;
  description: string;
  query: ReturnType<typeof useApi<ProductSales[]>>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <QueryState query={query}>
          {(list) =>
            list.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Sales</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.map((p) => (
                    <TableRow key={p.product_id}>
                      <TableCell className="font-medium">{p.product_name}</TableCell>
                      <TableCell className="text-muted-foreground">{p.category_name ?? "—"}</TableCell>
                      <TableCell className="text-right tabular">{formatNumber(p.quantity, 0)}</TableCell>
                      <TableCell className="text-right tabular">{formatMoney(p.sales_minor)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="py-6 text-center text-sm text-muted-foreground">No product sales in this period.</p>
            )
          }
        </QueryState>
      </CardContent>
    </Card>
  );
}

function UsageTable({
  title,
  description,
  query,
  emptyText = "No usage in this period.",
}: {
  title: string;
  description: string;
  query: ReturnType<typeof useApi<IngredientUsage[]>>;
  emptyText?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <QueryState query={query}>
          {(list) =>
            list.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ingredient</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Est. cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.slice(0, 12).map((u) => (
                    <TableRow key={u.ingredient_id}>
                      <TableCell>{u.ingredient_name}</TableCell>
                      <TableCell className="text-right tabular">{formatQty(u.quantity, u.base_unit)}</TableCell>
                      <TableCell className="text-right tabular">
                        {u.cost_known ? formatMoney(u.estimated_cost_minor) : <Badge variant="outline">no cost</Badge>}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="py-6 text-center text-sm text-muted-foreground">{emptyText}</p>
            )
          }
        </QueryState>
        {query.data && query.data.length > 12 ? (
          <p className="mt-2 text-xs text-muted-foreground">Showing 12 of {query.data.length}. Download the full list from Reports.</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

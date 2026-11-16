"use client";

import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  ChefHat,
  OctagonAlert,
  Plus,
  ReceiptText,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Wallet,
} from "lucide-react";
import Link from "next/link";

import { BarList, ChartCard, ColumnChart, ColumnTable, Sparkline } from "@/components/charts/charts";
import { EmptyState } from "@/components/shared/empty-state";
import { InsightList } from "@/components/shared/insight-list";
import { PageHeader } from "@/components/shared/page-header";
import { ErrorState } from "@/components/shared/query-state";
import { StatCard } from "@/components/shared/stat-card";
import { OrderStatusBadge, PaymentStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { useAuth } from "@/lib/auth";
import { formatMoney, formatMoneyCompact, formatNumber, formatShortDate, formatTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useLiveRefetchInterval } from "@/lib/realtime";
import { cn } from "@/lib/utils";
import type { Dashboard, StockRisk } from "@/types/api";

function DashboardSkeleton() {
  return (
    <div className="grid gap-4" aria-busy="true" aria-label="Loading dashboard">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <Skeleton className="h-80 rounded-xl xl:col-span-2" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    </div>
  );
}

function greeting(timezone: string): string {
  const hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone: timezone }).format(new Date()));
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

export default function DashboardPage() {
  const { t } = useI18n();
  const { membership, me, can } = useAuth();
  const refetchInterval = useLiveRefetchInterval(60_000, 300_000);
  const query = useApi<Dashboard>(["dashboard"], "/analytics/dashboard", undefined, { refetchInterval });
  const data = query.data;
  const firstName = me?.user.full_name.split(/\s+/)[0];
  const today = new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: data?.timezone ?? "Asia/Bangkok",
  }).format(new Date());

  return (
    <>
      <PageHeader
        title={data ? `${greeting(data.timezone)}${firstName ? `, ${firstName}` : ""}` : t("Dashboard")}
        description={[t("Dashboard"), membership?.restaurant_name, today].filter(Boolean).join(" · ")}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => query.refetch()} disabled={query.isFetching}>
              <RefreshCw className={query.isFetching ? "animate-spin" : undefined} /> Refresh
            </Button>
            {can("orders:create") ? (
              <Button asChild size="sm">
                <Link href="/pos">
                  <Plus /> New sale
                </Link>
              </Button>
            ) : null}
          </>
        }
      />
      {query.isPending ? (
        <DashboardSkeleton />
      ) : query.isError || !data ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        // Hold the previous render while refetching instead of flashing skeletons.
        <div className={cn("transition-opacity", query.isFetching && "opacity-80")}>
          <DashboardContent data={data} />
        </div>
      )}
    </>
  );
}

const RISK_BADGE: Record<StockRisk["level"], { label: string; variant: "danger" | "warning" | "secondary" }> = {
  out: { label: "Out", variant: "danger" },
  critical: { label: "Critical", variant: "danger" },
  warning: { label: "Reorder soon", variant: "warning" },
  ok: { label: "OK", variant: "secondary" },
};

function StockRiskCard({ risks, total }: { risks: StockRisk[]; total: number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Boxes className="size-4 text-muted-foreground" aria-hidden /> Stock at risk
        </CardTitle>
        <CardDescription>
          Days of cover vs supplier lead time{total > risks.length ? ` · ${risks.length} of ${total} shown` : ""}
        </CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/inventory">
              Inventory <ArrowRight />
            </Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {risks.length ? (
          <ul className="grid gap-3">
            {risks.map((r) => {
              const badge = RISK_BADGE[r.level];
              const Icon = r.level === "warning" ? AlertTriangle : OctagonAlert;
              return (
                <li key={r.ingredient_id} className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{r.ingredient_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {r.level === "out"
                        ? "No stock left"
                        : r.days_of_cover !== null
                          ? `~${formatNumber(r.days_of_cover, 1)} days left · delivery ${r.lead_time_days} day${r.lead_time_days === 1 ? "" : "s"}`
                          : "At or below reorder level"}
                      {r.incoming > 0 ? " · on order" : ""}
                    </p>
                  </div>
                  <Badge variant={badge.variant} className="shrink-0" title={r.reason}>
                    <Icon aria-hidden /> {badge.label}
                  </Badge>
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState title="Stock is healthy" description="Nothing runs out before a delivery could arrive." />
        )}
      </CardContent>
    </Card>
  );
}

function KitchenCard({ kitchen }: { kitchen: NonNullable<Dashboard["kitchen"]> }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ChefHat className="size-4 text-muted-foreground" aria-hidden /> Kitchen now
        </CardTitle>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/kitchen">
              Open display <ArrowRight />
            </Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="grid grid-cols-3 gap-3 text-center">
        {(
          [
            ["New", kitchen.new],
            ["Preparing", kitchen.preparing],
            ["Ready", kitchen.ready],
          ] as const
        ).map(([label, count]) => (
          <div key={label} className="rounded-lg border bg-muted/40 py-4">
            <p className="text-3xl font-semibold">{count}</p>
            <p className="text-xs text-muted-foreground">{t(label)}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function DashboardContent({ data }: { data: Dashboard }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const today = data.today;
  const cmp = data.comparison;
  const todayKey = data.sales_last_14_days.at(-1)?.date;
  const days = data.sales_last_14_days.map((d) => ({
    key: d.date,
    label: formatShortDate(d.date),
    value: d.total_billed_minor,
    secondary: `${d.order_count} orders`,
  }));
  // Show trading hours (10:00-22:00) plus any hour that actually had sales.
  const activeHours = data.sales_by_hour_today.filter((h) => h.order_count > 0).map((h) => h.hour);
  const firstHour = Math.min(10, ...activeHours);
  const lastHour = Math.max(22, ...activeHours);
  const hours = data.sales_by_hour_today
    .filter((h) => h.hour >= firstHour && h.hour <= lastHour)
    .map((h) => ({ key: String(h.hour), label: `${h.hour}:00`, value: h.total_billed_minor, secondary: `${h.order_count} orders` }));
  const netTrend = data.sales_last_14_days.map((d) => ({ label: formatShortDate(d.date), value: d.net_sales_minor }));
  const orderTrend = data.sales_last_14_days.map((d) => ({ label: formatShortDate(d.date), value: d.order_count }));
  const showStock = can("inventory:read");

  return (
    <div className="grid gap-4">
      {today && cmp ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label={t("Today's sales")}
            icon={<Wallet aria-hidden />}
            value={formatMoney(today.net_sales_minor)}
            delta={cmp.net_sales_change_pct}
            deltaLabel="vs same time yesterday"
            hint={cmp.net_sales_change_pct === null ? "Net sales · no sales by this time yesterday" : undefined}
            trend={<Sparkline points={netTrend} formatValue={(v) => formatMoney(v)} />}
          />
          <StatCard
            label="Orders today"
            icon={<ReceiptText aria-hidden />}
            value={today.order_count}
            delta={cmp.order_count_change_pct}
            deltaLabel="vs same time yesterday"
            trend={<Sparkline points={orderTrend} formatValue={(v) => `${v} orders`} />}
          />
          <StatCard
            label="Average order value"
            icon={<TrendingUp aria-hidden />}
            value={formatMoney(today.average_order_value_minor)}
            delta={cmp.aov_change_pct}
            deltaLabel="vs same time yesterday"
            hint={`${today.items_sold} items sold`}
          />
          {showStock ? (
            <StatCard
              label="Needs attention"
              icon={<AlertTriangle aria-hidden />}
              value={
                data.stock_critical_count
                  ? `${data.stock_critical_count} critical`
                  : data.stock_at_risk_count
                    ? `${data.stock_at_risk_count} to reorder`
                    : "All clear"
              }
              hint={`${data.stock_at_risk_count} ingredient(s) low on cover · ${data.pending_recommendation_count} reorder suggestion(s)`}
            />
          ) : data.kitchen ? (
            <StatCard
              label="Kitchen queue"
              icon={<ChefHat aria-hidden />}
              value={data.kitchen.new + data.kitchen.preparing}
              hint={`${data.kitchen.ready} ready to serve`}
            />
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        {days.length ? (
          <ChartCard
            className={showStock ? "xl:col-span-2" : "xl:col-span-3"}
            title="Sales, last 14 days"
            description="Total billed per day (incl. service charge and VAT) · today highlighted"
            chart={
              <ColumnChart
                data={days}
                valueLabel="Total billed"
                formatValue={(v) => formatMoney(v)}
                formatTick={formatMoneyCompact}
                highlightKey={todayKey}
                height={260}
              />
            }
            table={<ColumnTable data={days} labelHeader="Date" valueHeader="Total billed" formatValue={(v) => formatMoney(v)} />}
          />
        ) : null}
        {showStock ? <StockRiskCard risks={data.stock_at_risk} total={data.stock_at_risk_count} /> : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" aria-hidden /> Smart insights
          </CardTitle>
          <CardDescription>Calculated from your sales, stock and forecasts, with the numbers behind each one</CardDescription>
        </CardHeader>
        <CardContent>
          {data.insights.length ? (
            <InsightList insights={data.insights} className="-mx-2 gap-x-6 md:grid-cols-2" />
          ) : (
            <p className="text-sm text-muted-foreground">No insights yet. They appear as orders come in.</p>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {today ? (
          <ChartCard
            title="Today by hour"
            description="Total billed per hour"
            chart={
              activeHours.length ? (
                <ColumnChart data={hours} valueLabel="Total billed" formatValue={(v) => formatMoney(v)} formatTick={formatMoneyCompact} height={200} />
              ) : (
                <EmptyState title="No paid orders yet today" description="Hourly sales appear once orders are paid." />
              )
            }
            table={<ColumnTable data={hours} labelHeader="Hour" valueHeader="Total billed" formatValue={(v) => formatMoney(v)} />}
          />
        ) : null}
        {data.top_products_7_days.length || today ? (
          <Card>
            <CardHeader>
              <CardTitle>Top products, last 7 days</CardTitle>
              <CardDescription>Units sold</CardDescription>
            </CardHeader>
            <CardContent>
              <BarList
                items={data.top_products_7_days.map((p) => ({
                  key: p.product_id,
                  label: p.product_name,
                  value: p.quantity,
                  detail: formatMoney(p.sales_minor),
                }))}
                formatValue={(v) => `${v}`}
              />
            </CardContent>
          </Card>
        ) : null}
        {data.kitchen ? <KitchenCard kitchen={data.kitchen} /> : null}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Recent orders</CardTitle>
            <CardAction>
              <Button asChild variant="ghost" size="sm">
                <Link href="/orders">
                  View all <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            {data.recent_orders.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Order</TableHead>
                    <TableHead>Time</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Payment</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.recent_orders.map((o) => (
                    <TableRow key={o.id}>
                      <TableCell>
                        <Link href={`/orders/${o.id}`} className="font-medium hover:underline">
                          #{o.display_number}
                        </Link>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {o.table_name ? `Table ${o.table_name}` : t("Takeaway")}
                        </span>
                      </TableCell>
                      <TableCell className="text-muted-foreground tabular">{formatTime(o.created_at, data.timezone)}</TableCell>
                      <TableCell>
                        <OrderStatusBadge status={o.status} />
                      </TableCell>
                      <TableCell>
                        <PaymentStatusBadge status={o.payment_status} />
                      </TableCell>
                      <TableCell className="text-right tabular">{formatMoney(o.total_minor)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState title="No orders yet" description="Orders created at the POS appear here." />
            )}
          </CardContent>
        </Card>

        <div className="grid content-start gap-4">
          {data.forecast ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="size-4 text-muted-foreground" aria-hidden /> Forecast for{" "}
                  {formatShortDate(data.forecast.target_date)}
                </CardTitle>
                <CardDescription>
                  Predicted, not actual · {data.forecast.model_name.replaceAll("_", " ")}
                  {data.forecast.uses_demo_data ? " · demo data" : ""}
                </CardDescription>
                {data.forecast.is_stale ? (
                  <CardAction>
                    <Badge variant="warning">
                      <AlertTriangle aria-hidden /> Out of date
                    </Badge>
                  </CardAction>
                ) : null}
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  {data.forecast.top_products.map((p) => (
                    <li key={p.product_name} className="flex justify-between gap-2">
                      <span className="truncate">{p.product_name}</span>
                      <span className="tabular text-muted-foreground">≈ {Math.round(p.predicted_quantity)}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}

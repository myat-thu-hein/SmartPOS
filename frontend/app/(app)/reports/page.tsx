"use client";

import { Download, FileSpreadsheet, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AnalyticsFilters, defaultFilters, filterQuery, type AnalyticsFilterState } from "@/features/analytics/filters";
import { downloadFile, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

interface Report {
  id: string;
  title: string;
  description: string;
  path: string;
  /** Which filters the endpoint honours. */
  uses: "all" | "dates" | "none";
}

const REPORTS: Report[] = [
  {
    id: "daily-sales",
    title: "Daily sales",
    description: "One row per day: orders, gross sales, discounts, refunds, net sales, VAT, service charge and collected.",
    path: "/reports/daily-sales.csv",
    uses: "all",
  },
  {
    id: "product-sales",
    title: "Product sales",
    description: "Quantity and revenue per menu item and category.",
    path: "/reports/product-sales.csv",
    uses: "all",
  },
  {
    id: "orders",
    title: "Orders",
    description: "Every order created in the period, any status (cancelled orders include the reason), with type, table, customer, totals and refunds.",
    path: "/reports/orders.csv",
    uses: "dates",
  },
  {
    id: "inventory-movements",
    title: "Inventory movements",
    description: "The stock ledger: every receipt, sale deduction, waste, adjustment and count, with balances and cost basis.",
    path: "/reports/inventory-movements.csv",
    uses: "dates",
  },
  {
    id: "inventory-valuation",
    title: "Inventory valuation",
    description: "Current stock per ingredient valued at moving-average cost. Always as of now.",
    path: "/reports/inventory-valuation.csv",
    uses: "none",
  },
  {
    id: "purchases",
    title: "Purchases",
    description: "Deliveries received per supplier: number of deliveries and their total value.",
    path: "/reports/purchases.csv",
    uses: "dates",
  },
];

export default function ReportsPage() {
  const { t } = useI18n();
  const [filters, setFilters] = useState<AnalyticsFilterState>(() => defaultFilters());
  const [busy, setBusy] = useState<string | null>(null);

  async function download(report: Report) {
    setBusy(report.id);
    try {
      const all = filterQuery(filters);
      const query =
        report.uses === "all" ? all : report.uses === "dates" ? { start_date: all.start_date, end_date: all.end_date } : {};
      await downloadFile(report.path, query, `${report.id}.csv`);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        title={t("Reports")}
        description="CSV exports in UTF-8 with Thai text preserved for Excel and Google Sheets. Amounts are in baht; per-unit cost columns are in satang, as their headers say."
      />
      <div className="grid gap-4">
        <Card className="py-4">
          <CardContent className="grid gap-2">
            <AnalyticsFilters value={filters} onChange={setFilters} />
            <p className="text-xs text-muted-foreground">
              Period {formatDate(filters.range.start)} – {formatDate(filters.range.end)} in restaurant local time. Category,
              product, payment and order-type filters apply to the sales reports only.
            </p>
          </CardContent>
        </Card>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {REPORTS.map((report) => (
            <Card key={report.id}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileSpreadsheet className="size-4 text-muted-foreground" aria-hidden /> {report.title}
                </CardTitle>
                <CardDescription>{report.description}</CardDescription>
              </CardHeader>
              <CardContent className="mt-auto flex items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground">
                  {report.uses === "none" ? "Current snapshot" : report.uses === "dates" ? "Uses the period" : "Uses all filters"}
                </span>
                <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => download(report)}>
                  {busy === report.id ? <Loader2 className="animate-spin" /> : <Download />} Download CSV
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </>
  );
}

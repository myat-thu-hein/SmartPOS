import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Dashboard, SalesSummary } from "@/types/api";

// The dashboard reads from useApi; each test decides what the "server" returned.
const query = { isPending: true, isError: false, isFetching: false, error: null as unknown, data: undefined as Dashboard | undefined, refetch: vi.fn() };
vi.mock("@/hooks/use-api", () => ({ useApi: () => query }));
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    membership: { restaurant_name: "Baan Test" },
    me: { user: { full_name: "Mali Srisuk" } },
    permissions: new Set(["orders:read"]),
    can: () => true,
  }),
}));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));

const { default: DashboardPage } = await import("@/app/(app)/dashboard/page");

function summary(net: number, orders: number): SalesSummary {
  return {
    range: { start_date: "2026-10-25", end_date: "2026-10-25", timezone: "Asia/Bangkok", cutoff_time: "12:01:00" },
    order_count: orders,
    items_sold: orders * 2,
    gross_sales_minor: net,
    discounts_minor: 0,
    refunds_minor: 0,
    net_sales_minor: net,
    tax_minor: 0,
    service_charge_minor: 0,
    total_billed_minor: net,
    total_collected_minor: net,
    average_order_value_minor: orders ? Math.round(net / orders) : 0,
    estimated_ingredient_cost_minor: 0,
    estimated_gross_profit_minor: null,
    cost_data_complete: true,
    prices_include_tax: true,
  };
}

const dashboard: Dashboard = {
  generated_at: "2026-10-25T05:00:00Z",
  timezone: "Asia/Bangkok",
  today: summary(1_234_500, 25),
  comparison: {
    current: summary(1_234_500, 25),
    previous: summary(1_000_000, 20),
    net_sales_change_pct: 23.5,
    order_count_change_pct: 25,
    aov_change_pct: -1.2,
  },
  sales_last_14_days: [
    { date: "2026-10-24", order_count: 20, gross_sales_minor: 1_000_000, net_sales_minor: 990_000, total_billed_minor: 1_000_000 },
    { date: "2026-10-25", order_count: 25, gross_sales_minor: 1_234_500, net_sales_minor: 1_234_500, total_billed_minor: 1_234_500 },
  ],
  sales_by_hour_today: [{ hour: 12, order_count: 25, total_billed_minor: 1_234_500 }],
  top_products_7_days: [{ product_id: "p1", product_name: "Pad Thai", category_name: "Noodles", quantity: 40, sales_minor: 480_000 }],
  low_stock: [{ id: "i1", name: "Thai basil", base_unit: "g", current_stock: 55, reorder_level: 200 }],
  recent_orders: [
    { id: "o1", display_number: "BS0042", order_type: "TAKEAWAY", status: "COMPLETED", payment_status: "PAID", total_minor: 12_000, created_at: "2026-10-25T04:30:00Z", table_name: null },
  ],
  kitchen: { new: 2, preparing: 1, ready: 0 },
  forecast: null,
  pending_recommendations: [],
  pending_recommendation_count: 1,
  stock_at_risk: [
    {
      ingredient_id: "i1",
      ingredient_name: "Thai basil",
      base_unit: "g",
      current_stock: 55,
      reorder_level: 200,
      incoming: 0,
      daily_usage: 40,
      usage_basis: "recent_sales",
      days_of_cover: 1.4,
      runs_out_on: "2026-10-26",
      lead_time_days: 2,
      supplier_name: null,
      level: "critical",
      reason: "About 1.4 day(s) left at 40 g/day (last 14 days); lead time is 2 day(s).",
    },
  ],
  stock_at_risk_count: 1,
  stock_critical_count: 1,
  insights: [
    {
      key: "sales-today",
      category: "sales",
      severity: "positive",
      title: "Sales are up 12% on yesterday",
      detail: "฿12,345.00 net from 25 order(s).",
      link: "/analytics",
      action: null,
    },
  ],
};

describe("Dashboard data loading", () => {
  beforeEach(() => {
    Object.assign(query, { isPending: true, isError: false, error: null, data: undefined });
    query.refetch.mockReset();
  });

  it("shows placeholders while loading, not zero totals", () => {
    const { container } = render(<DashboardPage />);
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByText("฿0.00")).not.toBeInTheDocument();
  });

  it("renders the figures returned by the API", () => {
    Object.assign(query, { isPending: false, data: dashboard });
    render(<DashboardPage />);
    expect(screen.getAllByText("฿12,345.00").length).toBeGreaterThan(0);
    expect(screen.getByText("+23.5%")).toBeInTheDocument();
    expect(screen.getByText("1 critical")).toBeInTheDocument();
    expect(screen.getByText(/~1.4 days left · delivery 2 days/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/^Good (morning|afternoon|evening), Mali$/);
    expect(screen.getByText("#BS0042")).toBeInTheDocument();
    expect(screen.getByText("Thai basil")).toBeInTheDocument();
    expect(screen.getByText("Sales are up 12% on yesterday")).toBeInTheDocument();
  });

  it("offers a retry when the request fails", async () => {
    Object.assign(query, { isPending: false, isError: true, error: new Error("Cannot reach the SmartPOS server.") });
    render(<DashboardPage />);
    expect(screen.getByRole("alert")).toHaveTextContent("Cannot reach the SmartPOS server.");
    await userEvent.click(screen.getAllByRole("button", { name: /try again/i })[0]);
    expect(query.refetch).toHaveBeenCalled();
  });
});

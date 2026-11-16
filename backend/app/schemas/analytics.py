"""Analytics, dashboard and report schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field

from app.utils.types import Qty


class DateRange(BaseModel):
    start_date: date
    end_date: date
    timezone: str
    cutoff_time: time | None = Field(
        default=None, description="Local time at which the last day ends (set when comparing a day in progress)"
    )


class SalesSummary(BaseModel):
    """Metric definitions (all amounts in minor units):

    * gross_sales: item totals at menu prices for eligible orders (tax-inclusive when menu prices include tax)
    * discounts: order discounts plus loyalty redemptions
    * refunds: refunds recorded during the period
    * net_sales: gross_sales - discounts - refunds
    * tax / service_charges: amounts recorded on eligible orders
    * total_billed: what customers were charged (incl. service charge and tax)
    * total_collected: total_billed - refunds
    * average_order_value: total_billed / order_count

    Eligible orders are non-cancelled orders that became fully paid within the period.
    """

    range: DateRange
    order_count: int
    items_sold: int
    gross_sales_minor: int
    discounts_minor: int
    refunds_minor: int
    net_sales_minor: int
    tax_minor: int
    service_charge_minor: int
    total_billed_minor: int
    total_collected_minor: int
    average_order_value_minor: int
    estimated_ingredient_cost_minor: int
    estimated_gross_profit_minor: int | None
    cost_data_complete: bool
    prices_include_tax: bool


class PeriodComparison(BaseModel):
    current: SalesSummary
    previous: SalesSummary
    net_sales_change_pct: float | None
    order_count_change_pct: float | None
    aov_change_pct: float | None


class HourBucket(BaseModel):
    hour: int
    order_count: int
    total_billed_minor: int


class DayBucket(BaseModel):
    date: date
    order_count: int
    gross_sales_minor: int
    net_sales_minor: int
    total_billed_minor: int


class CategorySales(BaseModel):
    category_name: str
    quantity: int
    sales_minor: int
    share_pct: float


class ProductSales(BaseModel):
    product_id: uuid.UUID
    product_name: str
    category_name: str | None
    quantity: int
    sales_minor: int


class PaymentShare(BaseModel):
    method_code: str
    method_name: str
    payment_count: int
    amount_minor: int
    refunded_minor: int
    share_pct: float
    is_simulated: bool


class IngredientUsage(BaseModel):
    ingredient_id: uuid.UUID
    ingredient_name: str
    base_unit: str
    quantity: Qty
    estimated_cost_minor: int
    cost_known: bool


class SupplierSpend(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str
    deliveries: int
    amount_minor: int


class KitchenCounts(BaseModel):
    new: int
    preparing: int
    ready: int


class RecentOrder(BaseModel):
    id: uuid.UUID
    display_number: str
    order_type: str
    status: str
    payment_status: str
    total_minor: int
    created_at: datetime
    table_name: str | None


class LowStockItem(BaseModel):
    id: uuid.UUID
    name: str
    base_unit: str
    current_stock: Qty
    reorder_level: Qty


class ForecastHighlight(BaseModel):
    product_name: str
    predicted_quantity: Qty


class ForecastSummary(BaseModel):
    run_id: uuid.UUID
    model_name: str
    created_at: datetime
    target_date: date
    total_predicted_items: Qty
    top_products: list[ForecastHighlight]
    uses_demo_data: bool
    warnings: list[str]
    # Last day the run predicts; a run whose dates have passed (or that is old) is stale.
    covers_until: date | None = None
    is_stale: bool = False


class PendingRecommendation(BaseModel):
    id: uuid.UUID
    ingredient_name: str
    suggested_quantity: Qty
    unit: str
    created_at: datetime


RiskLevel = Literal["out", "critical", "warning", "ok"]


class StockRisk(BaseModel):
    """How long an ingredient lasts at its expected use, against the supplier's lead time."""

    ingredient_id: uuid.UUID
    ingredient_name: str
    base_unit: str
    current_stock: Qty
    reorder_level: Qty
    incoming: Qty
    daily_usage: Qty | None
    usage_basis: Literal["forecast", "recent_sales", "none"]
    days_of_cover: float | None
    runs_out_on: date | None
    lead_time_days: int
    supplier_name: str | None
    level: RiskLevel
    reason: str


class Insight(BaseModel):
    """One explainable observation: the numbers behind it and where to act on it."""

    key: str
    category: Literal["sales", "inventory", "kitchen", "forecast", "menu"]
    severity: Literal["positive", "info", "warning", "critical"]
    title: str
    detail: str
    link: str | None = None
    action: str | None = None


class Dashboard(BaseModel):
    generated_at: datetime
    timezone: str
    today: SalesSummary | None = None
    comparison: PeriodComparison | None = None
    sales_last_14_days: list[DayBucket] = Field(default_factory=list)
    sales_by_hour_today: list[HourBucket] = Field(default_factory=list)
    top_products_7_days: list[ProductSales] = Field(default_factory=list)
    low_stock: list[LowStockItem] = Field(default_factory=list)
    recent_orders: list[RecentOrder] = Field(default_factory=list)
    kitchen: KitchenCounts | None = None
    forecast: ForecastSummary | None = None
    pending_recommendations: list[PendingRecommendation] = Field(default_factory=list)
    pending_recommendation_count: int = 0
    stock_at_risk: list[StockRisk] = Field(default_factory=list)  # the most urgent few
    stock_at_risk_count: int = 0  # all ingredients that are out, critical or need reordering soon
    stock_critical_count: int = 0  # out of stock, or will run out before a delivery can arrive
    insights: list[Insight] = Field(default_factory=list)

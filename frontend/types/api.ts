// Types mirroring the FastAPI response/request schemas (backend/app/schemas).
// Money is always integer minor units (satang); quantities are base units.

export type UUID = string;

export type RestaurantRole = "MANAGER" | "CASHIER" | "KITCHEN";
export type OrderType = "DINE_IN" | "TAKEAWAY";
export type OrderStatus = "DRAFT" | "CONFIRMED" | "PREPARING" | "READY" | "COMPLETED" | "CANCELLED";
export type PaymentStatus = "UNPAID" | "PARTIALLY_PAID" | "PAID" | "PARTIALLY_REFUNDED" | "REFUNDED";
export type TableStatus = "AVAILABLE" | "OCCUPIED" | "RESERVED" | "CLEANING";
export type BaseUnit = "g" | "ml" | "piece";
export type MovementType =
  | "OPENING"
  | "RECEIPT"
  | "PURCHASE_RECEIPT"
  | "ISSUE"
  | "ADJUSTMENT"
  | "WASTE"
  | "SALE"
  | "SALE_REVERSAL";
export type PurchaseOrderStatus = "DRAFT" | "SUBMITTED" | "PARTIALLY_RECEIVED" | "RECEIVED" | "CANCELLED";
export type RecommendationStatus = "PENDING" | "APPROVED" | "MODIFIED" | "REJECTED" | "COMPLETED";
export type DiscountKind = "PERCENT" | "FIXED";
export type PaymentMethodKind = "CASH" | "CARD" | "QR" | "OTHER";
export type SelectionType = "SINGLE" | "MULTIPLE";
export type KitchenStatus = "NEW" | "PREPARING" | "READY" | "COMPLETED";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Message {
  message: string;
}

// ------------------------------------------------------------------ auth
export interface User {
  id: UUID;
  email: string;
  full_name: string;
  is_active: boolean;
  is_platform_admin: boolean;
  preferred_language: string;
  last_login_at: string | null;
  created_at: string;
}

export interface Membership {
  restaurant_id: UUID;
  restaurant_name: string;
  role: RestaurantRole | null;
  permissions: string[];
  is_demo: boolean;
  restaurant_active: boolean;
}

export interface Me {
  user: User;
  memberships: Membership[];
}

export interface LoginResponse extends Me {
  csrf_token: string;
  expires_at: string;
}

export interface Staff {
  user_id: UUID;
  membership_id: UUID;
  email: string;
  full_name: string;
  role: RestaurantRole;
  membership_active: boolean;
  user_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

// ------------------------------------------------------------------ restaurant
export interface Restaurant {
  id: UUID;
  name: string;
  legal_name: string | null;
  branch_name: string | null;
  tax_id: string | null;
  address: string | null;
  phone: string | null;
  email: string | null;
  currency: string;
  timezone: string;
  locale: string;
  tax_rate_bps: number;
  tax_label: string;
  prices_include_tax: boolean;
  service_charge_bps: number;
  service_charge_taxable: boolean;
  service_charge_dine_in_only: boolean;
  max_cashier_discount_bps: number;
  allow_negative_stock: boolean;
  loyalty_enabled: boolean;
  loyalty_spend_per_point_minor: number;
  loyalty_point_value_minor: number;
  receipt_header: string | null;
  receipt_footer: string | null;
  order_number_prefix: string;
  is_active: boolean;
  is_demo: boolean;
  created_at: string;
}

export interface RestaurantSummary {
  id: UUID;
  name: string;
  branch_name: string | null;
  is_active: boolean;
  is_demo: boolean;
  created_at: string;
}

export interface PaymentMethod {
  id: UUID;
  code: string;
  name: string;
  kind: PaymentMethodKind;
  is_simulated: boolean;
  is_active: boolean;
  display_order: number;
}

export interface Discount {
  id: UUID;
  name: string;
  kind: DiscountKind;
  value: number;
  requires_manager: boolean;
  is_active: boolean;
}

export interface AuditLog {
  id: UUID;
  restaurant_id: UUID | null;
  actor_user_id: UUID | null;
  actor_email: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  request_id: string | null;
  created_at: string;
}

// ------------------------------------------------------------------ catalog
export interface Category {
  id: UUID;
  name: string;
  description: string | null;
  display_order: number;
  is_active: boolean;
  product_count: number;
  created_at: string;
  updated_at: string;
}

export interface ModifierOption {
  id: UUID;
  group_id: UUID;
  name: string;
  price_delta_minor: number;
  is_default: boolean;
  is_active: boolean;
  display_order: number;
  ingredient_id: UUID | null;
  ingredient_quantity: number | null;
}

export interface ModifierGroup {
  id: UUID;
  name: string;
  description: string | null;
  selection_type: SelectionType;
  min_select: number;
  max_select: number | null;
  display_order: number;
  is_active: boolean;
  options: ModifierOption[];
}

export interface Product {
  id: UUID;
  category_id: UUID;
  category_name: string | null;
  name: string;
  description: string | null;
  sku: string | null;
  image_url: string | null;
  price_minor: number;
  is_available: boolean;
  is_active: boolean;
  has_recipe: boolean;
  modifier_groups: ModifierGroup[];
  created_at: string;
  updated_at: string;
}

export interface TableOrderSummary {
  id: UUID;
  order_number: number;
  display_number: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  total_minor: number;
  item_count: number;
  created_at: string;
}

export interface DiningTable {
  id: UUID;
  name: string;
  capacity: number;
  zone: string | null;
  status: TableStatus;
  current_order_id: UUID | null;
  layout_x: number | null;
  layout_y: number | null;
  is_active: boolean;
  current_order: TableOrderSummary | null;
}

// ------------------------------------------------------------------ inventory
export interface IngredientUnit {
  id: UUID;
  unit_name: string;
  factor_to_base: number;
}

export interface Ingredient {
  id: UUID;
  name: string;
  sku: string | null;
  base_unit: BaseUnit;
  current_stock: number;
  reorder_level: number;
  safety_stock: number;
  average_cost_minor: number;
  stock_value_minor: number;
  default_supplier_id: UUID | null;
  default_supplier_name: string | null;
  is_active: boolean;
  is_low_stock: boolean;
  units: IngredientUnit[];
  allowed_units: string[];
  created_at: string;
  updated_at: string;
}

export interface Movement {
  id: UUID;
  ingredient_id: UUID;
  ingredient_name: string | null;
  base_unit: string | null;
  movement_type: MovementType;
  quantity: number;
  balance_after: number;
  unit_cost_minor: number | null;
  input_quantity: number | null;
  input_unit: string | null;
  reason: string | null;
  order_id: UUID | null;
  purchase_order_id: UUID | null;
  actor_user_id: UUID | null;
  actor_name: string | null;
  created_at: string;
}

export interface InventorySummary {
  ingredient_count: number;
  low_stock_count: number;
  out_of_stock_count: number;
  total_value_minor: number;
  valued_ingredient_count: number;
  unvalued_ingredient_count: number;
}

export interface RecipeItem {
  id: UUID;
  ingredient_id: UUID;
  ingredient_name: string;
  base_unit: BaseUnit;
  quantity: number;
  input_quantity: number;
  input_unit: string;
  waste_factor: number;
  effective_quantity: number;
  estimated_cost_minor: number;
}

export interface Recipe {
  id: UUID;
  product_id: UUID;
  product_name: string;
  version: number;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  items: RecipeItem[];
  estimated_cost_minor: number;
  selling_price_minor: number;
  estimated_margin_bps: number | null;
}

export interface RecipeSummary {
  product_id: UUID;
  product_name: string;
  category_name: string | null;
  price_minor: number;
  is_available: boolean;
  recipe_id: UUID | null;
  version: number | null;
  ingredient_count: number;
  estimated_cost_minor: number | null;
}

// ------------------------------------------------------------------ purchasing
export interface Supplier {
  id: UUID;
  name: string;
  contact_name: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  notes: string | null;
  lead_time_days: number;
  is_active: boolean;
  ingredient_count: number;
  open_purchase_orders: number;
  created_at: string;
}

export interface SupplierIngredient {
  id: UUID;
  supplier_id: UUID;
  ingredient_id: UUID;
  ingredient_name: string | null;
  base_unit: string | null;
  supplier_sku: string | null;
  unit_cost_minor: number | null;
  min_order_quantity: number | null;
  lead_time_days: number | null;
}

export interface PurchaseOrderItem {
  id: UUID;
  ingredient_id: UUID;
  ingredient_name: string | null;
  base_unit: string | null;
  quantity_ordered: number;
  quantity_received: number;
  quantity_remaining: number;
  input_quantity: number;
  input_unit: string;
  unit_cost_minor: number;
  line_total_minor: number;
}

export interface PurchaseOrderReceipt {
  id: UUID;
  notes: string | null;
  total_cost_minor: number;
  received_by: UUID | null;
  created_at: string;
  lines: { id: UUID; purchase_order_item_id: UUID; ingredient_id: UUID; quantity: number; unit_cost_minor: number }[];
}

export interface PurchaseOrder {
  id: UUID;
  po_number: number;
  display_number: string;
  supplier_id: UUID;
  supplier_name: string | null;
  status: PurchaseOrderStatus;
  expected_delivery_date: string | null;
  notes: string | null;
  estimated_total_minor: number;
  received_total_minor: number;
  created_by: UUID | null;
  submitted_at: string | null;
  received_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  created_at: string;
  updated_at: string;
  items: PurchaseOrderItem[];
  receipts: PurchaseOrderReceipt[];
}

export interface PurchaseOrderListItem {
  id: UUID;
  po_number: number;
  display_number: string;
  supplier_id: UUID;
  supplier_name: string;
  status: PurchaseOrderStatus;
  expected_delivery_date: string | null;
  estimated_total_minor: number;
  item_count: number;
  created_at: string;
}

// ------------------------------------------------------------------ orders
export interface OrderItemInput {
  product_id: UUID;
  quantity: number;
  modifier_option_ids: UUID[];
  notes?: string | null;
}

export interface DiscountInput {
  discount_id?: UUID;
  kind?: DiscountKind;
  value?: number;
  reason?: string;
}

export interface OrderDraftInput {
  order_type: OrderType;
  table_id?: UUID | null;
  customer_id?: UUID | null;
  notes?: string | null;
  items: OrderItemInput[];
  discount?: DiscountInput | null;
  loyalty_points_to_redeem?: number;
}

export interface OrderQuote {
  lines: {
    product_id: UUID;
    product_name: string;
    unit_price_minor: number;
    quantity: number;
    line_total_minor: number;
    modifiers: string[];
  }[];
  subtotal_minor: number;
  discount_minor: number;
  loyalty_discount_minor: number;
  service_charge_minor: number;
  tax_minor: number;
  total_minor: number;
  prices_include_tax: boolean;
  tax_rate_bps: number;
  service_charge_bps: number;
  discount_name: string | null;
  max_redeemable_points: number;
}

export interface OrderItem {
  id: UUID;
  product_id: UUID;
  product_name: string;
  product_sku: string | null;
  category_name: string | null;
  base_price_minor: number;
  unit_price_minor: number;
  quantity: number;
  line_total_minor: number;
  notes: string | null;
  recipe_id: UUID | null;
  modifiers: {
    id: UUID;
    modifier_option_id: UUID | null;
    group_name: string;
    option_name: string;
    price_delta_minor: number;
  }[];
}

export interface Payment {
  id: UUID;
  order_id: UUID;
  payment_method_id: UUID | null;
  method_code: string;
  method_name: string;
  method_kind: PaymentMethodKind;
  is_simulated: boolean;
  status: string;
  amount_minor: number;
  amount_tendered_minor: number | null;
  change_minor: number;
  refunded_minor: number;
  reference: string | null;
  recorded_by: UUID | null;
  created_at: string;
  verification_note: string;
}

export interface Refund {
  id: UUID;
  order_id: UUID;
  payment_id: UUID;
  amount_minor: number;
  reason: string;
  recorded_by: UUID | null;
  created_at: string;
}

export interface Order {
  id: UUID;
  order_number: number;
  display_number: string;
  order_type: OrderType;
  status: OrderStatus;
  payment_status: PaymentStatus;
  table_id: UUID | null;
  table_name: string | null;
  customer_id: UUID | null;
  customer_name: string | null;
  notes: string | null;
  discount_id: UUID | null;
  discount_name: string | null;
  discount_kind: DiscountKind | null;
  discount_value: number | null;
  discount_reason: string | null;
  loyalty_points_redeemed: number;
  subtotal_minor: number;
  discount_minor: number;
  loyalty_discount_minor: number;
  service_charge_minor: number;
  tax_minor: number;
  total_minor: number;
  amount_paid_minor: number;
  amount_refunded_minor: number;
  balance_due_minor: number;
  tax_rate_bps: number;
  service_charge_bps: number;
  prices_include_tax: boolean;
  stock_committed: boolean;
  created_by: UUID | null;
  created_by_name: string | null;
  confirmed_at: string | null;
  preparing_at: string | null;
  ready_at: string | null;
  completed_at: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  created_at: string;
  updated_at: string;
  items: OrderItem[];
  payments: Payment[];
  refunds: Refund[];
  allowed_transitions: OrderStatus[];
}

export interface OrderListItem {
  id: UUID;
  order_number: number;
  display_number: string;
  order_type: OrderType;
  status: OrderStatus;
  payment_status: PaymentStatus;
  table_name: string | null;
  customer_name: string | null;
  item_count: number;
  total_minor: number;
  amount_paid_minor: number;
  created_at: string;
  paid_at: string | null;
}

export interface Receipt {
  restaurant_name: string;
  legal_name: string | null;
  branch_name: string | null;
  tax_id: string | null;
  address: string | null;
  phone: string | null;
  header: string | null;
  footer: string | null;
  currency: string;
  timezone: string;
  order_id: UUID;
  display_number: string;
  order_type: OrderType;
  table_name: string | null;
  customer_name: string | null;
  cashier_name: string | null;
  created_at: string;
  paid_at: string | null;
  lines: {
    name: string;
    quantity: number;
    unit_price_minor: number;
    line_total_minor: number;
    modifiers: string[];
    notes: string | null;
  }[];
  subtotal_minor: number;
  discount_minor: number;
  discount_label: string | null;
  loyalty_discount_minor: number;
  loyalty_points_redeemed: number;
  service_charge_minor: number;
  service_charge_bps: number;
  tax_minor: number;
  tax_rate_bps: number;
  tax_label: string;
  prices_include_tax: boolean;
  total_minor: number;
  amount_paid_minor: number;
  amount_refunded_minor: number;
  balance_due_minor: number;
  payment_status: PaymentStatus;
  status: OrderStatus;
  payments: {
    method_name: string;
    amount_minor: number;
    amount_tendered_minor: number | null;
    change_minor: number;
    is_simulated: boolean;
    status: string;
    reference: string | null;
    created_at: string;
  }[];
  loyalty_points_earned: number | null;
  simulated_payment_notice: string | null;
}

export interface KitchenTicket {
  order_id: UUID;
  display_number: string;
  order_type: OrderType;
  label: string;
  kitchen_status: KitchenStatus;
  order_status: OrderStatus;
  notes: string | null;
  created_at: string;
  confirmed_at: string | null;
  preparing_at: string | null;
  ready_at: string | null;
  completed_at: string | null;
  items: { id: UUID; product_name: string; quantity: number; modifiers: string[]; notes: string | null }[];
}

// ------------------------------------------------------------------ customers
export interface CustomerLookup {
  id: UUID;
  name: string;
  phone_masked: string | null;
  loyalty_balance: number;
}

export interface Customer {
  id: UUID;
  name: string;
  phone: string | null;
  email: string | null;
  notes: string | null;
  loyalty_balance: number;
  created_at: string;
  updated_at: string;
  order_count: number;
  total_spent_minor: number;
  last_order_at: string | null;
}

export type CustomerAny = Customer | CustomerLookup;

export interface LoyaltyTransaction {
  id: UUID;
  customer_id: UUID;
  order_id: UUID | null;
  transaction_type: "EARN" | "REDEEM" | "ADJUST" | "REVERSAL";
  points: number;
  balance_after: number;
  reason: string | null;
  created_by: UUID | null;
  created_at: string;
}

// ------------------------------------------------------------------ analytics
export interface SalesSummary {
  range: { start_date: string; end_date: string; timezone: string; cutoff_time: string | null };
  order_count: number;
  items_sold: number;
  gross_sales_minor: number;
  discounts_minor: number;
  refunds_minor: number;
  net_sales_minor: number;
  tax_minor: number;
  service_charge_minor: number;
  total_billed_minor: number;
  total_collected_minor: number;
  average_order_value_minor: number;
  estimated_ingredient_cost_minor: number;
  estimated_gross_profit_minor: number | null;
  cost_data_complete: boolean;
  prices_include_tax: boolean;
}

export interface PeriodComparison {
  current: SalesSummary;
  previous: SalesSummary;
  net_sales_change_pct: number | null;
  order_count_change_pct: number | null;
  aov_change_pct: number | null;
}

export interface DayBucket {
  date: string;
  order_count: number;
  gross_sales_minor: number;
  net_sales_minor: number;
  total_billed_minor: number;
}

export interface HourBucket {
  hour: number;
  order_count: number;
  total_billed_minor: number;
}

export interface CategorySales {
  category_name: string;
  quantity: number;
  sales_minor: number;
  share_pct: number;
}

export interface ProductSales {
  product_id: UUID;
  product_name: string;
  category_name: string | null;
  quantity: number;
  sales_minor: number;
}

export interface PaymentShare {
  method_code: string;
  method_name: string;
  payment_count: number;
  amount_minor: number;
  refunded_minor: number;
  share_pct: number;
  is_simulated: boolean;
}

export interface IngredientUsage {
  ingredient_id: UUID;
  ingredient_name: string;
  base_unit: string;
  quantity: number;
  estimated_cost_minor: number;
  cost_known: boolean;
}

export interface SupplierSpend {
  supplier_id: UUID;
  supplier_name: string;
  deliveries: number;
  amount_minor: number;
}

export interface Dashboard {
  generated_at: string;
  timezone: string;
  today: SalesSummary | null;
  comparison: PeriodComparison | null;
  sales_last_14_days: DayBucket[];
  sales_by_hour_today: HourBucket[];
  top_products_7_days: ProductSales[];
  low_stock: { id: UUID; name: string; base_unit: string; current_stock: number; reorder_level: number }[];
  recent_orders: {
    id: UUID;
    display_number: string;
    order_type: OrderType;
    status: OrderStatus;
    payment_status: PaymentStatus;
    total_minor: number;
    created_at: string;
    table_name: string | null;
  }[];
  kitchen: { new: number; preparing: number; ready: number } | null;
  forecast: {
    run_id: UUID;
    model_name: string;
    created_at: string;
    target_date: string;
    total_predicted_items: number;
    top_products: { product_name: string; predicted_quantity: number }[];
    uses_demo_data: boolean;
    warnings: string[];
    covers_until: string | null;
    is_stale: boolean;
  } | null;
  pending_recommendations: {
    id: UUID;
    ingredient_name: string;
    suggested_quantity: number;
    unit: string;
    created_at: string;
  }[];
  pending_recommendation_count: number;
  stock_at_risk: StockRisk[];
  stock_at_risk_count: number;
  stock_critical_count: number;
  insights: Insight[];
}

export type InsightSeverity = "positive" | "info" | "warning" | "critical";

/** An explainable observation computed from the restaurant's data (no AI provider involved). */
export interface Insight {
  key: string;
  category: "sales" | "inventory" | "kitchen" | "forecast" | "menu";
  severity: InsightSeverity;
  title: string;
  detail: string;
  link: string | null;
  action: string | null;
}

export type StockRiskLevel = "out" | "critical" | "warning" | "ok";

export interface StockRisk {
  ingredient_id: UUID;
  ingredient_name: string;
  base_unit: string;
  current_stock: number;
  reorder_level: number;
  incoming: number;
  daily_usage: number | null;
  usage_basis: "forecast" | "recent_sales" | "none";
  days_of_cover: number | null;
  runs_out_on: string | null;
  lead_time_days: number;
  supplier_name: string | null;
  level: StockRiskLevel;
  reason: string;
}

export interface ProductSuggestion {
  product_id: UUID;
  product_name: string;
  kind: "ordered_together" | "customer_usual" | "popular_now";
  reason: string;
  score: number;
  evidence: Record<string, number>;
}

// ------------------------------------------------------------------ forecasting
export interface ModelInfo {
  name: string;
  label: string;
  description: string;
  min_history_days: number;
}

export interface ModelMetric {
  model_name: string;
  model_version: string;
  evaluation_points: number;
  mae: number | null;
  rmse: number | null;
  mape: number | null;
  mape_points: number;
  zero_actual_points: number;
  notes: string | null;
  is_selected: boolean;
}

export interface ForecastPoint {
  date: string;
  horizon_day: number;
  predicted_quantity: number;
  actual_quantity: number | null;
}

export interface ForecastRunSummary {
  id: UUID;
  model_name: string;
  model_version: string;
  selection_strategy: string;
  horizon_days: number;
  history_start: string | null;
  history_end: string | null;
  history_days: number;
  products_forecast: number;
  warnings: string[];
  uses_demo_data: boolean;
  created_at: string;
}

export interface ForecastRun extends ForecastRunSummary {
  parameters: Record<string, unknown>;
  metrics: ModelMetric[];
  covers_until: string | null;
  is_stale: boolean;
  products: {
    product_id: UUID;
    product_name: string;
    model_name: string;
    total_predicted: number;
    points: ForecastPoint[];
  }[];
  ingredients: {
    ingredient_id: UUID;
    ingredient_name: string;
    base_unit: string;
    total_predicted: number;
    points: ForecastPoint[];
  }[];
}

export interface ProductHistory {
  product_id: UUID;
  product_name: string;
  run_id: UUID | null;
  model_name: string | null;
  points: {
    date: string;
    actual_quantity: number | null;
    predicted_quantity: number | null;
    is_future: boolean;
    closed: boolean;
  }[];
}

export interface Recommendation {
  id: UUID;
  ingredient_id: UUID;
  ingredient_name: string | null;
  supplier_id: UUID | null;
  supplier_name: string | null;
  forecast_run_id: UUID | null;
  status: RecommendationStatus;
  current_stock: number;
  forecast_demand: number;
  safety_stock: number;
  incoming_quantity: number;
  lead_time_days: number;
  coverage_days: number;
  raw_quantity: number;
  suggested_quantity: number;
  approved_quantity: number | null;
  min_order_quantity: number | null;
  unit: string;
  reason: string;
  calculation: Record<string, unknown>;
  reviewed_by: UUID | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  purchase_order_id: UUID | null;
  created_at: string;
}

// ------------------------------------------------------------------ AI
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AssistantReply {
  answer: string;
  mode: "llm" | "offline";
  model: string | null;
  tools_used: { name: string; arguments: Record<string, unknown> }[];
  notice: string | null;
}

export interface AIStatus {
  llm_configured: boolean;
  model: string | null;
  available_tools: string[];
  message: string;
}

export interface CustomerFavourite {
  product_id: UUID;
  product_name: string;
  orders: number;
  quantity: number;
  last_ordered_at: string;
}

export type DemoRoleName = "MANAGER" | "CASHIER" | "KITCHEN";

export interface DemoInfo {
  enabled: boolean;
  restaurant_name: string | null;
  roles: { role: DemoRoleName; label: string; description: string }[];
}

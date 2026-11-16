# Database design

PostgreSQL 15+ with 37 tables, managed by Alembic (`backend/migrations`). Every
primary key is a UUID, except the two composite-key tables
`restaurant_counters` and `product_modifier_groups`. Every business table
carries `restaurant_id`, and uniqueness is scoped per restaurant.

## Conventions

| Topic | Rule |
| --- | --- |
| Money | `BIGINT` minor units (satang): `*_minor` columns |
| Unit costs | `NUMERIC(16,4)` minor units per base unit, so fractions of a satang per gram are representable |
| Quantities | `NUMERIC(14,3)` in the ingredient's base unit (`g`, `ml`, `piece`) |
| Rates | basis points: 700 = 7% (`tax_rate_bps`, `service_charge_bps`, percent discounts) |
| Time | `TIMESTAMPTZ` in UTC; reports convert to the restaurant's IANA time zone |
| Enums | stored as text with `CHECK` constraints (`ck_<table>_<enum>`) |
| Names | constraint naming convention `pk_`, `fk_`, `uq_`, `ix_`, `ck_` |
| Snapshots | order lines copy product name, SKU, category, prices and modifier names, so history survives menu edits |

## Entity overview

```
restaurants ─┬─ restaurant_memberships ── users ── user_sessions, password_reset_tokens
             ├─ categories ── products ─┬─ product_modifier_groups ── modifier_groups ── modifier_options
             │                          └─ recipes (versioned) ── recipe_items ── ingredients
             ├─ ingredients ─┬─ ingredient_units (pack sizes)
             │               ├─ inventory_movements (append-only ledger)
             │               └─ supplier_ingredients ── suppliers
             ├─ dining_tables
             ├─ customers ── loyalty_transactions (append-only ledger)
             ├─ orders ─┬─ order_items ── order_item_modifiers
             │          ├─ payments ── refunds
             │          └─ (inventory_movements, loyalty_transactions)
             ├─ purchase_orders ─┬─ purchase_order_items
             │                   └─ purchase_order_receipts ── purchase_order_receipt_lines
             ├─ forecast_runs ─┬─ forecast_model_metrics
             │                 └─ forecasts (per product or ingredient per day)
             ├─ reorder_recommendations
             ├─ payment_methods, discounts, restaurant_counters
             └─ audit_logs
```

## Tables

### Identity and tenancy

| Table | Purpose | Notable constraints |
| --- | --- | --- |
| `restaurants` | Tenant and its settings: tax, service charge, loyalty, receipt text, numbering, `is_demo` | range checks on rates and loyalty values |
| `users` | Accounts. `password_hash` is Argon2id; `is_platform_admin` | unique email (case-normalised) |
| `restaurant_memberships` | User ↔ restaurant with role MANAGER, CASHIER or KITCHEN | unique `(restaurant_id, user_id)` |
| `user_sessions` | Server-side sessions: HMAC hashes of the session and CSRF tokens, expiry, revocation, IP and user agent | unique `token_hash` |
| `password_reset_tokens` | Single-use, hashed, expiring reset tokens | unique `token_hash` |
| `audit_logs` | Who did what, when, from which request ID and IP | |
| `restaurant_counters` | Gap-free per-restaurant counters (order and PO numbers), incremented with `INSERT … ON CONFLICT … RETURNING` | PK `(restaurant_id, name)` |

### Menu

| Table | Purpose | Notable constraints |
| --- | --- | --- |
| `categories` | Menu sections | unique name per restaurant |
| `products` | Menu items: `price_minor`, availability, active/archived | unique SKU per restaurant; price ≥ 0 |
| `modifier_groups` | Option groups: SINGLE or MULTIPLE, min/max selections | `max ≥ min`, SINGLE implies at most 1 |
| `modifier_options` | Price delta; optionally consumes an ingredient quantity | unique name per group |
| `product_modifier_groups` | Which groups apply to a product, in order | PK `(product_id, modifier_group_id)` |
| `recipes` | Versioned recipe per product | unique `(product_id, version)`; partial unique index `uq_recipes_one_active_per_product` (one active version) |
| `recipe_items` | Ingredient quantity (base unit) plus the entered quantity and unit, and a waste factor | waste in `[0, 1)`; quantity > 0 |

### Front of house

| Table | Purpose | Notable constraints |
| --- | --- | --- |
| `dining_tables` | Status AVAILABLE, OCCUPIED, RESERVED or CLEANING; current order; zone; layout coordinates | unique name per restaurant |
| `customers` | Contact details and cached `loyalty_balance` | unique phone per restaurant; balance ≥ 0 |
| `loyalty_transactions` | EARN, REDEEM, ADJUST and REVERSAL entries with `balance_after` | append-only (trigger); points ≠ 0; partial unique index `uq_loyalty_order_earn_redeem` (at most one EARN and one REDEEM per order) |
| `orders` | Header: type, status, payment status, table, customer, discount snapshot, pricing snapshot (rates, inclusive flag), totals, paid and refunded amounts, lifecycle timestamps, `stock_committed`, idempotency key | unique number and idempotency key per restaurant; refunded ≤ paid |
| `order_items` | Line snapshot (name, SKU, category, base and unit price), quantity, notes, pinned `recipe_id` | quantity 1–999 |
| `order_item_modifiers` | Chosen options snapshot, including ingredient use | |
| `payment_methods` | Per-restaurant methods (CASH, CARD, QR, OTHER), all `is_simulated` | unique code per restaurant |
| `payments` | Amount, tendered, change, refunded, method snapshot, idempotency key | amount > 0; refunded ≤ amount |
| `refunds` | Refund against a payment, with reason and idempotency key | amount > 0 |
| `discounts` | Preset PERCENT (bps) or FIXED discounts; manager-only flag | percent ≤ 10000 |

### Inventory and purchasing

| Table | Purpose | Notable constraints |
| --- | --- | --- |
| `ingredients` | Base unit, cached `current_stock`, reorder level, safety stock, moving-average cost, default supplier | unique name and SKU per restaurant |
| `ingredient_units` | Pack units: `factor_to_base` base units per pack | factor > 0; unique per ingredient |
| `inventory_movements` | **Append-only ledger.** Type, signed quantity, `balance_after`, cost basis, entered quantity and unit, reason, links to order, PO and receipt, actor | quantity ≠ 0; UPDATE and DELETE rejected by trigger |
| `suppliers` | Contacts and default lead time | unique name per restaurant |
| `supplier_ingredients` | Price list: cost per base unit, minimum order quantity, lead time override | unique `(supplier_id, ingredient_id)` |
| `purchase_orders` | Status DRAFT, SUBMITTED, PARTIALLY_RECEIVED, RECEIVED or CANCELLED; expected date; estimated total; who submitted | unique PO number per restaurant |
| `purchase_order_items` | Ordered and received quantities (base unit), entered quantity and unit, cost | received in `[0, ordered]` |
| `purchase_order_receipts` | One delivery, with an idempotency key | unique key per restaurant |
| `purchase_order_receipt_lines` | Quantity and actual cost per line | quantity > 0 |

### Forecasting

| Table | Purpose |
| --- | --- |
| `forecast_runs` | Model used, selection strategy (auto or manual), horizon, history window, warnings, parameters, demo-data flag |
| `forecast_model_metrics` | Backtest MAE, RMSE, MAPE, points, zero-actual points excluded from MAPE, and the selected flag for each model |
| `forecasts` | Predicted quantity per day for a product *or* an ingredient (`ck_forecasts_one_target`) |
| `reorder_recommendations` | Inputs (stock, demand, safety stock, incoming, lead time, coverage), raw and suggested quantity, approved quantity, status, reviewer, note, resulting purchase order, `calculation` JSON |

## Integrity guarantees

* **Ledger immutability.** Migration `0002` installs
  `smartpos_reject_ledger_mutation()` as a `BEFORE UPDATE OR DELETE` trigger on
  `inventory_movements` and `loyalty_transactions`.
* **Ledger consistency.** Stock changes go through
  `services/inventory.apply_stock_changes`. It locks the affected ingredients
  (`SELECT … FOR UPDATE`, ordered by id), validates the net change, writes the
  movements and updates the cached balance in one transaction. Tests assert
  `current_stock = SUM(movements.quantity)`.
* **Idempotency.** `orders`, `payments`, `refunds` and `purchase_order_receipts`
  have a unique `(restaurant_id, idempotency_key)`. Services look the key up
  again after taking the row lock, so concurrent retries return the original
  result instead of a conflict.
* **Row level security.** Enabled on all 37 tables without permissive policies.
  Only the owning role (used by the API) can read or write, and Supabase's
  `anon` and `authenticated` roles see nothing.
* **Deletion policy.** Products with sales are archived, not deleted. Customers
  can be anonymised, which keeps order and loyalty history. Ledgers are never
  deleted.

## Migrations

```bash
cd backend
alembic upgrade head          # apply
alembic check                 # fail if models and migrations differ
alembic downgrade base        # roll everything back (development only)
alembic revision --autogenerate -m "describe change"   # then review the generated file
```

CI runs upgrade → check → downgrade → upgrade on a fresh database.

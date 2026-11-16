"""Ledger immutability triggers and row level security.

* inventory_movements and loyalty_transactions are append-only ledgers. A
  trigger rejects UPDATE and DELETE so corrections must be new, compensating
  entries. (TRUNCATE, used only by the isolated test suite, is not affected.)
* Row Level Security is enabled on every application table with no policies.
  The backend connects as the table owner, which bypasses RLS, so the
  application is unaffected. Any other role - for example Supabase's `anon` and
  `authenticated` roles used by the auto-generated Data API - is denied by
  default. Tenant isolation is enforced by the backend's authorised queries.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 18:10:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEDGER_TABLES = ("inventory_movements", "loyalty_transactions")

APP_TABLES = (
    "users", "user_sessions", "password_reset_tokens", "restaurants", "restaurant_counters",
    "restaurant_memberships", "audit_logs", "categories", "products", "product_modifier_groups",
    "modifier_groups", "modifier_options", "dining_tables", "payment_methods", "discounts",
    "customers", "orders", "order_items", "order_item_modifiers", "payments", "refunds",
    "ingredients", "ingredient_units", "recipes", "recipe_items", "inventory_movements",
    "suppliers", "supplier_ingredients", "purchase_orders", "purchase_order_items",
    "purchase_order_receipts", "purchase_order_receipt_lines", "loyalty_transactions",
    "forecast_runs", "forecasts", "forecast_model_metrics", "reorder_recommendations",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION smartpos_reject_ledger_mutation() RETURNS trigger AS $$
        BEGIN
            -- Allow foreign keys declared ON DELETE SET NULL to clear references
            -- (e.g. a deleted user) without permitting changes to ledger values.
            IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'inventory_movements'
               AND NEW.quantity = OLD.quantity AND NEW.balance_after = OLD.balance_after
               AND NEW.movement_type = OLD.movement_type AND NEW.ingredient_id = OLD.ingredient_id
               AND NEW.actor_user_id IS NULL THEN
                RETURN NEW;
            END IF;
            IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'loyalty_transactions'
               AND NEW.points = OLD.points AND NEW.balance_after = OLD.balance_after
               AND NEW.transaction_type = OLD.transaction_type AND NEW.customer_id = OLD.customer_id THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION '% is an append-only ledger; % is not allowed', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in LEDGER_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION smartpos_reject_ledger_mutation();"
        )
    for table in APP_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    for table in APP_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    for table in LEDGER_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table};")
    op.execute("DROP FUNCTION IF EXISTS smartpos_reject_ledger_mutation();")

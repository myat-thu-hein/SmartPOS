"""Fix the append-only ledger trigger.

The 0002 function referenced columns of both ledgers in one IF chain. PL/pgSQL
does not short-circuit record field access, so an UPDATE on either table failed
with "record new has no field ..." instead of the intended error, and the
ON DELETE SET NULL exception never worked for loyalty_transactions.

The replacement is table-agnostic: each trigger passes the nullable foreign
keys of its table as arguments, and an UPDATE is allowed only when those
columns are the only change and they become NULL (a referenced user or order
was deleted). Every other UPDATE, and every DELETE, is rejected.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12 02:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Table -> foreign keys declared ON DELETE SET NULL.
NULLABLE_REFERENCES = {
    "inventory_movements": ("actor_user_id",),
    "loyalty_transactions": ("order_id", "related_transaction_id", "created_by"),
}

FUNCTION = """
CREATE OR REPLACE FUNCTION smartpos_reject_ledger_mutation() RETURNS trigger AS $$
DECLARE
    new_row jsonb;
    old_row jsonb;
    col text;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        new_row := to_jsonb(NEW);
        old_row := to_jsonb(OLD);
        -- Ignore references that a deleted parent row set to NULL.
        FOREACH col IN ARRAY TG_ARGV LOOP
            IF new_row -> col = 'null'::jsonb THEN
                new_row := new_row - col;
                old_row := old_row - col;
            END IF;
        END LOOP;
        IF new_row = old_row THEN
            RETURN NEW;
        END IF;
    END IF;
    RAISE EXCEPTION '% is an append-only ledger; % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

OLD_FUNCTION = """
CREATE OR REPLACE FUNCTION smartpos_reject_ledger_mutation() RETURNS trigger AS $$
BEGIN
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


def _recreate_triggers(with_arguments: bool) -> None:
    for table, columns in NULLABLE_REFERENCES.items():
        args = ", ".join(f"'{c}'" for c in columns) if with_arguments else ""
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table};")
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION smartpos_reject_ledger_mutation({args});"
        )


def upgrade() -> None:
    op.execute(FUNCTION)
    _recreate_triggers(with_arguments=True)


def downgrade() -> None:
    op.execute(OLD_FUNCTION)
    _recreate_triggers(with_arguments=False)

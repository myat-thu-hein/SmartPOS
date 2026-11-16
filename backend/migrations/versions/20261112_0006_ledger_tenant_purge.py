"""Allow a deliberate, whole-restaurant purge through the ledger trigger.

Ledger rows stay append-only. The one exception is removing an entire
restaurant (used to refresh the public demo): the purge sets the
transaction-local setting ``smartpos.purge_restaurant`` to that restaurant's id,
and only DELETEs of rows belonging to that restaurant are then allowed.
UPDATEs keep the 0005 rules.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-12 04:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTION = """
CREATE OR REPLACE FUNCTION smartpos_reject_ledger_mutation() RETURNS trigger AS $$
DECLARE
    new_row jsonb;
    old_row jsonb;
    col text;
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting('smartpos.purge_restaurant', true) = OLD.restaurant_id::text THEN
        RETURN OLD;
    END IF;
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

# The 0005 function, restored on downgrade.
PREVIOUS_FUNCTION = """
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


def upgrade() -> None:
    op.execute(FUNCTION)


def downgrade() -> None:
    op.execute(PREVIOUS_FUNCTION)

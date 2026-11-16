"""The inventory and loyalty ledgers are append-only at the database level."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import Factory


def _expect_rejected(db, sql: str, **params) -> None:
    with pytest.raises(IntegrityError, match="append-only ledger"):
        db.execute(text(sql), params)
    db.rollback()


def test_ledger_rows_cannot_be_changed_or_deleted(client: TestClient, factory: Factory, db) -> None:
    rid = factory.restaurant("Ledger Thai")
    manager = factory.manager(rid)
    factory.ingredient(manager, "Rice", "g", stock=1000)
    movement = db.execute(text("SELECT id FROM inventory_movements WHERE restaurant_id = :r"), {"r": rid}).scalar_one()

    _expect_rejected(db, "UPDATE inventory_movements SET quantity = 5 WHERE id = :id", id=movement)
    _expect_rejected(db, "UPDATE inventory_movements SET reason = 'edited' WHERE id = :id", id=movement)
    _expect_rejected(db, "DELETE FROM inventory_movements WHERE id = :id", id=movement)
    # Clearing the actor is only allowed on its own (that is what ON DELETE SET NULL does).
    _expect_rejected(
        db, "UPDATE inventory_movements SET actor_user_id = NULL, quantity = 1 WHERE id = :id", id=movement
    )
    db.execute(text("UPDATE inventory_movements SET actor_user_id = NULL WHERE id = :id"), {"id": movement})
    db.commit()

    customer = client.post("/api/v1/customers", headers=manager.headers, json={"name": "Nok"}).json()
    adjust = client.post(
        f"/api/v1/loyalty/customers/{customer['id']}/adjust",
        headers=manager.headers,
        json={"points": 5, "reason": "Welcome bonus"},
    )
    assert adjust.status_code == 200, adjust.text
    tx = db.execute(
        text("SELECT id FROM loyalty_transactions WHERE customer_id = :c"), {"c": customer["id"]}
    ).scalar_one()
    _expect_rejected(db, "UPDATE loyalty_transactions SET points = 500 WHERE id = :id", id=tx)
    _expect_rejected(db, "DELETE FROM loyalty_transactions WHERE id = :id", id=tx)
    db.execute(text("UPDATE loyalty_transactions SET created_by = NULL WHERE id = :id"), {"id": tx})
    db.commit()

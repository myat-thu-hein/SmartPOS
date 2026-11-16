"""Dining tables."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext, require
from app.core.permissions import Permission
from app.db.session import get_db
from app.schemas.catalog import TableCreate, TableOut, TableStatusUpdate, TableUpdate
from app.schemas.common import Message
from app.services import tables as table_service

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("", response_model=list[TableOut])
def list_tables(
    include_inactive: bool = False,
    ctx: RestaurantContext = Depends(require(Permission.TABLES_READ)),
    db: Session = Depends(get_db),
) -> list[TableOut]:
    return table_service.list_tables(db, ctx, include_inactive)


@router.post("", response_model=TableOut, status_code=status.HTTP_201_CREATED)
def create_table(
    data: TableCreate, ctx: RestaurantContext = Depends(require(Permission.TABLES_WRITE)), db: Session = Depends(get_db)
) -> TableOut:
    return table_service.create_table(db, ctx, data)


@router.get("/{table_id}", response_model=TableOut)
def get_table(
    table_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.TABLES_READ)),
    db: Session = Depends(get_db),
) -> TableOut:
    return table_service.get_table_out(db, ctx, table_id)


@router.patch("/{table_id}", response_model=TableOut)
def update_table(
    table_id: uuid.UUID,
    data: TableUpdate,
    ctx: RestaurantContext = Depends(require(Permission.TABLES_WRITE)),
    db: Session = Depends(get_db),
) -> TableOut:
    return table_service.update_table(db, ctx, table_id, data)


@router.post("/{table_id}/status", response_model=TableOut, summary="Reserve, clean or free a table")
def set_status(
    table_id: uuid.UUID,
    data: TableStatusUpdate,
    ctx: RestaurantContext = Depends(require(Permission.TABLES_OPERATE)),
    db: Session = Depends(get_db),
) -> TableOut:
    return table_service.set_status(db, ctx, table_id, data.status)


@router.post(
    "/{table_id}/close",
    response_model=TableOut,
    summary="Close an occupied table once its orders are completed and paid",
)
def close_table(
    table_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.TABLES_OPERATE)),
    db: Session = Depends(get_db),
) -> TableOut:
    return table_service.close_table(db, ctx, table_id)


@router.delete("/{table_id}", response_model=Message)
def delete_table(
    table_id: uuid.UUID,
    ctx: RestaurantContext = Depends(require(Permission.TABLES_WRITE)),
    db: Session = Depends(get_db),
) -> Message:
    return Message(message=f"Table {table_service.delete_table(db, ctx, table_id)}.")

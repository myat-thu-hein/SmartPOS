"""Explainable inventory reorder recommendations.

Formula (all quantities in the ingredient's base unit)::

    coverage days     = supplier lead time + review period
    forecast demand   = forecast ingredient use over the coverage days
    raw quantity      = forecast demand + safety stock - current stock - incoming stock
    suggested         = max(0, raw quantity), rounded up to the supplier's minimum order multiple

"Incoming stock" is the outstanding quantity on submitted or partially received
purchase orders. Recommendations are only suggestions: a manager must approve,
modify or reject each one, and turning approved recommendations into purchase
orders creates DRAFT purchase orders that still need to be submitted manually.
Nothing is ordered or paid automatically.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.errors import Conflict, ValidationFailed
from app.core.permissions import Permission
from app.forecasting import service as forecast_service
from app.models import (
    Forecast,
    Ingredient,
    ReorderRecommendation,
    Supplier,
    SupplierIngredient,
    User,
)
from app.models.enums import ForecastTarget, RecommendationStatus
from app.repositories.tenant import get_owned, scoped
from app.schemas.forecast import (
    CreatePurchaseOrders,
    GenerateResult,
    ModifyRecommendation,
    PurchaseOrderCreated,
    RecommendationGenerate,
    RecommendationOut,
)
from app.schemas.purchasing import PurchaseOrderCreate, PurchaseOrderItemIn
from app.services import analytics, purchasing, realtime
from app.services.audit import record_audit
from app.services.inventory import convert
from app.services.units import quantize

DEFAULT_LEAD_TIME_DAYS = 2
OPEN_STATUSES = (RecommendationStatus.PENDING,)
APPROVED_STATUSES = (RecommendationStatus.APPROVED, RecommendationStatus.MODIFIED)


def round_up_to_multiple(quantity: Decimal, multiple: Decimal | None) -> Decimal:
    if quantity <= 0:
        return Decimal(0)
    if not multiple or multiple <= 0:
        return quantize(quantity)
    return quantize((quantity / multiple).to_integral_value(rounding=ROUND_CEILING) * multiple)


def calculate(
    current_stock: Decimal,
    forecast_demand: Decimal,
    safety_stock: Decimal,
    incoming: Decimal,
    min_order: Decimal | None,
) -> tuple[Decimal, Decimal]:
    """Return (raw quantity, suggested quantity)."""
    raw = quantize(forecast_demand + safety_stock - current_stock - incoming)
    return raw, round_up_to_multiple(max(raw, Decimal(0)), min_order)


def _fmt(value: Decimal, unit: str) -> str:
    text = f"{value.normalize():f}" if value == value.to_integral_value() else f"{value:.3f}".rstrip("0")
    return f"{text} {unit}"


SupplierTerms = tuple[Supplier | None, int, Decimal | None, str]


def supplier_terms(
    db: Session, restaurant_id: uuid.UUID, ingredients: Iterable[Ingredient]
) -> dict[uuid.UUID, SupplierTerms]:
    """Supplier, lead time (days), minimum order and where the lead time came from, per ingredient.

    The default supplier wins; otherwise the earliest price-list link. A lead time on the
    price list overrides the supplier's general lead time.
    """
    ingredients = list(ingredients)
    ids = [i.id for i in ingredients]
    links: dict[uuid.UUID, list[SupplierIngredient]] = defaultdict(list)
    for link in db.scalars(
        select(SupplierIngredient)
        .where(SupplierIngredient.restaurant_id == restaurant_id, SupplierIngredient.ingredient_id.in_(ids))
        .order_by(SupplierIngredient.created_at)
    ).all():
        links[link.ingredient_id].append(link)
    suppliers = {s.id: s for s in db.scalars(select(Supplier).where(Supplier.restaurant_id == restaurant_id)).all()}
    out: dict[uuid.UUID, SupplierTerms] = {}
    for ingredient in ingredients:
        supplier = suppliers.get(ingredient.default_supplier_id) if ingredient.default_supplier_id else None
        if supplier is not None:
            link = next((li for li in links[ingredient.id] if li.supplier_id == supplier.id), None)
        else:
            link = links[ingredient.id][0] if links[ingredient.id] else None
            supplier = suppliers.get(link.supplier_id) if link else None
        if link and link.lead_time_days is not None and supplier is not None:
            out[ingredient.id] = (supplier, link.lead_time_days, link.min_order_quantity, "supplier price list")
        elif supplier is not None:
            out[ingredient.id] = (
                supplier,
                supplier.lead_time_days,
                link.min_order_quantity if link else None,
                "supplier profile",
            )
        else:
            out[ingredient.id] = (
                None,
                DEFAULT_LEAD_TIME_DAYS,
                None,
                f"default ({DEFAULT_LEAD_TIME_DAYS} days, no supplier linked)",
            )
    return out


def generate(db: Session, ctx: RestaurantContext, data: RecommendationGenerate) -> GenerateResult:
    run = forecast_service.require_run(db, ctx, data.forecast_run_id)
    start = analytics.local_today(ctx) + timedelta(days=1)
    ingredient_ids = set(
        db.scalars(
            select(Forecast.ingredient_id).where(
                Forecast.run_id == run.id, Forecast.target_type == ForecastTarget.INGREDIENT
            )
        ).all()
    )
    ingredients = db.scalars(scoped(Ingredient, ctx.restaurant_id).where(Ingredient.is_active.is_(True))).all()
    incoming = purchasing.incoming_quantities(db, ctx.restaurant_id)
    terms = supplier_terms(db, ctx.restaurant_id, ingredients)
    created, skipped, notes = [], 0, []
    superseded = 0
    for ingredient in sorted(ingredients, key=lambda i: i.name):
        has_forecast = ingredient.id in ingredient_ids
        low = ingredient.current_stock <= ingredient.reorder_level
        if not has_forecast and not low:
            continue
        supplier, lead_time, moq, lead_source = terms[ingredient.id]
        coverage = lead_time + data.review_period_days
        demand, covered_days = forecast_service.ingredient_demand(db, run, ingredient.id, start, coverage)
        extrapolated = 0
        if has_forecast and covered_days < coverage and covered_days > 0:
            # The forecast horizon is shorter than the coverage period: extend it
            # with the average forecast daily demand and say so explicitly.
            extrapolated = coverage - covered_days
            demand = quantize(demand + demand / covered_days * extrapolated)
        on_order = quantize(incoming.get(ingredient.id, Decimal(0)))
        raw, suggested = calculate(ingredient.current_stock, demand, ingredient.safety_stock, on_order, moq)
        # Older pending suggestions for this ingredient are now stale.
        superseded += _supersede(db, ctx, ingredient.id)
        if suggested <= 0:
            skipped += 1
            continue
        unit = ingredient.base_unit.value
        parts = [
            f"Forecast use over the next {coverage} day(s) (lead time {lead_time} from {lead_source} + review "
            f"period {data.review_period_days}) is {_fmt(demand, unit)}"
            + (
                f", including {extrapolated} day(s) extrapolated beyond the {run.horizon_days}-day forecast"
                if extrapolated
                else ""
            )
            + ".",
            f"Need = {_fmt(demand, unit)} demand + {_fmt(ingredient.safety_stock, unit)} safety stock "
            f"- {_fmt(ingredient.current_stock, unit)} on hand - {_fmt(on_order, unit)} incoming "
            f"= {_fmt(raw, unit)}.",
        ]
        if not has_forecast:
            parts[0] = (
                f"Stock ({_fmt(ingredient.current_stock, unit)}) is at or below the reorder level "
                f"({_fmt(ingredient.reorder_level, unit)}); no forecast demand was available."
            )
        if suggested != raw:
            parts.append(
                f"Rounded up to {_fmt(suggested, unit)} to match the minimum order quantity of {_fmt(moq, unit)}."
                if moq
                else f"Suggested {_fmt(suggested, unit)}."
            )
        rec = ReorderRecommendation(
            restaurant_id=ctx.restaurant_id,
            ingredient_id=ingredient.id,
            forecast_run_id=run.id,
            supplier_id=supplier.id if supplier else None,
            status=RecommendationStatus.PENDING,
            current_stock=ingredient.current_stock,
            forecast_demand=demand,
            safety_stock=ingredient.safety_stock,
            incoming_quantity=on_order,
            lead_time_days=lead_time,
            coverage_days=coverage,
            raw_quantity=raw,
            suggested_quantity=suggested,
            min_order_quantity=moq,
            unit=unit,
            reason=" ".join(parts),
            calculation={
                "formula": "suggested = max(0, forecast_demand + safety_stock - current_stock - incoming), "
                "rounded up to the minimum order multiple",
                "forecast_demand": str(demand),
                "safety_stock": str(ingredient.safety_stock),
                "current_stock": str(ingredient.current_stock),
                "incoming": str(on_order),
                "raw": str(raw),
                "min_order_quantity": str(moq) if moq else None,
                "suggested": str(suggested),
                "lead_time_days": lead_time,
                "lead_time_source": lead_source,
                "review_period_days": data.review_period_days,
                "coverage_days": coverage,
                "forecast_days_used": covered_days,
                "extrapolated_days": extrapolated,
                "forecast_run_id": str(run.id),
                "forecast_model": run.model_name,
                "coverage_start": start.isoformat(),
            },
        )
        db.add(rec)
        created.append(rec)
    if not created:
        notes.append("No ingredient needs reordering for the coverage period.")
    if run.uses_demo_data:
        notes.append("Based on a forecast from synthetic demo data.")
    record_audit(
        db,
        action="recommendations.generated",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="forecast_run",
        entity_id=run.id,
        details={"created": len(created)},
        ip_address=ctx.ip,
    )
    realtime.emit(
        db, ctx.restaurant_id, "recommendations.generated", data={"created": len(created)}, actor_user_id=ctx.user_id
    )
    if created:
        realtime.notify(
            db,
            ctx.restaurant_id,
            kind="REORDER_SUGGESTIONS",
            title=f"{len(created)} reorder suggestion{'s' if len(created) != 1 else ''} to review",
            body=", ".join(
                sorted(db.scalars(select(Ingredient.name).where(Ingredient.id.in_([r.ingredient_id for r in created]))))
            )[:400],
            link="/forecasting?tab=recommendations",
            permission=Permission.RECOMMENDATIONS_REVIEW,
            actor_user_id=ctx.user_id,
        )
    db.commit()
    return GenerateResult(
        forecast_run_id=run.id,
        created=[_out(db, r) for r in created],
        superseded=superseded,
        skipped_without_need=skipped,
        notes=notes,
    )


def _supersede(db: Session, ctx: RestaurantContext, ingredient_id: uuid.UUID) -> int:
    old = db.scalars(
        scoped(ReorderRecommendation, ctx.restaurant_id).where(
            ReorderRecommendation.ingredient_id == ingredient_id,
            ReorderRecommendation.status == RecommendationStatus.PENDING,
        )
    ).all()
    for rec in old:
        rec.status = RecommendationStatus.REJECTED
        rec.review_note = "Superseded automatically by a newer calculation (no manager action)."
        rec.reviewed_at = datetime.now(UTC)
    return len(old)


def _out(db: Session, rec: ReorderRecommendation) -> RecommendationOut:
    out = RecommendationOut.model_validate(rec)
    out.ingredient_name = db.scalar(select(Ingredient.name).where(Ingredient.id == rec.ingredient_id))
    if rec.supplier_id:
        out.supplier_name = db.scalar(select(Supplier.name).where(Supplier.id == rec.supplier_id))
    if rec.reviewed_by:
        out.reviewer_name = db.scalar(select(User.full_name).where(User.id == rec.reviewed_by))
    return out


def list_recommendations(
    db: Session, ctx: RestaurantContext, statuses: list[RecommendationStatus] | None
) -> list[RecommendationOut]:
    stmt = scoped(ReorderRecommendation, ctx.restaurant_id).order_by(ReorderRecommendation.created_at.desc())
    if statuses:
        stmt = stmt.where(ReorderRecommendation.status.in_(statuses))
    return [_out(db, r) for r in db.scalars(stmt.limit(500)).all()]


def _get_pending(db: Session, ctx: RestaurantContext, rec_id: uuid.UUID) -> ReorderRecommendation:
    rec = get_owned(db, ReorderRecommendation, rec_id, ctx.restaurant_id, "Recommendation", for_update=True)
    if rec.status not in OPEN_STATUSES:
        raise Conflict(f"This recommendation is already {rec.status.value.lower()}.", code="already_reviewed")
    return rec


def _review(
    db: Session,
    ctx: RestaurantContext,
    rec: ReorderRecommendation,
    status: RecommendationStatus,
    note: str | None,
    quantity: Decimal | None = None,
) -> RecommendationOut:
    rec.status = status
    rec.reviewed_by = ctx.user_id
    rec.reviewed_at = datetime.now(UTC)
    rec.review_note = note
    if status in APPROVED_STATUSES:
        rec.approved_quantity = quantity if quantity is not None else rec.suggested_quantity
    record_audit(
        db,
        action=f"recommendation.{status.value.lower()}",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="recommendation",
        entity_id=rec.id,
        details={"approved_quantity": str(rec.approved_quantity) if rec.approved_quantity else None, "note": note},
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "recommendations.reviewed", entity_id=rec.id, actor_user_id=ctx.user_id)
    db.commit()
    return _out(db, rec)


def approve(db: Session, ctx: RestaurantContext, rec_id: uuid.UUID, note: str | None) -> RecommendationOut:
    return _review(db, ctx, _get_pending(db, ctx, rec_id), RecommendationStatus.APPROVED, note)


def reject(db: Session, ctx: RestaurantContext, rec_id: uuid.UUID, note: str | None) -> RecommendationOut:
    return _review(db, ctx, _get_pending(db, ctx, rec_id), RecommendationStatus.REJECTED, note)


def modify(db: Session, ctx: RestaurantContext, rec_id: uuid.UUID, data: ModifyRecommendation) -> RecommendationOut:
    rec = _get_pending(db, ctx, rec_id)
    ingredient = get_owned(db, Ingredient, rec.ingredient_id, ctx.restaurant_id, "Ingredient")
    quantity = convert(ingredient, data.quantity, data.unit)
    if quantity <= 0:
        raise ValidationFailed("Quantity must be positive.")
    return _review(db, ctx, rec, RecommendationStatus.MODIFIED, data.note, quantity)


def create_purchase_orders(
    db: Session, ctx: RestaurantContext, data: CreatePurchaseOrders
) -> list[PurchaseOrderCreated]:
    recs = db.scalars(
        scoped(ReorderRecommendation, ctx.restaurant_id)
        .where(ReorderRecommendation.id.in_(data.recommendation_ids))
        .with_for_update()
    ).all()
    if len(recs) != len(set(data.recommendation_ids)):
        raise ValidationFailed("One or more recommendations were not found.")
    not_approved = [str(r.id) for r in recs if r.status not in APPROVED_STATUSES]
    if not_approved:
        raise Conflict(
            "Only approved or modified recommendations can be turned into purchase orders.",
            code="not_approved",
            details={"recommendation_ids": not_approved},
        )
    no_supplier = [str(r.id) for r in recs if r.supplier_id is None]
    if no_supplier:
        raise ValidationFailed(
            "Link a supplier to these ingredients first.",
            code="no_supplier",
            details={"recommendation_ids": no_supplier},
        )
    by_supplier: dict[uuid.UUID, list[ReorderRecommendation]] = defaultdict(list)
    for rec in recs:
        by_supplier[rec.supplier_id].append(rec)  # type: ignore[index]
    created = []
    for supplier_id, group in by_supplier.items():
        supplier = get_owned(db, Supplier, supplier_id, ctx.restaurant_id, "Supplier")
        lead = max(r.lead_time_days for r in group)
        merged: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
        for rec in group:
            merged[rec.ingredient_id] += rec.approved_quantity or rec.suggested_quantity
        po = purchasing.create_purchase_order(
            db,
            ctx,
            PurchaseOrderCreate(
                supplier_id=supplier.id,
                expected_delivery_date=analytics.local_today(ctx) + timedelta(days=lead),
                notes="Created from approved reorder recommendations. Review and submit manually.",
                items=[PurchaseOrderItemIn(ingredient_id=i, quantity=q) for i, q in merged.items()],
            ),
            commit=False,
        )
        for rec in group:
            rec.status = RecommendationStatus.COMPLETED
            rec.purchase_order_id = po.id
        created.append(
            PurchaseOrderCreated(
                purchase_order_id=po.id,
                display_number=purchasing.po_display(po.po_number),
                supplier_name=supplier.name,
                recommendation_ids=[r.id for r in group],
            )
        )
    realtime.emit(db, ctx.restaurant_id, "recommendations.reviewed", actor_user_id=ctx.user_id)
    db.commit()
    return created

"""Versioned recipes linking products to ingredients.

Saving a recipe creates a new immutable version and deactivates the previous
one. Order items record the recipe version used for their stock deduction, so
historical consumption stays explainable after a recipe changes.
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import RestaurantContext
from app.core.errors import NotFound, ValidationFailed
from app.db.base import ZERO
from app.models import Category, Ingredient, Product, Recipe, RecipeItem
from app.repositories.tenant import get_owned, scoped
from app.schemas.inventory import RecipeItemOut, RecipeOut, RecipeSet, RecipeSummary
from app.services.audit import record_audit
from app.services.units import quantize, to_base


def effective_quantity(item: RecipeItem) -> Decimal:
    """Quantity consumed per serving including the preparation waste factor."""
    return quantize(item.quantity * (Decimal(1) + item.waste_factor))


def _recipe_query():
    return select(Recipe).options(selectinload(Recipe.items).selectinload(RecipeItem.ingredient))


def active_recipe(db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID) -> Recipe | None:
    return db.scalar(
        _recipe_query().where(
            Recipe.restaurant_id == restaurant_id, Recipe.product_id == product_id, Recipe.is_active.is_(True)
        )
    )


def active_recipes(db: Session, restaurant_id: uuid.UUID, product_ids: set[uuid.UUID]) -> dict[uuid.UUID, Recipe]:
    if not product_ids:
        return {}
    rows = db.scalars(
        _recipe_query().where(
            Recipe.restaurant_id == restaurant_id, Recipe.product_id.in_(product_ids), Recipe.is_active.is_(True)
        )
    ).all()
    return {r.product_id: r for r in rows}


def recipes_by_id(db: Session, recipe_ids: set[uuid.UUID]) -> dict[uuid.UUID, Recipe]:
    if not recipe_ids:
        return {}
    return {r.id: r for r in db.scalars(_recipe_query().where(Recipe.id.in_(recipe_ids))).all()}


def recipe_cost(recipe: Recipe) -> Decimal:
    return sum((effective_quantity(i) * i.ingredient.average_cost_minor for i in recipe.items), ZERO)


def recipe_out(recipe: Recipe, product: Product) -> RecipeOut:
    items = []
    for item in recipe.items:
        eff = effective_quantity(item)
        items.append(
            RecipeItemOut(
                id=item.id,
                ingredient_id=item.ingredient_id,
                ingredient_name=item.ingredient.name,
                base_unit=item.ingredient.base_unit,
                quantity=item.quantity,
                input_quantity=item.input_quantity,
                input_unit=item.input_unit,
                waste_factor=item.waste_factor,
                effective_quantity=eff,
                estimated_cost_minor=(eff * item.ingredient.average_cost_minor).quantize(
                    Decimal("0.01"), ROUND_HALF_UP
                ),
            )
        )
    cost = recipe_cost(recipe).quantize(Decimal("0.01"), ROUND_HALF_UP)
    margin = None
    if product.price_minor > 0 and all(i.ingredient.average_cost_minor > 0 for i in recipe.items):
        margin = int(
            ((Decimal(product.price_minor) - cost) / Decimal(product.price_minor) * 10000).quantize(
                Decimal(1), ROUND_HALF_UP
            )
        )
    return RecipeOut(
        id=recipe.id,
        product_id=product.id,
        product_name=product.name,
        version=recipe.version,
        is_active=recipe.is_active,
        notes=recipe.notes,
        created_at=recipe.created_at,
        items=items,
        estimated_cost_minor=cost,
        selling_price_minor=product.price_minor,
        estimated_margin_bps=margin,
    )


def list_recipe_summaries(db: Session, ctx: RestaurantContext) -> list[RecipeSummary]:
    products = db.scalars(
        scoped(Product, ctx.restaurant_id).where(Product.is_active.is_(True)).order_by(Product.name)
    ).all()
    categories = dict(
        db.execute(select(Category.id, Category.name).where(Category.restaurant_id == ctx.restaurant_id)).all()
    )
    recipes = active_recipes(db, ctx.restaurant_id, {p.id for p in products})
    out = []
    for product in products:
        recipe = recipes.get(product.id)
        out.append(
            RecipeSummary(
                product_id=product.id,
                product_name=product.name,
                category_name=categories.get(product.category_id),
                price_minor=product.price_minor,
                is_available=product.is_available,
                recipe_id=recipe.id if recipe else None,
                version=recipe.version if recipe else None,
                ingredient_count=len(recipe.items) if recipe else 0,
                estimated_cost_minor=recipe_cost(recipe).quantize(Decimal("0.01")) if recipe else None,
            )
        )
    return out


def get_product_recipe(db: Session, ctx: RestaurantContext, product_id: uuid.UUID) -> RecipeOut | None:
    """The product's active recipe, or None when it has none yet (a normal state, not an error)."""
    product = get_owned(db, Product, product_id, ctx.restaurant_id, "Product")
    recipe = active_recipe(db, ctx.restaurant_id, product.id)
    return recipe_out(recipe, product) if recipe is not None else None


def list_versions(db: Session, ctx: RestaurantContext, product_id: uuid.UUID) -> list[RecipeOut]:
    product = get_owned(db, Product, product_id, ctx.restaurant_id, "Product")
    rows = db.scalars(
        _recipe_query()
        .where(Recipe.restaurant_id == ctx.restaurant_id, Recipe.product_id == product.id)
        .order_by(Recipe.version.desc())
    ).all()
    return [recipe_out(r, product) for r in rows]


def set_recipe(db: Session, ctx: RestaurantContext, product_id: uuid.UUID, data: RecipeSet) -> RecipeOut:
    product = get_owned(db, Product, product_id, ctx.restaurant_id, "Product", for_update=True)
    ids = [i.ingredient_id for i in data.items]
    ingredients = {
        i.id: i
        for i in db.scalars(
            scoped(Ingredient, ctx.restaurant_id).where(Ingredient.id.in_(ids)).options(selectinload(Ingredient.units))
        ).all()
    }
    missing = [str(i) for i in ids if i not in ingredients]
    if missing:
        raise ValidationFailed("Unknown ingredient in recipe.", details={"ingredient_ids": missing})
    inactive = [ingredients[i].name for i in ids if not ingredients[i].is_active]
    if inactive:
        raise ValidationFailed(f"Inactive ingredients cannot be used: {', '.join(inactive)}.")

    new_items = []
    for item in data.items:
        ingredient = ingredients[item.ingredient_id]
        unit = item.unit or ingredient.base_unit.value
        base_qty = to_base(
            item.quantity, unit, ingredient.base_unit, {u.unit_name: u.factor_to_base for u in ingredient.units}
        )
        if base_qty <= 0:
            raise ValidationFailed(f"Quantity for {ingredient.name} is too small.")
        new_items.append(
            RecipeItem(
                ingredient_id=ingredient.id,
                quantity=base_qty,
                input_quantity=item.quantity,
                input_unit=unit,
                waste_factor=item.waste_factor,
            )
        )

    current = active_recipe(db, ctx.restaurant_id, product.id)
    if current is not None and _same_items(current, new_items) and current.notes == data.notes:
        return recipe_out(current, product)
    version = (db.scalar(select(func.max(Recipe.version)).where(Recipe.product_id == product.id)) or 0) + 1
    if current is not None:
        current.is_active = False
        db.flush()
    recipe = Recipe(
        restaurant_id=ctx.restaurant_id,
        product_id=product.id,
        version=version,
        notes=data.notes,
        created_by=ctx.user_id,
        items=new_items,
    )
    db.add(recipe)
    record_audit(
        db,
        action="recipe.saved",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="product",
        entity_id=product.id,
        details={"version": version},
        ip_address=ctx.ip,
    )
    db.commit()
    return recipe_out(active_recipe(db, ctx.restaurant_id, product.id), product)  # type: ignore[arg-type]


def _same_items(recipe: Recipe, items: list[RecipeItem]) -> bool:
    def key(i: RecipeItem) -> tuple:
        return (i.ingredient_id, quantize(i.quantity), Decimal(i.waste_factor).normalize())

    return sorted(map(key, recipe.items)) == sorted(map(key, items))


def remove_recipe(db: Session, ctx: RestaurantContext, product_id: uuid.UUID) -> None:
    product = get_owned(db, Product, product_id, ctx.restaurant_id, "Product")
    recipe = active_recipe(db, ctx.restaurant_id, product.id)
    if recipe is None:
        raise NotFound("This product has no recipe.")
    recipe.is_active = False
    record_audit(
        db,
        action="recipe.removed",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="product",
        entity_id=product.id,
        details={"version": recipe.version},
        ip_address=ctx.ip,
    )
    db.commit()

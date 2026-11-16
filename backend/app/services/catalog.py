"""Menu catalog: categories, products and modifier groups."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import RestaurantContext
from app.core.errors import Conflict, ValidationFailed
from app.core.permissions import Permission
from app.models import (
    Category,
    Ingredient,
    ModifierGroup,
    ModifierOption,
    OrderItem,
    Product,
    Recipe,
    product_modifier_groups,
)
from app.repositories.tenant import get_owned, scoped
from app.schemas.catalog import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ModifierGroupCreate,
    ModifierGroupOut,
    ModifierGroupUpdate,
    ModifierOptionCreate,
    ModifierOptionOut,
    ModifierOptionUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    validate_selection_rules,
)
from app.services import realtime
from app.services.audit import record_audit
from app.services.units import to_base

# --------------------------------------------------------------------------- categories


def _category_out(category: Category, count: int = 0) -> CategoryOut:
    out = CategoryOut.model_validate(category)
    out.product_count = count
    return out


def list_categories(db: Session, ctx: RestaurantContext, include_inactive: bool) -> list[CategoryOut]:
    counts = dict(
        db.execute(
            select(Product.category_id, func.count())
            .where(Product.restaurant_id == ctx.restaurant_id, Product.is_active.is_(True))
            .group_by(Product.category_id)
        ).all()
    )
    stmt = scoped(Category, ctx.restaurant_id)
    if not include_inactive:
        stmt = stmt.where(Category.is_active.is_(True))
    rows = db.scalars(stmt.order_by(Category.display_order, Category.name)).all()
    return [_category_out(c, counts.get(c.id, 0)) for c in rows]


def _unique_category_name(db: Session, ctx: RestaurantContext, name: str, exclude: uuid.UUID | None = None) -> None:
    stmt = scoped(Category, ctx.restaurant_id).where(func.lower(Category.name) == name.lower())
    if exclude:
        stmt = stmt.where(Category.id != exclude)
    if db.scalar(stmt):
        raise Conflict("A category with this name already exists.")


def create_category(db: Session, ctx: RestaurantContext, data: CategoryCreate) -> CategoryOut:
    _unique_category_name(db, ctx, data.name)
    category = Category(restaurant_id=ctx.restaurant_id, **data.model_dump())
    db.add(category)
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return _category_out(category)


def update_category(db: Session, ctx: RestaurantContext, category_id: uuid.UUID, data: CategoryUpdate) -> CategoryOut:
    category = get_owned(db, Category, category_id, ctx.restaurant_id, "Category")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name"):
        _unique_category_name(db, ctx, changes["name"], exclude=category.id)
    for field, value in changes.items():
        if value is not None or field == "description":
            setattr(category, field, value)
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return _category_out(category)


def delete_category(db: Session, ctx: RestaurantContext, category_id: uuid.UUID) -> None:
    category = get_owned(db, Category, category_id, ctx.restaurant_id, "Category")
    if db.scalar(select(func.count()).select_from(Product).where(Product.category_id == category.id)):
        raise Conflict(
            "This category still contains products. Move or archive them, or deactivate the category instead.",
            code="category_not_empty",
        )
    db.delete(category)
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()


# --------------------------------------------------------------------------- products


def _product_query(ctx: RestaurantContext):
    return scoped(Product, ctx.restaurant_id).options(
        selectinload(Product.category),
        selectinload(Product.modifier_groups).selectinload(ModifierGroup.options),
    )


def product_out(
    product: Product, recipe_products: set[uuid.UUID] | None = None, include_inactive_modifiers: bool = False
) -> ProductOut:
    out = ProductOut.model_validate(product)
    out.category_name = product.category.name if product.category else None
    out.has_recipe = product.id in (recipe_products or set())
    groups = []
    for group in product.modifier_groups:
        if not group.is_active and not include_inactive_modifiers:
            continue
        g = ModifierGroupOut.model_validate(group)
        if not include_inactive_modifiers:
            g.options = [o for o in g.options if o.is_active]
        groups.append(g)
    out.modifier_groups = groups
    return out


def _products_with_recipes(db: Session, ctx: RestaurantContext) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(Recipe.product_id).where(Recipe.restaurant_id == ctx.restaurant_id, Recipe.is_active.is_(True))
        ).all()
    )


def list_products(
    db: Session,
    ctx: RestaurantContext,
    *,
    category_id: uuid.UUID | None,
    search: str | None,
    available_only: bool,
    include_inactive: bool,
) -> list[ProductOut]:
    stmt = _product_query(ctx)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if available_only:
        stmt = stmt.where(Product.is_available.is_(True))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    recipes = _products_with_recipes(db, ctx)
    rows = db.scalars(stmt.order_by(Product.name)).all()
    return [product_out(p, recipes) for p in rows]


def get_product(db: Session, ctx: RestaurantContext, product_id: uuid.UUID) -> Product:
    return get_owned(
        db,
        Product,
        product_id,
        ctx.restaurant_id,
        "Product",
        options=(
            selectinload(Product.category),
            selectinload(Product.modifier_groups).selectinload(ModifierGroup.options),
        ),
    )


def get_product_out(db: Session, ctx: RestaurantContext, product_id: uuid.UUID) -> ProductOut:
    product = get_product(db, ctx, product_id)
    return product_out(
        product, _products_with_recipes(db, ctx), include_inactive_modifiers=ctx.can(Permission.MENU_WRITE)
    )


def _check_sku(db: Session, ctx: RestaurantContext, sku: str | None, exclude: uuid.UUID | None = None) -> None:
    if not sku:
        return
    stmt = scoped(Product, ctx.restaurant_id).where(Product.sku == sku)
    if exclude:
        stmt = stmt.where(Product.id != exclude)
    if db.scalar(stmt):
        raise Conflict("Another product already uses this SKU.")


def _set_modifier_groups(db: Session, ctx: RestaurantContext, product: Product, group_ids: list[uuid.UUID]) -> None:
    if len(group_ids) != len(set(group_ids)):
        raise ValidationFailed("Modifier groups must not repeat.")
    groups = db.scalars(scoped(ModifierGroup, ctx.restaurant_id).where(ModifierGroup.id.in_(group_ids))).all()
    if len(groups) != len(group_ids):
        raise ValidationFailed("One or more modifier groups do not exist in this restaurant.")
    db.execute(delete(product_modifier_groups).where(product_modifier_groups.c.product_id == product.id))
    if group_ids:
        db.execute(
            insert(product_modifier_groups),
            [
                {"product_id": product.id, "modifier_group_id": gid, "display_order": index}
                for index, gid in enumerate(group_ids)
            ],
        )
    db.expire(product, ["modifier_groups"])


def create_product(db: Session, ctx: RestaurantContext, data: ProductCreate) -> ProductOut:
    get_owned(db, Category, data.category_id, ctx.restaurant_id, "Category")
    _check_sku(db, ctx, data.sku)
    product = Product(
        restaurant_id=ctx.restaurant_id,
        category_id=data.category_id,
        name=data.name,
        description=data.description,
        sku=data.sku,
        image_url=str(data.image_url) if data.image_url else None,
        price_minor=data.price_minor,
        is_available=data.is_available,
    )
    db.add(product)
    db.flush()
    _set_modifier_groups(db, ctx, product, data.modifier_group_ids)
    record_audit(
        db,
        action="product.created",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="product",
        entity_id=product.id,
        details={"price_minor": data.price_minor},
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return get_product_out(db, ctx, product.id)


def update_product(db: Session, ctx: RestaurantContext, product_id: uuid.UUID, data: ProductUpdate) -> ProductOut:
    product = get_product(db, ctx, product_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("category_id"):
        get_owned(db, Category, changes["category_id"], ctx.restaurant_id, "Category")
    if "sku" in changes:
        _check_sku(db, ctx, changes["sku"], exclude=product.id)
    if "image_url" in changes and changes["image_url"] is not None:
        changes["image_url"] = str(changes["image_url"])
    audit: dict[str, object] = {}
    for field, value in changes.items():
        if value is None and field not in {"description", "sku", "image_url"}:
            continue
        if field == "price_minor" and value != product.price_minor:
            audit["price_minor"] = {"from": product.price_minor, "to": value}
        setattr(product, field, value)
    if audit or "is_active" in changes or "is_available" in changes:
        audit.update({k: changes[k] for k in ("is_active", "is_available") if k in changes})
        record_audit(
            db,
            action="product.updated",
            actor_user_id=ctx.user_id,
            restaurant_id=ctx.restaurant_id,
            entity_type="product",
            entity_id=product.id,
            details=audit,
            ip_address=ctx.ip,
        )
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return get_product_out(db, ctx, product.id)


def set_product_modifier_groups(
    db: Session, ctx: RestaurantContext, product_id: uuid.UUID, group_ids: list[uuid.UUID]
) -> ProductOut:
    product = get_product(db, ctx, product_id)
    _set_modifier_groups(db, ctx, product, group_ids)
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return get_product_out(db, ctx, product.id)


def archive_or_delete_product(db: Session, ctx: RestaurantContext, product_id: uuid.UUID) -> str:
    """Products that were ever sold are archived to keep history intact."""
    product = get_product(db, ctx, product_id)
    sold = db.scalar(select(func.count()).select_from(OrderItem).where(OrderItem.product_id == product.id))
    if sold:
        product.is_active = False
        product.is_available = False
        outcome = "archived"
    else:
        db.delete(product)
        outcome = "deleted"
    record_audit(
        db,
        action=f"product.{outcome}",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="product",
        entity_id=product_id,
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return outcome


# --------------------------------------------------------------------------- modifiers


def _group_query(ctx: RestaurantContext):
    return scoped(ModifierGroup, ctx.restaurant_id).options(selectinload(ModifierGroup.options))


def list_modifier_groups(db: Session, ctx: RestaurantContext, include_inactive: bool) -> list[ModifierGroupOut]:
    stmt = _group_query(ctx)
    if not include_inactive:
        stmt = stmt.where(ModifierGroup.is_active.is_(True))
    rows = db.scalars(stmt.order_by(ModifierGroup.display_order, ModifierGroup.name)).all()
    out = []
    for group in rows:
        g = ModifierGroupOut.model_validate(group)
        if not include_inactive:
            g.options = [o for o in g.options if o.is_active]
        out.append(g)
    return out


def get_group(db: Session, ctx: RestaurantContext, group_id: uuid.UUID) -> ModifierGroup:
    return get_owned(
        db, ModifierGroup, group_id, ctx.restaurant_id, "Modifier group", options=(selectinload(ModifierGroup.options),)
    )


def _option_ingredient(db: Session, ctx: RestaurantContext, ingredient_id: uuid.UUID | None, quantity, unit):
    if ingredient_id is None:
        return None, None
    ingredient = get_owned(
        db, Ingredient, ingredient_id, ctx.restaurant_id, "Ingredient", options=(selectinload(Ingredient.units),)
    )
    base_qty = to_base(
        quantity,
        unit or ingredient.base_unit.value,
        ingredient.base_unit,
        {u.unit_name: u.factor_to_base for u in ingredient.units},
    )
    return ingredient.id, base_qty


def _build_option(db: Session, ctx: RestaurantContext, group: ModifierGroup, data: ModifierOptionCreate) -> None:
    if any(o.name.lower() == data.name.lower() for o in group.options):
        raise Conflict(f"The option '{data.name}' already exists in this group.")
    ingredient_id, qty = _option_ingredient(db, ctx, data.ingredient_id, data.ingredient_quantity, data.ingredient_unit)
    group.options.append(
        ModifierOption(
            restaurant_id=ctx.restaurant_id,
            name=data.name,
            price_delta_minor=data.price_delta_minor,
            is_default=data.is_default,
            display_order=data.display_order,
            ingredient_id=ingredient_id,
            ingredient_quantity=qty,
        )
    )


def create_modifier_group(db: Session, ctx: RestaurantContext, data: ModifierGroupCreate) -> ModifierGroupOut:
    if db.scalar(scoped(ModifierGroup, ctx.restaurant_id).where(func.lower(ModifierGroup.name) == data.name.lower())):
        raise Conflict("A modifier group with this name already exists.")
    group = ModifierGroup(
        restaurant_id=ctx.restaurant_id,
        name=data.name,
        description=data.description,
        selection_type=data.selection_type,
        min_select=data.min_select,
        max_select=1 if data.selection_type.value == "SINGLE" else data.max_select,
        display_order=data.display_order,
    )
    db.add(group)
    for option in data.options:
        _build_option(db, ctx, group, option)
    _check_defaults(group)
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return ModifierGroupOut.model_validate(get_group(db, ctx, group.id))


def _check_defaults(group: ModifierGroup) -> None:
    active = [o for o in group.options if o.is_active]
    defaults = [o for o in active if o.is_default]
    if group.max_select is not None and len(defaults) > group.max_select:
        raise ValidationFailed("More default options than the group allows.")
    if group.min_select > len(active) and active:
        raise ValidationFailed("The group requires more selections than it has active options.")


def update_modifier_group(
    db: Session, ctx: RestaurantContext, group_id: uuid.UUID, data: ModifierGroupUpdate
) -> ModifierGroupOut:
    group = get_group(db, ctx, group_id)
    changes = data.model_dump(exclude_unset=True, exclude={"clear_max_select"})
    for field, value in changes.items():
        if value is not None or field == "description":
            setattr(group, field, value)
    if data.clear_max_select:
        group.max_select = None
    if group.selection_type.value == "SINGLE":
        group.max_select = 1
    try:
        validate_selection_rules(group.selection_type, group.min_select, group.max_select)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    _check_defaults(group)
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return ModifierGroupOut.model_validate(get_group(db, ctx, group.id))


def add_modifier_option(
    db: Session, ctx: RestaurantContext, group_id: uuid.UUID, data: ModifierOptionCreate
) -> ModifierGroupOut:
    group = get_group(db, ctx, group_id)
    _build_option(db, ctx, group, data)
    _check_defaults(group)
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return ModifierGroupOut.model_validate(get_group(db, ctx, group.id))


def update_modifier_option(
    db: Session, ctx: RestaurantContext, option_id: uuid.UUID, data: ModifierOptionUpdate
) -> ModifierOptionOut:
    option = get_owned(db, ModifierOption, option_id, ctx.restaurant_id, "Modifier option")
    changes = data.model_dump(
        exclude_unset=True, exclude={"ingredient_id", "ingredient_quantity", "ingredient_unit", "clear_ingredient"}
    )
    if changes.get("name") and changes["name"].lower() != option.name.lower():
        siblings = db.scalars(
            select(ModifierOption).where(ModifierOption.group_id == option.group_id, ModifierOption.id != option.id)
        ).all()
        if any(s.name.lower() == changes["name"].lower() for s in siblings):
            raise Conflict("Another option in this group already has this name.")
    for field, value in changes.items():
        if value is not None:
            setattr(option, field, value)
    if data.clear_ingredient:
        option.ingredient_id = None
        option.ingredient_quantity = None
    elif data.ingredient_id is not None:
        if data.ingredient_quantity is None:
            raise ValidationFailed("ingredient_quantity is required with ingredient_id.")
        option.ingredient_id, option.ingredient_quantity = _option_ingredient(
            db, ctx, data.ingredient_id, data.ingredient_quantity, data.ingredient_unit
        )
    group = get_group(db, ctx, option.group_id)
    _check_defaults(group)
    realtime.emit(db, ctx.restaurant_id, "menu.changed", actor_user_id=ctx.user_id)
    db.commit()
    return ModifierOptionOut.model_validate(option)

"""Development-only demo data.

Creates a clearly labelled demo restaurant ("Baan Siam (Demo)", is_demo=True)
with a Thai menu, recipes, ingredients, suppliers, customers, tables and about
120 days of SYNTHETIC sales history so analytics and forecasting can be
demonstrated. All stock changes are written as inventory movements with
consistent running balances, and restocking happens through received purchase
orders.

Usage (from backend/):
    python -m app.seed.demo                 # seed if no demo restaurant exists
    python -m app.seed.demo --refresh       # replace only the demo restaurant with fresh history
    python -m app.seed.demo --reset --yes   # wipe ALL local data, then seed

Safety: refuses to run when APP_ENV=production, except to seed or refresh the
demo restaurant of a deployment that is a public demo (DEMO_LOGIN_ENABLED=true).
--reset never runs in production, and refuses a non-local database unless
--allow-remote is given. --refresh only ever deletes restaurants marked is_demo.
Passwords: set DEMO_PASSWORD, otherwise a random one is generated and printed.
"""

from __future__ import annotations

import argparse
import math
import random
import secrets
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import app.models as m
from app.core.config import get_settings
from app.core.permissions import permissions_for
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session_factory
from app.models.enums import (
    BaseUnit,
    DiscountKind,
    LoyaltyTransactionType,
    MovementType,
    OrderStatus,
    OrderType,
    PaymentRecordStatus,
    PaymentStatus,
    PurchaseOrderStatus,
    RestaurantRole,
    SelectionType,
    TableStatus,
)
from app.services.pricing import DiscountSpec, PricingSettings, calculate, loyalty_points_earned
from app.services.restaurants import initialise_restaurant_defaults

DEMO_NAME = "Baan Siam (Demo)"
TZ = ZoneInfo("Asia/Bangkok")
HISTORY_DAYS = 120
DOW_FACTOR = [0.7, 0.75, 0.85, 0.95, 1.25, 1.55, 1.35]  # Monday..Sunday

# name, unit, cost per base unit (satang), supplier key, pack units
INGREDIENTS = [
    ("Rice noodles", BaseUnit.GRAM, "0.9", "market", {}),
    ("Jasmine rice", BaseUnit.GRAM, "0.45", "market", {"sack": "5000"}),
    ("Sticky rice", BaseUnit.GRAM, "0.6", "market", {}),
    ("Egg", BaseUnit.PIECE, "450", "farm", {"tray": "30"}),
    ("Shrimp", BaseUnit.GRAM, "4.2", "seafood", {}),
    ("Chicken thigh", BaseUnit.GRAM, "1.3", "farm", {}),
    ("Pork shoulder", BaseUnit.GRAM, "1.6", "farm", {}),
    ("Tofu", BaseUnit.GRAM, "0.8", "market", {}),
    ("Bean sprouts", BaseUnit.GRAM, "0.5", "market", {}),
    ("Peanuts", BaseUnit.GRAM, "1.2", "market", {}),
    ("Fish sauce", BaseUnit.MILLILITRE, "0.9", "market", {"bottle": "700"}),
    ("Pad Thai sauce", BaseUnit.MILLILITRE, "1.1", "market", {}),
    ("Coconut milk", BaseUnit.MILLILITRE, "0.7", "market", {}),
    ("Green curry paste", BaseUnit.GRAM, "2.0", "market", {}),
    ("Red curry paste", BaseUnit.GRAM, "2.0", "market", {}),
    ("Thai basil", BaseUnit.GRAM, "2.5", "farm", {}),
    ("Garlic", BaseUnit.GRAM, "1.0", "market", {}),
    ("Bird's eye chili", BaseUnit.GRAM, "2.2", "farm", {}),
    ("Lime", BaseUnit.PIECE, "300", "farm", {}),
    ("Green papaya", BaseUnit.GRAM, "0.4", "farm", {}),
    ("Thai tea leaves", BaseUnit.GRAM, "3.0", "market", {}),
    ("Condensed milk", BaseUnit.MILLILITRE, "1.0", "market", {}),
    ("Sugar", BaseUnit.GRAM, "0.3", "market", {}),
    ("Mango", BaseUnit.PIECE, "2500", "farm", {}),
    ("Young coconut", BaseUnit.PIECE, "2000", "farm", {}),
]

# category, name, price (THB, VAT inclusive), popularity, recipe [(ingredient, qty)], modifiers
# Dishes guests tend to order together: (companion, probability it is added).
PAIRINGS: dict[str, tuple[tuple[str, float], ...]] = {
    "Green Curry Chicken": (("Steamed Jasmine Rice", 0.7),),
    "Red Curry Pork": (("Steamed Jasmine Rice", 0.7),),
    "Tom Yum Goong": (("Steamed Jasmine Rice", 0.55),),
    "Pad Krapow Chicken": (("Steamed Jasmine Rice", 0.4),),
    "Som Tam Thai": (("Thai Iced Tea", 0.45), ("Young Coconut", 0.2)),
    "Pad Thai Goong": (("Thai Iced Tea", 0.4),),
    "Shrimp Fried Rice": (("Lime Soda", 0.3),),
}

MENU = [
    (
        "Noodles / ก๋วยเตี๋ยว",
        "Pad Thai Goong (ผัดไทยกุ้ง)",
        120,
        10,
        [
            ("Rice noodles", 100),
            ("Egg", 1),
            ("Shrimp", 80),
            ("Bean sprouts", 50),
            ("Peanuts", 10),
            ("Pad Thai sauce", 30),
        ],
        ["spice", "extras"],
    ),
    (
        "Noodles / ก๋วยเตี๋ยว",
        "Pad See Ew Chicken (ผัดซีอิ๊วไก่)",
        100,
        6,
        [("Rice noodles", 120), ("Chicken thigh", 80), ("Egg", 1), ("Garlic", 5), ("Fish sauce", 10)],
        ["extras"],
    ),
    (
        "Soups & Curries / ต้มและแกง",
        "Tom Yum Goong (ต้มยำกุ้ง)",
        150,
        7,
        [("Shrimp", 100), ("Lime", 1), ("Bird's eye chili", 5), ("Fish sauce", 15)],
        ["spice"],
    ),
    (
        "Soups & Curries / ต้มและแกง",
        "Green Curry Chicken (แกงเขียวหวานไก่)",
        130,
        7,
        [
            ("Chicken thigh", 100),
            ("Green curry paste", 30),
            ("Coconut milk", 150),
            ("Thai basil", 5),
            ("Jasmine rice", 150),
        ],
        ["spice"],
    ),
    (
        "Soups & Curries / ต้มและแกง",
        "Red Curry Pork (แกงเผ็ดหมู)",
        130,
        4,
        [("Pork shoulder", 100), ("Red curry paste", 30), ("Coconut milk", 150), ("Jasmine rice", 150)],
        ["spice"],
    ),
    (
        "Rice Dishes / อาหารจานเดียว",
        "Pad Krapow Chicken (ผัดกะเพราไก่)",
        90,
        11,
        [
            ("Chicken thigh", 120),
            ("Thai basil", 10),
            ("Garlic", 5),
            ("Bird's eye chili", 5),
            ("Jasmine rice", 150),
            ("Fish sauce", 10),
        ],
        ["spice", "extras"],
    ),
    (
        "Rice Dishes / อาหารจานเดียว",
        "Shrimp Fried Rice (ข้าวผัดกุ้ง)",
        100,
        6,
        [("Jasmine rice", 200), ("Shrimp", 60), ("Egg", 1), ("Garlic", 5), ("Fish sauce", 10)],
        ["extras"],
    ),
    (
        "Rice Dishes / อาหารจานเดียว",
        "Garlic Tofu (เต้าหู้ผัดกระเทียม)",
        90,
        2,
        [("Tofu", 150), ("Garlic", 10), ("Jasmine rice", 150)],
        [],
    ),
    (
        "Salads / ยำและส้มตำ",
        "Som Tam Thai (ส้มตำไทย)",
        80,
        6,
        [
            ("Green papaya", 150),
            ("Lime", 1),
            ("Bird's eye chili", 5),
            ("Peanuts", 10),
            ("Fish sauce", 15),
            ("Sugar", 10),
        ],
        ["spice"],
    ),
    (
        "Drinks / เครื่องดื่ม",
        "Thai Iced Tea (ชาเย็น)",
        60,
        9,
        [("Thai tea leaves", 10), ("Condensed milk", 40), ("Sugar", 15)],
        ["size"],
    ),
    ("Drinks / เครื่องดื่ม", "Lime Soda (โซดามะนาว)", 50, 4, [("Lime", 1), ("Sugar", 20)], []),
    ("Drinks / เครื่องดื่ม", "Young Coconut (มะพร้าวอ่อน)", 70, 3, [("Young coconut", 1)], []),
    ("Drinks / เครื่องดื่ม", "Drinking Water (น้ำดื่ม)", 20, 5, [], []),
    (
        "Desserts / ของหวาน",
        "Mango Sticky Rice (ข้าวเหนียวมะม่วง)",
        120,
        4,
        [("Mango", 1), ("Sticky rice", 120), ("Coconut milk", 60), ("Sugar", 15)],
        [],
    ),
    ("Rice Dishes / อาหารจานเดียว", "Steamed Jasmine Rice (ข้าวสวย)", 20, 3, [("Jasmine rice", 150)], []),
]

SUPPLIERS = {
    "market": ("Talad Thai Wholesale (Demo)", 2, "02-111-0001"),
    "farm": ("Green Valley Farm (Demo)", 1, "053-222-002"),
    "seafood": ("Andaman Seafood (Demo)", 1, "076-333-003"),
}

CUSTOMER_NAMES = [
    "Somchai P.",
    "Nok K.",
    "Ploy S.",
    "Anan T.",
    "Malee W.",
    "Kittisak R.",
    "Pim J.",
    "Arthit C.",
    "Siriporn L.",
    "Narong B.",
    "Wipa D.",
    "Ton M.",
    "Fah N.",
    "Beam V.",
]


@dataclass
class Plan:
    rows: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))

    def add(self, table: str, **row: object) -> dict:
        row.setdefault("id", uuid.uuid4())
        self.rows[table].append(row)
        return row


def _guard(reset: bool, allow_remote: bool) -> None:
    settings = get_settings()
    if settings.is_production and (reset or not settings.demo_login_enabled):
        sys.exit(
            "Refusing to seed demo data: APP_ENV is 'production'. A public demo deployment "
            "(DEMO_LOGIN_ENABLED=true) may seed or --refresh its demo restaurant, never --reset."
        )
    host = make_url(settings.database_url).host or ""
    if reset and host not in ("localhost", "127.0.0.1", "db", "postgres") and not allow_remote:
        sys.exit(f"Refusing to reset a non-local database ({host}). Pass --allow-remote if you are sure.")


def reset_database(db: Session) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    db.commit()


DEMO_ACCOUNTS = ("admin", "manager", "cashier", "kitchen")


def demo_email(key: str) -> str:
    return f"{key}@smartpos.demo"


def apply_demo_password(db: Session, password: str, *, include_admin: bool = True) -> int:
    """Give the existing demo accounts this password (they are shared, synthetic accounts).

    Without this, re-running the seed with a new DEMO_PASSWORD would leave accounts
    created by an earlier run with their old (possibly random) password.
    """
    keys = DEMO_ACCOUNTS if include_admin else DEMO_ACCOUNTS[1:]
    users = db.scalars(select(m.User).where(m.User.email.in_([demo_email(k) for k in keys]))).all()
    password_hash = hash_password(password)
    for user in users:
        user.password_hash = password_hash
    db.commit()
    return len(users)


def purge_restaurant(db: Session, restaurant_id: uuid.UUID) -> None:
    """Delete one restaurant and everything it owns. The caller commits.

    The append-only ledger trigger allows these DELETEs only for the restaurant
    named in the transaction-local ``smartpos.purge_restaurant`` setting.
    """
    db.execute(text("SELECT set_config('smartpos.purge_restaurant', :rid, true)"), {"rid": str(restaurant_id)})
    for table in reversed(Base.metadata.sorted_tables):
        if table.name != "restaurants" and "restaurant_id" in table.c:
            db.execute(table.delete().where(table.c.restaurant_id == restaurant_id))
    db.execute(delete(m.Restaurant).where(m.Restaurant.id == restaurant_id))


def refresh_demo(
    db: Session,
    password: str,
    *,
    history_days: int = HISTORY_DAYS,
    create_admin: bool = True,
    forecast: bool = True,
    set_password: bool = False,
) -> dict[str, object]:
    """Replace every demo restaurant with a freshly generated one (history ending today).

    Only restaurants marked ``is_demo`` are removed; the demo user accounts are kept
    and get new memberships. They keep their password unless ``set_password`` is true
    (pass it when the password is configured, i.e. DEMO_PASSWORD is set).
    """
    removed = 0
    for restaurant_id in db.scalars(select(m.Restaurant.id).where(m.Restaurant.is_demo.is_(True))).all():
        purge_restaurant(db, restaurant_id)
        removed += 1
    db.commit()
    result = seed(db, password, history_days=history_days, create_admin=create_admin)
    if forecast and not result.get("skipped"):
        generate_forecast(db, result["restaurant"].id, result["users"]["manager"].id)  # type: ignore[union-attr,index]
    if set_password:
        apply_demo_password(db, password, include_admin=create_admin)
    return {**result, "removed": removed}


def _local_dt(day: date, hour: int, minute: int) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=TZ).astimezone(UTC)


def seed(
    db: Session,
    password: str,
    *,
    history_days: int = HISTORY_DAYS,
    rng_seed: int = 42,
    create_admin: bool = True,
) -> dict[str, object]:
    rng = random.Random(rng_seed)
    if db.scalar(select(m.Restaurant).where(m.Restaurant.name == DEMO_NAME)):
        return {"skipped": True}

    pw_hash = hash_password(password)
    restaurant = m.Restaurant(
        name=DEMO_NAME,
        legal_name="Baan Siam Co., Ltd. (Demo)",
        branch_name="Sukhumvit",
        tax_id="0105500000000",
        address="123 Sukhumvit Road, Khlong Toei, Bangkok 10110",
        phone="02-000-0000",
        timezone="Asia/Bangkok",
        tax_rate_bps=700,
        prices_include_tax=True,
        service_charge_bps=1000,
        service_charge_dine_in_only=True,
        receipt_header="ยินดีต้อนรับ / Welcome",
        receipt_footer="ขอบคุณที่ใช้บริการ / Thank you! (Demo receipt)",
        order_number_prefix="BS",
        is_demo=True,
    )
    db.add(restaurant)
    db.flush()
    initialise_restaurant_defaults(db, restaurant)
    methods = {
        pm.code: pm
        for pm in db.scalars(select(m.PaymentMethod).where(m.PaymentMethod.restaurant_id == restaurant.id)).all()
    }

    users = {}
    accounts = [
        ("admin", "Demo Admin", None, True),
        ("manager", "Mali (Manager)", "MANAGER", False),
        ("cashier", "Chai (Cashier)", "CASHIER", False),
        ("kitchen", "Kai (Kitchen)", "KITCHEN", False),
    ]
    # A public demo deployment has no platform administrator account.
    for key, name, role, admin in accounts if create_admin else accounts[1:]:
        email = demo_email(key)
        user = db.scalar(select(m.User).where(m.User.email == email))
        if user is None:
            user = m.User(email=email, full_name=name, password_hash=pw_hash, is_platform_admin=admin)
            db.add(user)
            db.flush()
        if role:
            db.add(m.RestaurantMembership(restaurant_id=restaurant.id, user_id=user.id, role=RestaurantRole(role)))
        users[key] = user
    manager, cashier = users["manager"], users["cashier"]

    suppliers = {}
    for key, (name, lead, phone) in SUPPLIERS.items():
        s = m.Supplier(
            restaurant_id=restaurant.id,
            name=name,
            lead_time_days=lead,
            phone=phone,
            contact_name="Demo contact",
            notes="Synthetic supplier for the demo restaurant.",
        )
        db.add(s)
        suppliers[key] = s
    db.flush()

    ingredients: dict[str, m.Ingredient] = {}
    costs: dict[str, Decimal] = {}
    for name, unit, cost, supplier_key, packs in INGREDIENTS:
        ing = m.Ingredient(
            restaurant_id=restaurant.id,
            name=name,
            base_unit=unit,
            default_supplier_id=suppliers[supplier_key].id,
            average_cost_minor=Decimal(cost),
        )
        db.add(ing)
        db.flush()
        for pack, factor in packs.items():
            db.add(
                m.IngredientUnit(
                    restaurant_id=restaurant.id, ingredient_id=ing.id, unit_name=pack, factor_to_base=Decimal(factor)
                )
            )
        moq = (
            Decimal(30)
            if unit == BaseUnit.PIECE and name == "Egg"
            else (Decimal(1000) if unit != BaseUnit.PIECE else Decimal(10))
        )
        db.add(
            m.SupplierIngredient(
                restaurant_id=restaurant.id,
                supplier_id=suppliers[supplier_key].id,
                ingredient_id=ing.id,
                unit_cost_minor=Decimal(cost),
                min_order_quantity=moq,
                supplier_sku=f"DEMO-{len(ingredients) + 1:03d}",
            )
        )
        ingredients[name] = ing
        costs[name] = Decimal(cost)

    egg = ingredients["Egg"]
    spice = m.ModifierGroup(
        restaurant_id=restaurant.id,
        name="Spiciness / ความเผ็ด",
        selection_type=SelectionType.SINGLE,
        min_select=1,
        max_select=1,
        display_order=1,
    )
    spice.options = [
        m.ModifierOption(restaurant_id=restaurant.id, name=n, is_default=n.startswith("Medium"), display_order=i)
        for i, n in enumerate(["Mild / ไม่เผ็ด", "Medium / เผ็ดกลาง", "Hot / เผ็ดมาก"])
    ]
    extras = m.ModifierGroup(
        restaurant_id=restaurant.id,
        name="Extras / เพิ่มเติม",
        selection_type=SelectionType.MULTIPLE,
        min_select=0,
        max_select=3,
        display_order=2,
    )
    extras.options = [
        m.ModifierOption(
            restaurant_id=restaurant.id,
            name="Fried egg / ไข่ดาว",
            price_delta_minor=1000,
            ingredient_id=egg.id,
            ingredient_quantity=Decimal(1),
            display_order=0,
        ),
        m.ModifierOption(
            restaurant_id=restaurant.id,
            name="Extra shrimp / เพิ่มกุ้ง",
            price_delta_minor=4000,
            ingredient_id=ingredients["Shrimp"].id,
            ingredient_quantity=Decimal(50),
            display_order=1,
        ),
    ]
    size = m.ModifierGroup(
        restaurant_id=restaurant.id,
        name="Size / ขนาด",
        selection_type=SelectionType.SINGLE,
        min_select=1,
        max_select=1,
        display_order=3,
    )
    size.options = [
        m.ModifierOption(restaurant_id=restaurant.id, name="Regular", is_default=True, display_order=0),
        m.ModifierOption(restaurant_id=restaurant.id, name="Large", price_delta_minor=1500, display_order=1),
    ]
    db.add_all([spice, extras, size])
    db.flush()
    groups = {"spice": spice, "extras": extras, "size": size}

    categories: dict[str, m.Category] = {}
    products = []
    for order_index, (cat_name, name, price, popularity, recipe_items, mods) in enumerate(MENU):
        if cat_name not in categories:
            categories[cat_name] = m.Category(restaurant_id=restaurant.id, name=cat_name, display_order=len(categories))
            db.add(categories[cat_name])
            db.flush()
        product = m.Product(
            restaurant_id=restaurant.id,
            category_id=categories[cat_name].id,
            name=name,
            sku=f"BS-{order_index + 1:03d}",
            price_minor=price * 100,
            description="Demo menu item",
        )
        product.modifier_groups = [groups[g] for g in mods]
        db.add(product)
        db.flush()
        recipe = None
        if recipe_items:
            recipe = m.Recipe(
                restaurant_id=restaurant.id,
                product_id=product.id,
                version=1,
                created_by=manager.id,
                items=[
                    m.RecipeItem(
                        ingredient_id=ingredients[i].id,
                        quantity=Decimal(q),
                        input_quantity=Decimal(q),
                        input_unit=ingredients[i].base_unit.value,
                    )
                    for i, q in recipe_items
                ],
            )
            db.add(recipe)
            db.flush()
        products.append(
            {
                "product": product,
                "category": categories[cat_name],
                "popularity": popularity,
                "recipe": recipe,
                "recipe_items": recipe_items,
            }
        )

    tables = []
    for i in range(1, 11):
        t = m.DiningTable(
            restaurant_id=restaurant.id,
            name=f"T{i}",
            capacity=2 if i <= 4 else 4,
            zone="Indoor" if i <= 6 else "Terrace",
            layout_x=(i - 1) % 5,
            layout_y=(i - 1) // 5,
        )
        db.add(t)
        tables.append(t)
    customers = []
    for i, name in enumerate(CUSTOMER_NAMES):
        c = m.Customer(
            restaurant_id=restaurant.id,
            name=name,
            phone=f"08{rng.randint(10000000, 99999999)}",
            notes="Synthetic demo customer" if i == 0 else None,
        )
        db.add(c)
        customers.append(c)
    staff_discount = m.Discount(
        restaurant_id=restaurant.id, name="Staff meal 10%", kind=DiscountKind.PERCENT, value=1000
    )
    db.add_all(
        [
            staff_discount,
            m.Discount(restaurant_id=restaurant.id, name="Happy hour 5%", kind=DiscountKind.PERCENT, value=500),
            m.Discount(
                restaurant_id=restaurant.id,
                name="Manager comp ฿100",
                kind=DiscountKind.FIXED,
                value=10000,
                requires_manager=True,
            ),
        ]
    )
    db.flush()

    plan = Plan()
    today = datetime.now(TZ).date()
    now_local = datetime.now(TZ)
    now_utc = now_local.astimezone(UTC)
    start_day = today - timedelta(days=history_days)
    settings_dine = PricingSettings(700, True, 1000, True)
    settings_take = PricingSettings(700, True, 0, True)
    weights = [p["popularity"] for p in products]
    order_number = 0
    usage_by_day: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    sale_events: list[tuple[datetime, uuid.UUID, dict[str, Decimal], str]] = []
    loyalty_balance: dict[uuid.UUID, int] = defaultdict(int)

    by_name = {p["product"].name.split(" (")[0]: i for i, p in enumerate(products)}

    def build_order(
        day: date,
        when: datetime,
        *,
        status: OrderStatus,
        paid: bool,
        table: m.DiningTable | None,
        order_type: OrderType,
    ) -> dict:
        nonlocal order_number
        order_number += 1
        n_lines = rng.choices([1, 2, 3, 4], weights=[3, 4, 2, 1])[0]
        chosen = rng.choices(range(len(products)), weights=weights, k=n_lines)
        # Guests pair some dishes (curry with rice, a sweet drink with spicy food), which gives the
        # POS "ordered together" suggestions real patterns to find in the demo history.
        for i in list(chosen):
            for companion, probability in PAIRINGS.get(products[i]["product"].name.split(" (")[0], ()):
                if rng.random() < probability:
                    chosen.append(by_name[companion])
        if not any("Drinks" in products[i]["category"].name for i in chosen) and rng.random() < 0.6:
            chosen.append(rng.choice([i for i, p in enumerate(products) if "Drinks" in p["category"].name]))
        lines, usage = [], defaultdict(Decimal)
        for pos, idx in enumerate(dict.fromkeys(chosen)):
            p = products[idx]
            qty = 1 if rng.random() < 0.8 else 2
            mods = []
            for g in p["product"].modifier_groups:
                if g.selection_type == SelectionType.SINGLE:
                    opt = rng.choices(g.options, weights=[3 if o.is_default else 1 for o in g.options])[0]
                    mods.append((g, opt))
                elif rng.random() < 0.15:
                    mods.append((g, rng.choice(g.options)))
            unit_price = p["product"].price_minor + sum(o.price_delta_minor for _, o in mods)
            lines.append((pos, p, qty, unit_price, mods))
            for ing_name, q in p["recipe_items"]:
                usage[ing_name] += Decimal(q) * qty
            for _, o in mods:
                if o.ingredient_id:
                    usage[next(n for n, i in ingredients.items() if i.id == o.ingredient_id)] += (
                        o.ingredient_quantity or 0
                    ) * qty
        discount = DiscountSpec(DiscountKind.PERCENT, 1000) if rng.random() < 0.04 else None
        settings = settings_dine if order_type == OrderType.DINE_IN else settings_take
        priced = calculate([lp[3] * lp[2] for lp in lines], settings, discount)
        customer = rng.choice(customers) if rng.random() < 0.18 else None
        order = plan.add(
            "orders",
            restaurant_id=restaurant.id,
            order_number=order_number,
            order_type=order_type,
            status=status,
            payment_status=PaymentStatus.PAID if paid else PaymentStatus.UNPAID,
            table_id=table.id if table else None,
            customer_id=customer.id if customer else None,
            discount_id=staff_discount.id if discount else None,
            discount_name="Staff meal 10%" if discount else None,
            discount_kind=DiscountKind.PERCENT if discount else None,
            discount_value=1000 if discount else None,
            discount_applied_by=manager.id if discount else None,
            loyalty_points_redeemed=0,
            subtotal_minor=priced.subtotal_minor,
            discount_minor=priced.discount_minor,
            loyalty_discount_minor=0,
            service_charge_minor=priced.service_charge_minor,
            tax_minor=priced.tax_minor,
            total_minor=priced.total_minor,
            amount_paid_minor=priced.total_minor if paid else 0,
            amount_refunded_minor=0,
            tax_rate_bps=700,
            service_charge_bps=settings.service_charge_bps,
            prices_include_tax=True,
            stock_committed=status != OrderStatus.CANCELLED,
            created_by=cashier.id,
            confirmed_at=when if status != OrderStatus.CANCELLED else None,
            preparing_at=when + timedelta(minutes=2)
            if status in (OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.COMPLETED)
            else None,
            ready_at=when + timedelta(minutes=14) if status in (OrderStatus.READY, OrderStatus.COMPLETED) else None,
            completed_at=when + timedelta(minutes=35) if status == OrderStatus.COMPLETED else None,
            paid_at=min(when + timedelta(minutes=40), now_utc) if paid else None,
            cancelled_at=when + timedelta(minutes=3) if status == OrderStatus.CANCELLED else None,
            cancel_reason="Customer changed their mind (demo)" if status == OrderStatus.CANCELLED else None,
            cancelled_by=manager.id if status == OrderStatus.CANCELLED else None,
            created_at=when,
            updated_at=when,
        )
        for pos, p, qty, unit_price, mods in lines:
            item = plan.add(
                "order_items",
                restaurant_id=restaurant.id,
                order_id=order["id"],
                position=pos,
                product_id=p["product"].id,
                product_name=p["product"].name,
                product_sku=p["product"].sku,
                category_id=p["category"].id,
                category_name=p["category"].name,
                base_price_minor=p["product"].price_minor,
                unit_price_minor=unit_price,
                quantity=qty,
                line_total_minor=unit_price * qty,
                recipe_id=p["recipe"].id if p["recipe"] else None,
                created_at=when,
            )
            for g, o in mods:
                plan.add(
                    "order_item_modifiers",
                    order_item_id=item["id"],
                    modifier_option_id=o.id,
                    group_name=g.name,
                    option_name=o.name,
                    price_delta_minor=o.price_delta_minor,
                    ingredient_id=o.ingredient_id,
                    ingredient_quantity=o.ingredient_quantity,
                )
        if paid:
            code = rng.choices(["CASH", "QR", "CARD"], weights=[45, 35, 20])[0]
            method = methods[code]
            tendered = priced.total_minor
            if code == "CASH":
                tendered = int(math.ceil(priced.total_minor / 10000) * 10000) or priced.total_minor
            if priced.total_minor > 0:
                plan.add(
                    "payments",
                    restaurant_id=restaurant.id,
                    order_id=order["id"],
                    payment_method_id=method.id,
                    method_code=code,
                    method_name=method.name,
                    method_kind=method.kind,
                    is_simulated=True,
                    status=PaymentRecordStatus.RECORDED,
                    amount_minor=priced.total_minor,
                    amount_tendered_minor=tendered if code == "CASH" else None,
                    change_minor=tendered - priced.total_minor if code == "CASH" else 0,
                    refunded_minor=0,
                    recorded_by=cashier.id,
                    created_at=min(when + timedelta(minutes=40), now_utc),
                )
            if customer is not None:
                points = loyalty_points_earned(priced.total_minor, restaurant.loyalty_spend_per_point_minor)
                if points:
                    loyalty_balance[customer.id] += points
                    plan.add(
                        "loyalty_transactions",
                        restaurant_id=restaurant.id,
                        customer_id=customer.id,
                        order_id=order["id"],
                        transaction_type=LoyaltyTransactionType.EARN,
                        points=points,
                        balance_after=loyalty_balance[customer.id],
                        reason="Earned (demo history)",
                        created_by=cashier.id,
                        created_at=min(when + timedelta(minutes=40), now_utc),
                    )
        if status != OrderStatus.CANCELLED:
            for ing_name, q in usage.items():
                usage_by_day[day][ing_name] += q
            sale_events.append((when, order["id"], dict(usage), f"Order #BS{order_number:04d} confirmed"))
        return order

    # ---------------------------------------------------------------- history
    for offset in range(history_days, -1, -1):
        day = start_day + timedelta(days=history_days - offset)
        trend = 1 + 0.15 * (history_days - offset) / history_days
        expected = 42 * DOW_FACTOR[day.weekday()] * trend
        n_orders = max(0, int(rng.gauss(expected, 0.6 * math.sqrt(expected))))
        for _ in range(n_orders):
            hour = rng.choices([11, 12, 13, 14, 17, 18, 19, 20, 21], weights=[3, 6, 5, 2, 2, 5, 6, 4, 2])[0]
            when = _local_dt(day, hour, rng.randint(0, 59))
            if day == today and when + timedelta(minutes=45) > now_local.astimezone(UTC):
                continue
            cancelled = rng.random() < 0.02
            dine_in = rng.random() < 0.6
            build_order(
                day,
                when,
                status=OrderStatus.CANCELLED if cancelled else OrderStatus.COMPLETED,
                paid=not cancelled,
                table=rng.choice(tables) if dine_in else None,
                order_type=OrderType.DINE_IN if dine_in else OrderType.TAKEAWAY,
            )

    # Live orders for the kitchen display and table view.
    live_time = now_local.astimezone(UTC) - timedelta(minutes=20)
    active_tables = {}
    for status, table_index, paid in [
        (OrderStatus.CONFIRMED, 2, False),
        (OrderStatus.PREPARING, 4, False),
        (OrderStatus.READY, None, True),
        (OrderStatus.CONFIRMED, None, True),
    ]:
        table = tables[table_index] if table_index is not None else None
        order = build_order(
            today,
            live_time,
            status=status,
            paid=paid,
            table=table,
            order_type=OrderType.DINE_IN if table else OrderType.TAKEAWAY,
        )
        if table:
            active_tables[table.id] = order["id"]
        live_time += timedelta(minutes=4)

    # ---------------------------------------------------------------- inventory simulation
    daily_avg = {
        name: sum(usage_by_day[d][name] for d in usage_by_day) / max(len(usage_by_day), 1) for name in ingredients
    }
    for name, ing in ingredients.items():
        avg = daily_avg[name]
        ing.reorder_level = (avg * Decimal("1.5")).quantize(Decimal(1))
        ing.safety_stock = (avg * Decimal("1.0")).quantize(Decimal(1))
    low_on_purpose = {"Shrimp", "Thai basil", "Lime"}
    balance = {name: Decimal(0) for name in ingredients}
    restock_days = [
        start_day + timedelta(days=i)
        for i in range(history_days + 1)
        if (start_day + timedelta(days=i)).weekday() in (0, 3)
    ]
    last_restock = max(restock_days)
    movements: list[dict] = []

    def move(name: str, qty: Decimal, mtype: MovementType, when: datetime, reason: str, **extra: object) -> None:
        balance[name] += qty
        movements.append(
            {
                "id": uuid.uuid4(),
                "restaurant_id": restaurant.id,
                "ingredient_id": ingredients[name].id,
                "movement_type": mtype,
                "quantity": qty,
                "balance_after": balance[name],
                "reason": reason,
                "created_at": when,
                "actor_user_id": manager.id,
                **extra,
            }
        )

    opening_time = _local_dt(start_day, 7, 0)
    for name in ingredients:
        qty = (daily_avg[name] * 4).quantize(Decimal(1)) or Decimal(10)
        move(
            name,
            qty,
            MovementType.OPENING,
            opening_time,
            "Opening stock (demo)",
            unit_cost_minor=costs[name],
            input_quantity=qty,
            input_unit=ingredients[name].base_unit.value,
        )

    sale_events.sort(key=lambda e: e[0])
    event_index = 0
    po_number = 0
    for day_index in range(history_days + 1):
        day = start_day + timedelta(days=day_index)
        morning = _local_dt(day, 8, 0)
        if day in restock_days and day_index > 0:
            for supplier_key, supplier in suppliers.items():
                lines = []
                horizon = [day + timedelta(days=k) for k in range(4)]
                for name, _, _, s_key, _ in INGREDIENTS:
                    if s_key != supplier_key:
                        continue
                    need = sum((usage_by_day[d][name] for d in horizon), Decimal(0))
                    target = need * Decimal("1.6") + ingredients[name].safety_stock
                    qty = target - balance[name]
                    if day == last_restock and name in low_on_purpose:
                        until_now = sum((usage_by_day[d][name] for d in horizon if d <= today), Decimal(0))
                        qty = until_now + daily_avg[name] * Decimal("0.3") - balance[name]
                    qty = qty.quantize(Decimal(1))
                    if qty > 0:
                        lines.append((name, qty))
                if not lines:
                    continue
                po_number += 1
                ordered_at = morning - timedelta(days=supplier.lead_time_days)
                po = plan.add(
                    "purchase_orders",
                    restaurant_id=restaurant.id,
                    po_number=po_number,
                    supplier_id=supplier.id,
                    status=PurchaseOrderStatus.RECEIVED,
                    expected_delivery_date=day,
                    notes="Demo restock",
                    created_by=manager.id,
                    submitted_by=manager.id,
                    submitted_at=ordered_at,
                    received_at=morning,
                    created_at=ordered_at,
                    updated_at=morning,
                    estimated_total_minor=int(sum(q * costs[n] for n, q in lines)),
                )
                receipt = plan.add(
                    "purchase_order_receipts",
                    restaurant_id=restaurant.id,
                    purchase_order_id=po["id"],
                    idempotency_key=f"demo-receipt-{po_number}",
                    received_by=manager.id,
                    total_cost_minor=po["estimated_total_minor"],
                    created_at=morning,
                )
                for pos, (name, qty) in enumerate(lines):
                    item = plan.add(
                        "purchase_order_items",
                        purchase_order_id=po["id"],
                        position=pos,
                        ingredient_id=ingredients[name].id,
                        quantity_ordered=qty,
                        quantity_received=qty,
                        input_quantity=qty,
                        input_unit=ingredients[name].base_unit.value,
                        unit_cost_minor=costs[name],
                    )
                    plan.add(
                        "purchase_order_receipt_lines",
                        receipt_id=receipt["id"],
                        purchase_order_item_id=item["id"],
                        ingredient_id=ingredients[name].id,
                        quantity=qty,
                        unit_cost_minor=costs[name],
                    )
                    move(
                        name,
                        qty,
                        MovementType.PURCHASE_RECEIPT,
                        morning,
                        f"Received on PO-{po_number:05d}",
                        unit_cost_minor=costs[name],
                        input_quantity=qty,
                        input_unit=ingredients[name].base_unit.value,
                        purchase_order_id=po["id"],
                        purchase_order_receipt_id=receipt["id"],
                    )
        day_end = _local_dt(day + timedelta(days=1), 0, 0)
        while event_index < len(sale_events) and sale_events[event_index][0] < day_end:
            when, order_id, usage, reason = sale_events[event_index]
            for name, qty in usage.items():
                if qty:
                    move(name, -qty, MovementType.SALE, when, reason, order_id=order_id, unit_cost_minor=costs[name])
            event_index += 1
        if rng.random() < 0.15:
            name = rng.choice(["Thai basil", "Bean sprouts", "Lime", "Mango"])
            qty = min(balance[name], (daily_avg[name] * Decimal("0.2")).quantize(Decimal(1)))
            if qty > 0:
                move(
                    name,
                    -qty,
                    MovementType.WASTE,
                    _local_dt(day, 22, 0),
                    "Spoiled at closing (demo)",
                    unit_cost_minor=costs[name],
                )

    plan.rows["inventory_movements"] = movements
    for table in (
        "orders",
        "order_items",
        "order_item_modifiers",
        "payments",
        "loyalty_transactions",
        "purchase_orders",
        "purchase_order_items",
        "purchase_order_receipts",
        "purchase_order_receipt_lines",
        "inventory_movements",
    ):
        rows = plan.rows.get(table, [])
        # executemany needs identical keys in every row; absent optional columns become NULL.
        keys = set().union(*(r.keys() for r in rows)) if rows else set()
        rows = [{k: r.get(k) for k in keys} for r in rows]
        for start in range(0, len(rows), 2000):
            db.execute(insert(Base.metadata.tables[table]), rows[start : start + 2000])

    for name, ing in ingredients.items():
        ing.current_stock = balance[name]
    for customer in customers:
        customer.loyalty_balance = loyalty_balance[customer.id]
    for table in tables:
        if table.id in active_tables:
            table.status = TableStatus.OCCUPIED
            table.current_order_id = active_tables[table.id]
    tables[7].status = TableStatus.RESERVED
    db.add_all(
        [
            m.RestaurantCounter(restaurant_id=restaurant.id, name="order_number", value=order_number),
            m.RestaurantCounter(restaurant_id=restaurant.id, name="po_number", value=po_number),
        ]
    )
    db.commit()
    return {
        "restaurant": restaurant,
        "users": users,
        "orders": order_number,
        "movements": len(movements),
        "purchase_orders": po_number,
    }


def generate_forecast(db: Session, restaurant_id: uuid.UUID, manager_id: uuid.UUID) -> None:
    from app.api.deps import RestaurantContext
    from app.forecasting.service import run_forecast
    from app.schemas.forecast import ForecastRunCreate, RecommendationGenerate
    from app.services.recommendations import generate

    restaurant = db.get(m.Restaurant, restaurant_id)
    manager = db.get(m.User, manager_id)
    ctx = RestaurantContext(
        user=manager,
        restaurant=restaurant,
        role=RestaurantRole.MANAGER,
        permissions=permissions_for(RestaurantRole.MANAGER, is_platform_admin=False),
    )
    run = run_forecast(db, ctx, ForecastRunCreate(horizon_days=7))
    result = generate(db, ctx, RecommendationGenerate(review_period_days=1))
    print(
        f"  Forecast: model={run.model_name}, products={run.products_forecast}; "
        f"{len(result.created)} reorder recommendation(s) pending review"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SmartPOS AI demo data (development only).")
    parser.add_argument("--reset", action="store_true", help="Delete ALL data in the database first")
    parser.add_argument("--yes", action="store_true", help="Confirm --reset without prompting")
    parser.add_argument("--allow-remote", action="store_true", help="Allow --reset on a non-local database")
    parser.add_argument("--days", type=int, default=HISTORY_DAYS, help="Days of synthetic history")
    parser.add_argument("--no-forecast", action="store_true", help="Skip generating an initial forecast")
    parser.add_argument(
        "--refresh", action="store_true", help="Replace only the demo restaurant(s) with fresh history ending today"
    )
    parser.add_argument("--no-admin", action="store_true", help="Do not create the demo platform administrator")
    args = parser.parse_args()
    _guard(args.reset, args.allow_remote)
    # DEMO_PASSWORD from the environment or .env (read through the app settings).
    configured = get_settings().demo_password
    password = configured or secrets.token_urlsafe(9) + "1a"
    with get_session_factory()() as db:
        if args.refresh:
            result = refresh_demo(
                db,
                password,
                history_days=args.days,
                create_admin=not args.no_admin,
                forecast=not args.no_forecast,
                set_password=configured is not None,
            )
            print(f"Replaced {result['removed']} demo restaurant(s); created {result['orders']} synthetic orders.")
            _print_accounts(args.no_admin, configured, password, existing=True)
            return
        if args.reset:
            if not args.yes:
                sys.exit("--reset deletes every row in the database. Re-run with --reset --yes to confirm.")
            reset_database(db)
            print("Database cleared.")
        result = seed(db, password, history_days=args.days, create_admin=not args.no_admin)
        if result.get("skipped"):
            if configured:
                count = apply_demo_password(db, configured, include_admin=not args.no_admin)
                print(f"'{DEMO_NAME}' already exists; its {count} demo account(s) now use DEMO_PASSWORD.")
            else:
                print(
                    f"'{DEMO_NAME}' already exists; nothing to do. The demo accounts keep their password: "
                    "set DEMO_PASSWORD to choose one, or use --reset --yes to recreate everything."
                )
            return
        print(
            f"Created '{DEMO_NAME}' with {result['orders']} synthetic orders, {result['movements']} inventory "
            f"movements and {result['purchase_orders']} purchase orders."
        )
        if not args.no_forecast:
            generate_forecast(db, result["restaurant"].id, result["users"]["manager"].id)
    _print_accounts(args.no_admin, configured, password, existing=False)


def _print_accounts(no_admin: bool, configured: str | None, password: str, *, existing: bool) -> None:
    print("\nDemo accounts (development only):")
    for key in DEMO_ACCOUNTS[1:] if no_admin else DEMO_ACCOUNTS:
        print(f"  {key:<8} {demo_email(key)}")
    if configured:
        print("  password: the value of DEMO_PASSWORD")
    elif existing:
        print("  password: unchanged (set DEMO_PASSWORD to choose one)")
    else:
        print(f"  password: {password}   (set DEMO_PASSWORD to choose your own)")


if __name__ == "__main__":
    main()

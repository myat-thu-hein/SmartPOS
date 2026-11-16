"""Role-based access control.

Permissions are checked on the backend for every request. The frontend only
uses the same permission list to decide which navigation items to display.
"""

from __future__ import annotations

import enum

from app.models.enums import RestaurantRole


class Permission(enum.StrEnum):
    MENU_READ = "menu:read"
    MENU_WRITE = "menu:write"
    TABLES_READ = "tables:read"
    TABLES_OPERATE = "tables:operate"
    TABLES_WRITE = "tables:write"
    ORDERS_READ = "orders:read"
    ORDERS_CREATE = "orders:create"
    ORDERS_COMPLETE = "orders:complete"
    ORDERS_CANCEL_DRAFT = "orders:cancel_draft"
    ORDERS_CANCEL = "orders:cancel"
    PAYMENTS_RECORD = "payments:record"
    REFUNDS_RECORD = "refunds:record"
    DISCOUNTS_APPLY = "discounts:apply"
    DISCOUNTS_OVERRIDE = "discounts:override"
    KITCHEN_READ = "kitchen:read"
    KITCHEN_UPDATE = "kitchen:update"
    RECIPES_READ = "recipes:read"
    RECIPES_WRITE = "recipes:write"
    INVENTORY_READ = "inventory:read"
    INVENTORY_WRITE = "inventory:write"
    SUPPLIERS_READ = "suppliers:read"
    SUPPLIERS_WRITE = "suppliers:write"
    PURCHASING_READ = "purchasing:read"
    PURCHASING_WRITE = "purchasing:write"
    CUSTOMERS_READ = "customers:read"
    CUSTOMERS_CREATE = "customers:create"
    CUSTOMERS_WRITE = "customers:write"
    LOYALTY_ADJUST = "loyalty:adjust"
    ANALYTICS_READ = "analytics:read"
    REPORTS_READ = "reports:read"
    FORECAST_READ = "forecast:read"
    FORECAST_RUN = "forecast:run"
    RECOMMENDATIONS_READ = "recommendations:read"
    RECOMMENDATIONS_REVIEW = "recommendations:review"
    AI_USE = "ai:use"
    STAFF_MANAGE = "staff:manage"
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"
    # Platform-level permissions (ADMIN only).
    PLATFORM_ADMIN = "platform:admin"
    AUDIT_READ = "audit:read"


RESTAURANT_PERMISSIONS = frozenset(p for p in Permission if p not in {Permission.PLATFORM_ADMIN, Permission.AUDIT_READ})

ROLE_PERMISSIONS: dict[RestaurantRole, frozenset[Permission]] = {
    RestaurantRole.MANAGER: RESTAURANT_PERMISSIONS,
    RestaurantRole.CASHIER: frozenset(
        {
            Permission.MENU_READ,
            Permission.TABLES_READ,
            Permission.TABLES_OPERATE,
            Permission.ORDERS_READ,
            Permission.ORDERS_CREATE,
            Permission.ORDERS_COMPLETE,
            Permission.ORDERS_CANCEL_DRAFT,
            Permission.PAYMENTS_RECORD,
            Permission.DISCOUNTS_APPLY,
            Permission.KITCHEN_READ,
            Permission.CUSTOMERS_READ,
            Permission.CUSTOMERS_CREATE,
            Permission.SETTINGS_READ,
        }
    ),
    RestaurantRole.KITCHEN: frozenset(
        {
            Permission.MENU_READ,
            Permission.KITCHEN_READ,
            Permission.KITCHEN_UPDATE,
        }
    ),
}

ADMIN_PERMISSIONS = frozenset(Permission)


def permissions_for(role: RestaurantRole | None, *, is_platform_admin: bool) -> frozenset[Permission]:
    if is_platform_admin:
        return ADMIN_PERMISSIONS
    if role is None:
        return frozenset()
    return ROLE_PERMISSIONS[role]

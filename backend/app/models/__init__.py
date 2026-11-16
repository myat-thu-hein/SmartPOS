"""SQLAlchemy models. Importing this package registers every table on the metadata."""

from app.models.catalog import (
    Category,
    DiningTable,
    ModifierGroup,
    ModifierOption,
    Product,
    product_modifier_groups,
)
from app.models.customers import Customer, LoyaltyTransaction
from app.models.forecasting import Forecast, ForecastModelMetric, ForecastRun, ReorderRecommendation
from app.models.identity import (
    AuditLog,
    PasswordResetToken,
    Restaurant,
    RestaurantCounter,
    RestaurantMembership,
    User,
    UserSession,
)
from app.models.inventory import Ingredient, IngredientUnit, InventoryMovement, Recipe, RecipeItem
from app.models.platform import Notification, NotificationCursor, RateLimitBucket, RealtimeEvent
from app.models.purchasing import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
    Supplier,
    SupplierIngredient,
)
from app.models.sales import (
    Discount,
    Order,
    OrderItem,
    OrderItemModifier,
    Payment,
    PaymentMethod,
    Refund,
)

__all__ = [
    "AuditLog",
    "Category",
    "Customer",
    "DiningTable",
    "Discount",
    "Forecast",
    "ForecastModelMetric",
    "ForecastRun",
    "Ingredient",
    "IngredientUnit",
    "InventoryMovement",
    "LoyaltyTransaction",
    "ModifierGroup",
    "ModifierOption",
    "Notification",
    "NotificationCursor",
    "Order",
    "OrderItem",
    "OrderItemModifier",
    "PasswordResetToken",
    "Payment",
    "PaymentMethod",
    "Product",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseOrderReceipt",
    "PurchaseOrderReceiptLine",
    "RateLimitBucket",
    "RealtimeEvent",
    "Recipe",
    "RecipeItem",
    "Refund",
    "ReorderRecommendation",
    "Restaurant",
    "RestaurantCounter",
    "RestaurantMembership",
    "Supplier",
    "SupplierIngredient",
    "User",
    "UserSession",
    "product_modifier_groups",
]

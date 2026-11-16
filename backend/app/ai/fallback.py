"""Deterministic, rule-based answers used when no LLM is configured or reachable.

It recognises common questions (English and Thai keywords), calls the same
approved tools, and formats the numbers without any language model.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai import tools
from app.api.deps import RestaurantContext

HELP = (
    'I can answer questions such as: "What were today\'s sales?", "Which products sold the most this week?", '
    '"Which ingredients are running low?", "What demand do we expect tomorrow?", "Which items should we '
    'reorder?" or "How do sales compare with last week?"'
)


def _has(text: str, *words: str) -> bool:
    return any(w in text for w in words)


def detect(message: str) -> tuple[str, dict[str, Any]] | None:
    text = message.lower()
    period = "today"
    if _has(text, "today", "วันนี้"):
        period = "today"
    elif _has(text, "yesterday", "เมื่อวาน"):
        period = "yesterday"
    elif _has(text, "last week", "previous week", "สัปดาห์ที่แล้ว"):
        period = "last_week"
    elif _has(text, "this week", "week", "สัปดาห์", "7 days"):
        period = "last_7_days" if "7 days" in text else "this_week"
    elif _has(text, "month", "เดือน", "30 days"):
        period = "this_month" if "30 days" not in text else "last_30_days"
    if _has(text, "reorder", "order more", "should we buy", "purchase", "recommend", "สั่งซื้อ", "สั่งของ"):
        return "get_reorder_recommendations", {"status": "PENDING"}
    if _has(text, "forecast", "expect", "predict", "tomorrow", "demand", "พยากรณ์", "พรุ่งนี้", "คาดการณ์"):
        days = 7 if _has(text, "week", "7 days", "สัปดาห์") else 1
        return "get_forecast", {"days": days}
    if _has(text, "running low", "low stock", "low on", "out of stock", "ใกล้หมด", "หมด"):
        return "get_low_stock_items", {"limit": 10}
    if _has(text, "inventory", "stock", "ingredient", "สต็อก", "วัตถุดิบ"):
        return "get_inventory_status", {}
    if _has(text, "slow", "least", "worst", "ขายไม่ดี"):
        return "get_slow_products", {"period": period, "limit": 5}
    if _has(text, "top", "best", "most", "popular", "ขายดี"):
        return "get_top_products", {"period": period, "limit": 5}
    if _has(text, "compare", "sales", "revenue", "sold", "earn", "ยอดขาย", "รายได้"):
        if _has(text, "compare", "เทียบ") and period in ("today", "last_week", "this_week"):
            # "Compare with last week" = the last 7 days against the 7 days before.
            period = "last_7_days" if period != "today" or _has(text, "week", "สัปดาห์") else "today"
        return "get_sales_summary", {"period": period}
    return None


def _format(name: str, data: dict[str, Any]) -> str:
    if name == "get_sales_summary":
        r = data["date_range"]
        change = data["net_sales_change_pct"]
        prev = data["previous_period"]
        until = f" up to {prev['until_time']}" if prev.get("until_time") else ""
        trend = (
            f"{'up' if change >= 0 else 'down'} {abs(change):.1f}% compared with "
            f"{prev['start']} to {prev['end']}{until}"
            if change is not None
            else "there were no sales in the previous period to compare with"
        )
        return (
            f"From {r['start']} to {r['end']}{' up to ' + r['until_time'] if r.get('until_time') else ''} "
            f"({r['timezone']}): {data['orders']} paid orders, net sales "
            f"{data['net_sales']} (gross {data['gross_sales']}, discounts {data['discounts']}, refunds "
            f"{data['refunds']}). Average order value {data['average_order_value']}. Net sales are {trend}."
        )
    if name in ("get_top_products", "get_slow_products"):
        r = data["date_range"]
        label = "Top" if name == "get_top_products" else "Slowest"
        if not data["products"]:
            return f"No product sales were recorded between {r['start']} and {r['end']}."
        lines = [f"{i + 1}. {p['name']} - {p['quantity']} sold ({p['sales']})" for i, p in enumerate(data["products"])]
        return f"{label} products from {r['start']} to {r['end']}:\n" + "\n".join(lines)
    if name == "get_low_stock_items":
        if not data["items"]:
            return "No ingredients are at or below their reorder level right now."
        lines = [
            f"- {i['name']}: {i['current_stock']:g} {i['unit']} (reorder level {i['reorder_level']:g})"
            for i in data["items"]
        ]
        return f"{data['count']} ingredient(s) are running low:\n" + "\n".join(lines)
    if name == "get_inventory_status":
        return (
            f"{data['active_ingredients']} active ingredients: {data['low_stock']} low on stock, "
            f"{data['out_of_stock']} out of stock. Estimated stock value {data['stock_value']}"
            + (
                f" ({data['ingredients_without_cost']} ingredient(s) have no cost data)."
                if data["ingredients_without_cost"]
                else "."
            )
        )
    if name == "get_forecast":
        if not data.get("available"):
            return data.get("message") or data.get("note") or "No forecast is available for those dates."
        r = data["date_range"]
        lines = [f"- {p['name']}: about {p['predicted_quantity']:g}" for p in data["products"][:8]]
        demo = " It is based on synthetic demo data." if data["uses_demo_data"] else ""
        return (
            f"Forecast ({data['model']}) for {r['start']} to {r['end']} - these are predictions, not actual "
            f"sales:{demo}\n" + "\n".join(lines)
        )
    if name == "get_reorder_recommendations":
        if not data["items"]:
            return "There are no pending reorder recommendations. Generate them from the Forecasting page."
        lines = [
            f"- {i['ingredient']}: {i['suggested_quantity']:g} {i['unit']}"
            + (f" from {i['supplier']}" if i["supplier"] else "")
            for i in data["items"]
        ]
        return (
            f"{data['count']} pending recommendation(s):\n"
            + "\n".join(lines)
            + "\nA manager must approve each recommendation; nothing is ordered automatically."
        )
    return HELP


def answer(db: Session, ctx: RestaurantContext, message: str) -> tuple[str, list[dict[str, Any]]]:
    intent = detect(message)
    if intent is None:
        return HELP, []
    name, args = intent
    try:
        data = tools.execute(db, ctx, name, args)
    except tools.ToolError as exc:
        return f"I could not look that up: {exc}", [{"name": name, "arguments": args}]
    return _format(name, data), [{"name": name, "arguments": args}]

# API documentation

The backend is a JSON REST API under `/api/v1`, with 140 operations.
Interactive documentation generated from the code is served at `/api/docs`
(Swagger UI) and `/api/redoc`, plus the OpenAPI schema at
`/api/v1/openapi.json`. These are on by default outside production; set
`API_DOCS_ENABLED=true` to expose them in production.

## Conventions

| Topic | Convention |
| --- | --- |
| Base URL | Browsers: same origin as the frontend (`/api/v1/...`, proxied by Next.js). API clients: the backend origin |
| Authentication | Browser: `POST /auth/login` sets the httpOnly `smartpos_session` cookie and a readable `smartpos_csrf` cookie. API clients: `POST /auth/token`, then `Authorization: Bearer <token>` |
| CSRF | Cookie-authenticated `POST`, `PUT`, `PATCH` and `DELETE` requests must send `X-CSRF-Token: <smartpos_csrf cookie value>`. Bearer requests are exempt |
| Tenant | Restaurant-scoped endpoints require `X-Restaurant-ID: <uuid>`. The user must be an active member (administrators may use any restaurant). Records of other restaurants return `404` |
| Permissions | Checked on every call. Missing permission → `403 forbidden`. See [SECURITY.md](SECURITY.md#roles-and-permissions) |
| Money | Integer minor units (satang): `12050` = ฿120.50. Unit costs may have up to 4 decimals |
| Quantities | Decimal strings or numbers. Most write endpoints accept a `unit` (`g`, `kg`, `ml`, `l`, `piece` or a pack unit) and convert to the ingredient's base unit |
| Dates | ISO 8601. Analytics `start_date` and `end_date` are local dates in the restaurant's time zone, inclusive |
| Pagination | `?page=1&page_size=50` (max 200) → `{ "items": [...], "total", "page", "page_size" }` |
| Unknown fields | Request bodies reject fields that are not part of the schema (`422`, type `extra_forbidden`). Prices are never accepted from clients |
| Idempotency | Send `Idempotency-Key: <unique string>` when creating orders and recording payments or refunds; it is required when receiving purchase orders. A retry with the same key returns the original result (`Idempotent-Replayed: true`). Reusing a key for a different request → `409 idempotency_key_reused` |
| Rate limits | Sign-in, password change and reset: 10 attempts per 5 minutes, counted separately per IP address and per email address. AI assistant: 30 requests per 10 minutes per user → `429 rate_limited` |
| Tracing | Every response has `X-Request-ID`. Quote it when reporting a problem |

## Errors

Every error has the same shape:

```json
{
  "error": {
    "code": "insufficient_stock",
    "message": "Not enough stock for: Rice noodles.",
    "details": { "shortages": [{ "ingredient_name": "Rice noodles", "required": 300.0, "available": 120.0, "unit": "g" }] },
    "request_id": "6f1c0a…"
  }
}
```

| HTTP | Typical `code` values |
| --- | --- |
| 400 | `bad_request` |
| 401 | `unauthorized`, `invalid_credentials`, `session_expired` |
| 403 | `forbidden`, `csrf_failed`, `restaurant_forbidden`, `restaurant_inactive`, `discount_requires_manager`, `discount_limit_exceeded` |
| 404 | `not_found`, `no_forecast`, `recipe_not_found` |
| 409 | `conflict`, `insufficient_stock`, `invalid_transition`, `order_not_payable`, `order_already_paid`, `po_not_receivable`, `idempotency_key_reused`, `table_has_active_order`, `email_taken` |
| 422 | `validation_error` (with per-field `details`), `incompatible_unit`, `insufficient_data`, `insufficient_points`, `modifier_required` |
| 429 | `rate_limited` (`details.retry_after` in seconds) |
| 503 | `database_unavailable` |

## Examples

Sign in as an API client and list today's orders:

```bash
API=http://localhost:8000/api/v1
TOKEN=$(curl -s $API/auth/token -H 'Content-Type: application/json' \
  -d '{"email":"manager@smartpos.demo","password":"'"$DEMO_PASSWORD"'"}' | jq -r .access_token)
RID=$(curl -s $API/auth/me -H "Authorization: Bearer $TOKEN" | jq -r '.memberships[0].restaurant_id')
H=(-H "Authorization: Bearer $TOKEN" -H "X-Restaurant-ID: $RID" -H 'Content-Type: application/json')
curl -s "$API/orders?page_size=10" "${H[@]}" | jq '.items[] | {display_number, status, total_minor}'
```

Price a cart, then create and confirm a takeaway order (stock is deducted on confirm):

```bash
curl -s $API/orders/quote "${H[@]}" -d '{"order_type":"TAKEAWAY","items":[{"product_id":"<uuid>","quantity":2}]}'
curl -s $API/orders "${H[@]}" -H 'Idempotency-Key: pos-1-0001' \
  -d '{"order_type":"TAKEAWAY","items":[{"product_id":"<uuid>","quantity":2,"modifier_option_ids":[],"notes":"no peanuts"}],"confirm":true}'
```

Record a cash payment (a retry with the same key is safe):

```bash
curl -s $API/orders/<order-id>/payments "${H[@]}" -H 'Idempotency-Key: pay-0001' \
  -d '{"payment_method_id":"<cash-method-id>","amount_minor":28600,"amount_tendered_minor":30000}'
```

Receive part of a purchase order:

```bash
curl -s $API/purchase-orders/<po-id>/receive "${H[@]}" -H 'Idempotency-Key: rcv-0001' \
  -d '{"lines":[{"item_id":"<line-id>","quantity":"2","unit":"kg"}],"notes":"Invoice 1182"}'
```

Run a forecast and generate reorder suggestions:

```bash
curl -s $API/forecast/runs "${H[@]}" -d '{"horizon_days":7,"model":"auto"}' | jq '{model_name, metrics}'
curl -s $API/recommendations/generate "${H[@]}" -d '{"review_period_days":3}'
```

Ask the assistant:

```bash
curl -s $API/ai/chat "${H[@]}" -d '{"message":"Which ingredients are running low?","history":[]}' | jq '{answer, mode, tools_used}'
```

## Live updates

Every change that other screens care about (orders, stock, tables, purchase
orders, menu, settings, forecasts, notifications) is recorded as an event in
the same transaction as the change. Events carry ids and statuses only, never
money amounts or personal data, and each reader only receives topics their
role may see.

```bash
# Polling: start from "now", then ask for anything newer than the cursor.
curl -s "$API/events" -H "Authorization: Bearer $TOKEN" -H "X-Restaurant-ID: $RID"
# -> {"events": [], "cursor": 1841}
curl -s "$API/events?after=1841" -H "Authorization: Bearer $TOKEN" -H "X-Restaurant-ID: $RID"

# Server-Sent Events (browsers use EventSource, which cannot send headers, so the
# restaurant is a query parameter). Reconnect with Last-Event-ID to resume.
curl -N "$API/events/stream?restaurant_id=$RID" -H "Authorization: Bearer $TOKEN"
# retry: 2000
# id: 1841
# event: ready
#
# id: 1842
# data: {"id":1842,"type":"order.confirmed","topic":"order","entity_id":"…","data":{"display_number":"BS0042",…}}
```

A stream ends after `EVENTS_STREAM_SECONDS` (240 s by default) and sends a
`ping` event every 15 s while idle.

## Endpoint reference

Paths are relative to `/api/v1`.
<!-- generated from the OpenAPI schema: 149 operations -->

### health

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (checks the database) |

### auth

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/auth/login` | Sign in (browser session cookie) |
| `GET` | `/auth/demo` | Whether one-click demo sign-in is available |
| `POST` | `/auth/demo-login` | Sign in to the demo restaurant by role |
| `POST` | `/auth/token` | Obtain a bearer token for API clients |
| `POST` | `/auth/logout` | Logout |
| `GET` | `/auth/me` | Me |
| `PATCH` | `/auth/me` | Update Profile |
| `POST` | `/auth/change-password` | Change Password |
| `POST` | `/auth/password-reset/request` | Request Password Reset |
| `POST` | `/auth/password-reset/confirm` | Confirm Password Reset |

### users

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/users` | List staff of the current restaurant |
| `POST` | `/users` | Create Staff |
| `PATCH` | `/users/{user_id}` | Update Staff |
| `POST` | `/users/{user_id}/password` | Set Staff Password |
| `GET` | `/users/all` | List all platform users (admin) |
| `POST` | `/users/platform` | Create a platform user (admin) |
| `PATCH` | `/users/{user_id}/platform` | Activate/deactivate or promote a user (admin) |

### restaurants

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/restaurants` | Restaurants the user can access |
| `POST` | `/restaurants` | Create Restaurant |
| `GET` | `/restaurants/current` | Get Current Restaurant |
| `PATCH` | `/restaurants/current` | Update Current Restaurant |
| `PATCH` | `/restaurants/{restaurant_id}/status` | Activate or deactivate a restaurant (admin) |
| `POST` | `/restaurants/{restaurant_id}/members` | Add an existing user to a restaurant (admin) |
| `GET` | `/payments/methods` | List Payment Methods |
| `POST` | `/payments/methods` | Create Payment Method |
| `PATCH` | `/payments/methods/{method_id}` | Update Payment Method |
| `GET` | `/discounts` | List Discounts |
| `POST` | `/discounts` | Create Discount |
| `PATCH` | `/discounts/{discount_id}` | Update Discount |
| `GET` | `/audit-logs` | Audit trail (admin) |

### categories

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/categories` | List Categories |
| `POST` | `/categories` | Create Category |
| `PATCH` | `/categories/{category_id}` | Update Category |
| `DELETE` | `/categories/{category_id}` | Delete Category |

### products

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/products` | List Products |
| `POST` | `/products` | Create Product |
| `GET` | `/products/suggestions` | Add-on suggestions for a POS cart, from this restaurant's sales |
| `GET` | `/products/{product_id}` | Get Product |
| `PATCH` | `/products/{product_id}` | Update Product |
| `DELETE` | `/products/{product_id}` | Delete a never-sold product, or archive a product with sales history |
| `PUT` | `/products/{product_id}/modifier-groups` | Set Modifier Groups |

### modifiers

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/modifiers/groups` | List Groups |
| `POST` | `/modifiers/groups` | Create Group |
| `PATCH` | `/modifiers/groups/{group_id}` | Update Group |
| `POST` | `/modifiers/groups/{group_id}/options` | Add Option |
| `PATCH` | `/modifiers/options/{option_id}` | Update Option |

### tables

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/tables` | List Tables |
| `POST` | `/tables` | Create Table |
| `GET` | `/tables/{table_id}` | Get Table |
| `PATCH` | `/tables/{table_id}` | Update Table |
| `DELETE` | `/tables/{table_id}` | Delete Table |
| `POST` | `/tables/{table_id}/status` | Reserve, clean or free a table |
| `POST` | `/tables/{table_id}/close` | Close an occupied table once its orders are completed and paid |

### orders

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/orders/quote` | Price a cart without saving it (authoritative totals) |
| `GET` | `/orders` | List Orders |
| `POST` | `/orders` | Create Order |
| `GET` | `/orders/{order_id}` | Get Order |
| `PATCH` | `/orders/{order_id}` | Change items, notes, customer or discount (until payment starts) |
| `POST` | `/orders/{order_id}/confirm` | Confirm a draft: sends it to the kitchen and deducts stock (idempotent) |
| `POST` | `/orders/{order_id}/status` | Change Status |
| `POST` | `/orders/{order_id}/cancel` | Cancel Order |
| `GET` | `/orders/{order_id}/receipt` | Receipt |

### payments

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/orders/{order_id}/payments` | List Order Payments |
| `POST` | `/orders/{order_id}/payments` | Record a payment (send an Idempotency-Key to avoid duplicates) |
| `POST` | `/orders/{order_id}/refunds` | Record a refund against a payment (manager) |
| `GET` | `/payments` | List Payments |

### kitchen

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/kitchen/orders` | Kitchen Orders |
| `POST` | `/kitchen/orders/{order_id}/status` | Kitchen Update |

### customers

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/customers` | Search customers (cashiers receive masked contact details) |
| `POST` | `/customers` | Create Customer |
| `GET` | `/customers/{customer_id}` | Get Customer |
| `PATCH` | `/customers/{customer_id}` | Update Customer |
| `POST` | `/customers/{customer_id}/anonymise` | Erase personal data while keeping order and loyalty history |
| `GET` | `/customers/{customer_id}/orders` | Customer Orders |
| `GET` | `/customers/{customer_id}/favourites` | Customer Favourites |

### loyalty

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/loyalty/settings` | Loyalty Settings |
| `GET` | `/loyalty/customers/{customer_id}/transactions` | Loyalty Transactions |
| `POST` | `/loyalty/customers/{customer_id}/adjust` | Adjust Points |

### ingredients

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/ingredients` | List Ingredients |
| `POST` | `/ingredients` | Create Ingredient |
| `GET` | `/ingredients/{ingredient_id}` | Get Ingredient |
| `PATCH` | `/ingredients/{ingredient_id}` | Update Ingredient |
| `POST` | `/ingredients/{ingredient_id}/units` | Define a pack unit such as 'tray' = 30 pieces |
| `DELETE` | `/ingredients/{ingredient_id}/units/{unit_id}` | Remove Unit |

### inventory

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/inventory/summary` | Inventory Summary |
| `GET` | `/inventory/stock-risk` | Days of cover and stock-out risk per ingredient |
| `GET` | `/inventory/low-stock` | Low Stock |
| `GET` | `/inventory/movements` | List Movements |
| `POST` | `/inventory/movements` | Record a stock receipt, issue, adjustment or waste |
| `POST` | `/inventory/stock-count` | Record a physical count; posts an adjustment for the difference |

### recipes

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/recipes` | List Recipes |
| `GET` | `/recipes/products/{product_id}` | The product's active recipe, or null when it has none yet |
| `PUT` | `/recipes/products/{product_id}` | Save a recipe (creates a new version when it changes) |
| `DELETE` | `/recipes/products/{product_id}` | Remove Recipe |
| `GET` | `/recipes/products/{product_id}/versions` | Recipe Versions |

### suppliers

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/suppliers` | List Suppliers |
| `POST` | `/suppliers` | Create Supplier |
| `GET` | `/suppliers/{supplier_id}` | Get Supplier |
| `PATCH` | `/suppliers/{supplier_id}` | Update Supplier |
| `GET` | `/suppliers/{supplier_id}/ingredients` | Supplier Ingredients |
| `POST` | `/suppliers/{supplier_id}/ingredients` | Add Supplier Ingredient |
| `PATCH` | `/suppliers/{supplier_id}/ingredients/{link_id}` | Update Supplier Ingredient |
| `DELETE` | `/suppliers/{supplier_id}/ingredients/{link_id}` | Remove Supplier Ingredient |

### purchase-orders

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/purchase-orders` | List Purchase Orders |
| `POST` | `/purchase-orders` | Create Purchase Order |
| `GET` | `/purchase-orders/{po_id}` | Get Purchase Order |
| `PATCH` | `/purchase-orders/{po_id}` | Update Purchase Order |
| `POST` | `/purchase-orders/{po_id}/submit` | Submit Purchase Order |
| `POST` | `/purchase-orders/{po_id}/receive` | Receive a full or partial delivery (Idempotency-Key header required) |
| `POST` | `/purchase-orders/{po_id}/cancel` | Cancel Purchase Order |

### analytics

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/analytics/dashboard` | Role-aware dashboard (sections depend on the caller's permissions) |
| `GET` | `/analytics/summary` | Summary |
| `GET` | `/analytics/comparison` | Compare the range with the immediately preceding period of equal length |
| `GET` | `/analytics/sales-by-hour` | By Hour |
| `GET` | `/analytics/sales-by-day` | By Day |
| `GET` | `/analytics/sales-by-category` | By Category |
| `GET` | `/analytics/top-products` | Top Products |
| `GET` | `/analytics/slow-products` | Slow Products |
| `GET` | `/analytics/payment-distribution` | Payment Distribution |
| `GET` | `/analytics/ingredient-consumption` | Ingredient Consumption |
| `GET` | `/analytics/waste` | Waste |
| `GET` | `/analytics/purchases` | Purchase Spend |

### reports

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/reports/daily-sales.csv` | Daily Sales Report |
| `GET` | `/reports/product-sales.csv` | Product Sales Report |
| `GET` | `/reports/orders.csv` | Orders Report |
| `GET` | `/reports/inventory-movements.csv` | Movements Report |
| `GET` | `/reports/inventory-valuation.csv` | Valuation Report |
| `GET` | `/reports/purchases.csv` | Purchases Report |

### forecast

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/forecast/models` | List Models |
| `GET` | `/forecast/runs` | List Runs |
| `POST` | `/forecast/runs` | Backtest the models and generate a forecast |
| `GET` | `/forecast/latest` | Latest |
| `GET` | `/forecast/runs/{run_id}` | Get Run |
| `GET` | `/forecast/products/{product_id}/history` | Actual daily sales versus predictions, plus the latest future forecast |

### recommendations

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/recommendations/generate` | Generate |
| `GET` | `/recommendations` | List Recommendations |
| `POST` | `/recommendations/{rec_id}/approve` | Approve |
| `POST` | `/recommendations/{rec_id}/modify` | Modify |
| `POST` | `/recommendations/{rec_id}/reject` | Reject |
| `POST` | `/recommendations/purchase-orders` | Create DRAFT purchase orders from approved recommendations (never submitted automatically) |

### ai

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/ai/status` | Status |
| `POST` | `/ai/chat` | Chat |
| `GET` | `/ai/insights` | Deterministic insights (no LLM required) |

### realtime

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/events` | Events after a cursor (polling transport) |
| `GET` | `/events/stream` | Server-Sent Events stream of live updates |
| `GET` | `/notifications` | Notifications |
| `POST` | `/notifications/read` | Mark all as read |

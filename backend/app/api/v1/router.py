"""Version 1 API router."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    analytics,
    auth,
    catalog,
    customers,
    forecasting,
    health,
    internal,
    inventory,
    orders,
    purchasing,
    realtime,
    restaurants,
    tables,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(restaurants.router)
api_router.include_router(catalog.router)
api_router.include_router(tables.router)
api_router.include_router(inventory.router)
api_router.include_router(orders.router)
api_router.include_router(purchasing.router)
api_router.include_router(customers.router)
api_router.include_router(analytics.router)
api_router.include_router(forecasting.router)
api_router.include_router(ai.router)
api_router.include_router(realtime.router)
api_router.include_router(internal.router)

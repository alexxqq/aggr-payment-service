"""V1 API router — combines all sub-routers."""

from fastapi import APIRouter

from app.api.v1.checkout_sessions import router as checkout_sessions_router
from app.api.v1.payment_intents import router as payment_intents_router
from app.api.v1.paywalls import router as paywalls_router
from app.api.v1.prices import router as prices_router
from app.api.v1.products import router as products_router

router = APIRouter(prefix="/v1")

router.include_router(products_router)
router.include_router(prices_router)
router.include_router(paywalls_router)
router.include_router(payment_intents_router)
router.include_router(checkout_sessions_router)

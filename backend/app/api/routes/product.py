from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_product_status_service
from app.api.schemas import ProductStatusResponse
from app.application.product.status_service import ProductStatusService

router = APIRouter(prefix="/api/v1/product", tags=["product"])


@router.get("/status", response_model=ProductStatusResponse)
async def product_status(
    svc: ProductStatusService = Depends(get_product_status_service),
) -> ProductStatusResponse:
    status = await svc.status()
    return ProductStatusResponse(
        data_source=status.data_source,
        live_ready=status.live_ready,
        claim=status.claim,
        last_candle_time=status.last_candle_time,
        symbols_with_candles=status.symbols_with_candles,
        environment=status.environment,
        plug_and_play=(
            "Set MARKET_DATA_SOURCE=upstox and UPSTOX_ACCESS_TOKEN, restart, "
            "then run python scripts/refresh_market_data.py"
        ),
    )

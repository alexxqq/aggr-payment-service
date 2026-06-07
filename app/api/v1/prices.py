"""Price endpoints — stub (operates on prices directly by ID)."""

from fastapi import APIRouter

router = APIRouter(prefix="/prices", tags=["prices"])


@router.patch("/{price_id}")
async def update_price(price_id: str):
    raise NotImplementedError("Not implemented yet")


@router.delete("/{price_id}")
async def delete_price(price_id: str):
    raise NotImplementedError("Not implemented yet")

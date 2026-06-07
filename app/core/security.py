"""Internal security dependencies."""

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def verify_internal_secret(
    x_internal_secret: str = Header(...),
) -> None:
    """Verify X-Internal-Secret header for internal endpoints."""
    settings = get_settings()
    if x_internal_secret != settings.internal_api_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal secret",
        )

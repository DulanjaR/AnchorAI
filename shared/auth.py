from fastapi import Header, HTTPException, status

from shared.config import settings


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

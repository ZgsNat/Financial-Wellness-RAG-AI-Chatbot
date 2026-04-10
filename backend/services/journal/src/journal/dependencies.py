import uuid

from fastapi import Header, HTTPException, Request, status

from journal.config import get_settings

settings = get_settings()


async def get_current_user_id(
    x_authenticated_userid: str | None = Header(default=None),
    request: Request = None,  # type: ignore[assignment]
) -> uuid.UUID:
    if settings.debug and not x_authenticated_userid:
        dev_user = request.headers.get("X-Dev-User-Id")
        if dev_user:
            try:
                return uuid.UUID(dev_user)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-Dev-User-Id") from exc

    if not x_authenticated_userid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication")

    try:
        return uuid.UUID(x_authenticated_userid)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed user identifier") from exc
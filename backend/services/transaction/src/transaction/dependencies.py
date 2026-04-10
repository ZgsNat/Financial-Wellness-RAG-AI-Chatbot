"""
Auth dependencies for transaction-service.

Key design decision: this service does NOT verify JWTs itself.
Kong verifies the token and injects X-Consumer-ID and X-Authenticated-Userid headers.
We trust those headers because Kong strips them from incoming client requests
(via request-transformer plugin) before injecting its own values.

In local dev (without Kong), you can set SKIP_AUTH=true and pass user_id as a header directly.
"""

import uuid

from fastapi import Header, HTTPException, Request, status

from transaction.config import get_settings

settings = get_settings()


async def get_current_user_id(
    x_authenticated_userid: str | None = Header(default=None),
    request: Request = None,  # type: ignore[assignment]
) -> uuid.UUID:
    """
    Extracts user identity from Kong-injected header.
    Kong sets X-Authenticated-Userid to the JWT `sub` claim value.
    """
    if settings.debug and not x_authenticated_userid:
        # Dev convenience: allow passing user_id directly as header
        # Never reaches production because Kong always injects the header
        dev_user = request.headers.get("X-Dev-User-Id")
        if dev_user:
            try:
                return uuid.UUID(dev_user)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid X-Dev-User-Id format",
                ) from exc

    if not x_authenticated_userid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication",
        )

    try:
        return uuid.UUID(x_authenticated_userid)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed user identifier",
        ) from exc
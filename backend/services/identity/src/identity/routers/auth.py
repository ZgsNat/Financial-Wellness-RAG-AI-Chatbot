import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from identity.database import get_db
from identity.schemas.auth import (
    JWKSResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from identity.services.jwt_service import create_access_token, get_jwks
from identity.services.user_service import UserService

logger = structlog.get_logger()
router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    svc = UserService(db)
    try:
        user = await svc.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    logger.info("user_registered", user_id=str(user.id), email=user.email)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    svc = UserService(db)
    user = await svc.authenticate(payload.email, payload.password)
    if not user:
        # Deliberate vagueness — don't reveal whether email exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token, expires_in = create_access_token(user.id, user.email)
    logger.info("user_logged_in", user_id=str(user.id))
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/.well-known/jwks.json", response_model=JWKSResponse)
async def jwks() -> JWKSResponse:
    """
    Public key endpoint. Kong fetches this to verify RS256 tokens.
    No auth required — public by design.
    """
    return get_jwks()
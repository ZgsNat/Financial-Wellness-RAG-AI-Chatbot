import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


# ── Request schemas ────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── Response schemas ───────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int   # seconds


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── JWKS (public key endpoint for Kong / other services) ──────────────────

class JWKKey(BaseModel):
    kty: str
    use: str
    alg: str
    kid: str
    n: str    # RSA modulus (base64url)
    e: str    # RSA exponent (base64url)


class JWKSResponse(BaseModel):
    keys: list[JWKKey]
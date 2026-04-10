import base64
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jose import jwt

from identity.config import get_settings
from identity.schemas.auth import JWKKey, JWKSResponse

_settings = get_settings()

# kid ties token to a specific key — useful when rotating keys later.
# Simple approach: hash of public key content (first 8 hex chars).
def _compute_kid() -> str:
    import hashlib
    return hashlib.sha256(_settings.public_key.encode()).hexdigest()[:8]


KID = _compute_kid()


def create_access_token(user_id: uuid.UUID, email: str) -> tuple[str, int]:
    """
    Returns (encoded_jwt, expires_in_seconds).
    Claims follow standard OIDC conventions so Kong JWT plugin works out of the box.
    """
    expire_seconds = _settings.access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),       # subject — user UUID
        "email": email,
        "iat": now,
        "exp": now + timedelta(seconds=expire_seconds),
        "jti": str(uuid.uuid4()),  # unique token ID — useful for future blacklist
    }
    token = jwt.encode(
        payload,
        _settings.private_key,
        algorithm=_settings.jwt_algorithm,
        headers={"kid": KID},
    )
    return token, expire_seconds


@lru_cache
def get_jwks() -> JWKSResponse:
    """
    Build JWKS from the RSA public key.
    Kong fetches this endpoint to verify tokens without needing the private key.
    Cached in-memory — public key doesn't change at runtime.
    """
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    pub_key: RSAPublicKey = load_pem_public_key(  # type: ignore[assignment]
        _settings.public_key.encode(),
        backend=default_backend(),
    )
    pub_numbers = pub_key.public_numbers()

    def _b64url(n: int) -> str:
        # Convert RSA integer to base64url-encoded bytes (big-endian, no padding)
        byte_length = (n.bit_length() + 7) // 8
        raw = n.to_bytes(byte_length, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    key = JWKKey(
        kty="RSA",
        use="sig",
        alg="RS256",
        kid=KID,
        n=_b64url(pub_numbers.n),
        e=_b64url(pub_numbers.e),
    )
    return JWKSResponse(keys=[key])
import uuid

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models.user import User
from identity.schemas.auth import RegisterRequest

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(self, payload: RegisterRequest) -> User:
        existing = await self.get_by_email(payload.email)
        if existing:
            raise ValueError("Email already registered")

        user = User(
            email=payload.email,
            hashed_password=pwd_context.hash(payload.password),
            full_name=payload.full_name,
        )
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)
        return user

    def verify_password(self, plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self.get_by_email(email)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user
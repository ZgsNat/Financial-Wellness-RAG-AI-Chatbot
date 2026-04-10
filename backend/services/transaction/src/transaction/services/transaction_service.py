import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from transaction.models.transaction import Transaction
from transaction.schemas.transaction import TransactionCreate, TransactionUpdate


class TransactionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, user_id: uuid.UUID, payload: TransactionCreate) -> Transaction:
        tx = Transaction(
            user_id=user_id,
            amount=payload.amount,
            currency=payload.currency,
            type=payload.type,
            category=payload.category,
            note=payload.note,
            transaction_date=payload.transaction_date,
        )
        self._db.add(tx)
        await self._db.commit()
        await self._db.refresh(tx)
        return tx

    async def get(self, transaction_id: uuid.UUID, user_id: uuid.UUID) -> Transaction | None:
        result = await self._db.execute(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id,  # ownership check — not done by Kong
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[Transaction], int]:
        query = select(Transaction).where(Transaction.user_id == user_id)

        if date_from:
            query = query.where(Transaction.transaction_date >= date_from)
        if date_to:
            query = query.where(Transaction.transaction_date <= date_to)

        # Total count (same filters, no pagination)
        count_result = await self._db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        # Paginated results
        query = (
            query.order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._db.execute(query)
        return list(result.scalars().all()), total

    async def update(
        self,
        transaction_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: TransactionUpdate,
    ) -> Transaction | None:
        tx = await self.get(transaction_id, user_id)
        if not tx:
            return None

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tx, field, value)

        await self._db.commit()
        await self._db.refresh(tx)
        return tx

    async def delete(self, transaction_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        tx = await self.get(transaction_id, user_id)
        if not tx:
            return False
        await self._db.delete(tx)
        await self._db.commit()
        return True
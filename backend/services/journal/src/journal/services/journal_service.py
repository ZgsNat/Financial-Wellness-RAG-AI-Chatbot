import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from journal.models.journal import JournalEntry, MoodEntry
from journal.schemas.journal import JournalEntryCreate, JournalEntryUpdate, MoodEntryCreate


class JournalService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Mood ──────────────────────────────────────────────────────────────

    async def create_mood(self, user_id: uuid.UUID, payload: MoodEntryCreate) -> MoodEntry:
        entry = MoodEntry(user_id=user_id, score=payload.score, note=payload.note)
        self._db.add(entry)
        await self._db.commit()
        await self._db.refresh(entry)
        return entry

    async def list_moods(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[MoodEntry], int]:
        q = select(MoodEntry).where(MoodEntry.user_id == user_id)
        total = (await self._db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        items = (
            await self._db.execute(
                q.order_by(MoodEntry.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return list(items), total

    # ── Journal ───────────────────────────────────────────────────────────

    async def create_entry(self, user_id: uuid.UUID, payload: JournalEntryCreate) -> JournalEntry:
        word_count = len(payload.content.split())
        entry = JournalEntry(
            user_id=user_id,
            content=payload.content,
            word_count=word_count,
        )
        self._db.add(entry)
        await self._db.commit()
        await self._db.refresh(entry)
        return entry

    async def get_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> JournalEntry | None:
        result = await self._db.execute(
            select(JournalEntry).where(
                JournalEntry.id == entry_id,
                JournalEntry.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[JournalEntry], int]:
        q = select(JournalEntry).where(JournalEntry.user_id == user_id)
        total = (await self._db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        items = (
            await self._db.execute(
                q.order_by(JournalEntry.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return list(items), total

    async def update_entry(
        self,
        entry_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: JournalEntryUpdate,
    ) -> JournalEntry | None:
        entry = await self.get_entry(entry_id, user_id)
        if not entry:
            return None
        entry.content = payload.content
        entry.word_count = len(payload.content.split())
        await self._db.commit()
        await self._db.refresh(entry)
        return entry

    async def delete_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        entry = await self.get_entry(entry_id, user_id)
        if not entry:
            return False
        await self._db.delete(entry)
        await self._db.commit()
        return True
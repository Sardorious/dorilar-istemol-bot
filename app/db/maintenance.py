"""Bir martalik ma'lumot tozalash — bot ishga tushganda bajariladi.

Eski versiyada har yuklangan PDF yangi Patient yaratardi va eskilari
is_active=True holida qolib ketardi. Natijada scheduler bitta odamga
bir nechta (jumladan allaqachon tugagan) retsept bo'yicha eslatma yuborardi.

Yangi kod bunday holatni yaratmaydi, lekin mavjud bazani tuzatish kerak.
Funksiya idempotent — har startda xavfsiz ishlaydi.
"""
import logging

from sqlalchemy import select, update, func

from app.db.engine import AsyncSessionLocal
from app.db.models import Patient

logger = logging.getLogger(__name__)


async def deduplicate_active_patients() -> int:
    """Har bir telegram_id uchun faqat ENG YANGI retsept aktiv qoladi.

    Qaytaradi: arxivga o'tkazilgan retseptlar soni.
    """
    archived_total = 0

    async with AsyncSessionLocal() as session:
        # Bittadan ko'p aktiv retsepti bor foydalanuvchilar
        dupes = await session.execute(
            select(Patient.telegram_id)
            .where(Patient.is_active.is_(True))
            .group_by(Patient.telegram_id)
            .having(func.count(Patient.id) > 1)
        )
        tg_ids = [row[0] for row in dupes.all()]

        for tg_id in tg_ids:
            keep = (
                await session.execute(
                    select(Patient.id)
                    .where(
                        Patient.telegram_id == tg_id,
                        Patient.is_active.is_(True),
                    )
                    .order_by(Patient.created_at.desc(), Patient.id.desc())
                    .limit(1)
                )
            ).scalar_one()

            result = await session.execute(
                update(Patient)
                .where(
                    Patient.telegram_id == tg_id,
                    Patient.is_active.is_(True),
                    Patient.id != keep,
                )
                .values(is_active=False)
            )
            archived_total += result.rowcount or 0
            logger.info(
                "tg_id=%s: %s та эски рецепт архивга ўтказилди (актив: %s)",
                tg_id, result.rowcount, keep,
            )

        if archived_total:
            await session.commit()

    if archived_total:
        logger.warning(
            "Тозалаш: жами %s та дубликат рецепт ўчирилди (%s фойдаланувчи)",
            archived_total, len(tg_ids),
        )
    else:
        logger.info("Тозалаш: дубликат актив рецепт топилмади")

    return archived_total

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.triggers.cron import CronTrigger

from app import tz
from app.bot.handlers import router
from app.config import settings
from app.db import init_db
from app.db.maintenance import deduplicate_active_patients
from app.scheduler.daily import schedule_daily_reminders
from app.scheduler.jobs import scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    logger.info("База данных инициализирована")

    # Eski bazadagi dublikat aktiv retseptlarni tozalash (idempotent)
    await deduplicate_active_patients()
    logger.info(
        "Вақт зонаси: %s | ҳозир: %s",
        tz.TZ_NAME, tz.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
    )

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    start_scheduler()

    # Har kuni 00:05 da (Toshkent) shu kunning eslatmalari rejalashtiriladi.
    scheduler.add_job(
        schedule_daily_reminders,
        trigger=CronTrigger(hour=0, minute=5, timezone=tz.TZ_NAME),
        args=[bot],
        # DIQQAT: id 'dose_' prefiksi bilan boshlanmasligi shart —
        # _purge_daily_jobs aks holda cron jobning o'zini o'chirib yuboradi.
        id="cron_daily_scheduler",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Joblar xotirada saqlanadi (aiogram Bot obyekti pickle qilinmaydi,
    # shuning uchun persistent jobstore ishlatilmaydi). Restartdan keyin
    # kun jadvali shu yerda qayta tiklanadi — o'tib ketgan vaqtlar
    # schedule_reminder ichida tashlab yuboriladi, ya'ni "portlash" bo'lmaydi.
    await schedule_daily_reminders(bot)

    logger.info("Бот ишга тушмоқда...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db import init_db
from app.bot.handlers import router as patient_router
from app.bot.admin import router as admin_router
from app.scheduler.jobs import scheduler, start_scheduler
from app.scheduler.daily import schedule_daily_reminders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    logger.info("Database initialized")

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin_router)
    dp.include_router(patient_router)

    start_scheduler()

    # Schedule daily reminders at 00:01 every day
    scheduler.add_job(
        schedule_daily_reminders,
        trigger=CronTrigger(hour=0, minute=1),
        args=[bot],
        id="daily_reminder_scheduler",
        replace_existing=True
    )

    # Also run once at startup for today
    await schedule_daily_reminders(bot)

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

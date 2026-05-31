import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db import init_db
from app.bot.handlers import router
from app.scheduler.jobs import scheduler, start_scheduler
from app.scheduler.daily import schedule_daily_reminders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    logger.info("База данных инициализирована")

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    start_scheduler()

    scheduler.add_job(
        schedule_daily_reminders,
        trigger=CronTrigger(hour=0, minute=1),
        args=[bot],
        id="daily_reminder_scheduler",
        replace_existing=True
    )
    await schedule_daily_reminders(bot)

    logger.info("Бот ишга тушмоқда...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot
from app.db.engine import AsyncSessionLocal
from app.db import queries as q
from app.bot.keyboards import dose_keyboard

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


async def send_reminder(bot: Bot, telegram_id: int, dose_log_id: int, med_name: str, dose: str):
    try:
        text = (
            f"💊 <b>Dori vaqti!</b>\n\n"
            f"<b>{med_name}</b>\n"
            f"Miqdor: {dose}\n\n"
            f"Iste'mol qildingizmi?"
        )
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode="HTML",
            reply_markup=dose_keyboard(dose_log_id)
        )
    except Exception as e:
        logger.error(f"Failed to send reminder to {telegram_id}: {e}")


def schedule_reminder(
    bot: Bot,
    telegram_id: int,
    dose_log_id: int,
    med_name: str,
    dose: str,
    run_at: datetime,
    job_id: str
):
    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=run_at),
        args=[bot, telegram_id, dose_log_id, med_name, dose],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300
    )
    logger.info(f"Scheduled reminder job {job_id} at {run_at}")


def schedule_snooze(
    bot: Bot,
    telegram_id: int,
    dose_log_id: int,
    med_name: str,
    dose: str,
    minutes: int
):
    run_at = datetime.now() + timedelta(minutes=minutes)
    job_id = f"snooze_{dose_log_id}_{int(run_at.timestamp())}"
    schedule_reminder(bot, telegram_id, dose_log_id, med_name, dose, run_at, job_id)
    return run_at


def cancel_job(job_id: str):
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

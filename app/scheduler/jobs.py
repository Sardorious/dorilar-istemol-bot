import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot

from app import tz
from app.bot.keyboards import dose_keyboard

logger = logging.getLogger(__name__)

# MUHIM: barcha run_date lar tz-aware bo'lishi shart (app.tz orqali).
# Naive datetime uzatilsa APScheduler uni shu zonada deb qabul qiladi va
# server UTC bo'lsa 5 soatlik siljish yuzaga keladi.
scheduler = AsyncIOScheduler(
    # Matn sifatida — APScheduler 3.x pytz talab qiladi (ZoneInfo TypeError beradi)
    timezone=tz.TZ_NAME,
    job_defaults={
        # Kechikkan joblar to'planib, birdaniga otilib ketmasin
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 60,
    },
)


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler ishga tushdi (TZ=%s)", tz.TZ_NAME)


async def _dose_still_pending(dose_log_id: int) -> bool:
    """Eslatma yuborishdan oldin dozaning holatini qayta tekshiradi.

    Foydalanuvchi menyudan 'ичдим'/'ўтказдим' bosgan bo'lsa, allaqachon
    rejalashtirilgan job baribir otilib ketmasligi uchun kerak.
    """
    from sqlalchemy import select

    from app.db.engine import AsyncSessionLocal
    from app.db.models import DoseLog

    async with AsyncSessionLocal() as session:
        log = (
            await session.execute(select(DoseLog).where(DoseLog.id == dose_log_id))
        ).scalar_one_or_none()

    if log is None:
        logger.warning("DoseLog %s topilmadi — eslatma bekor qilindi", dose_log_id)
        return False
    if log.status in ("taken", "skipped"):
        logger.info(
            "DoseLog %s holati '%s' — eslatma yuborilmadi", dose_log_id, log.status
        )
        return False
    return True


async def send_reminder(
    bot: Bot, telegram_id: int, dose_log_id: int, med_name: str, dose: str
):
    if not await _dose_still_pending(dose_log_id):
        return

    try:
        text = (
            f"💊 <b>Дори вақти!</b>\n\n"
            f"<b>{med_name}</b>\n"
            f"Миқдор: {dose}\n\n"
            f"Истеъмол қилдингизми?"
        )
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode="HTML",
            reply_markup=dose_keyboard(dose_log_id),
        )
    except Exception as e:
        logger.error(f"Эслатма юборишда хатолик {telegram_id}: {e}")


def schedule_reminder(
    bot: Bot,
    telegram_id: int,
    dose_log_id: int,
    med_name: str,
    dose: str,
    run_at: datetime,
    job_id: str,
) -> bool:
    """Eslatmani rejalashtiradi. run_at tz-aware bo'lishi shart."""
    run_at = tz.make_aware(run_at)

    if run_at <= tz.now():
        logger.debug("O'tib ketgan vaqt, rejalashtirilmadi: %s — %s", job_id, run_at)
        return False

    # run_at allaqachon tz-aware — APScheduler uni o'zgartirmasdan qabul qiladi
    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=run_at, timezone=tz.TZ_NAME),
        args=[bot, telegram_id, dose_log_id, med_name, dose],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
    )
    logger.info("Эслатма режалаштирилди: %s — %s", job_id, run_at.strftime("%Y-%m-%d %H:%M %Z"))
    return True


def schedule_snooze(
    bot: Bot,
    telegram_id: int,
    dose_log_id: int,
    med_name: str,
    dose: str,
    minutes: int,
) -> datetime:
    run_at = tz.now() + timedelta(minutes=minutes)
    job_id = f"snooze_{dose_log_id}_{int(run_at.timestamp())}"
    schedule_reminder(bot, telegram_id, dose_log_id, med_name, dose, run_at, job_id)
    return run_at


def cancel_job(job_id: str):
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

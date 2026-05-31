import logging
from datetime import datetime, date
from aiogram import Bot
from app.db.engine import AsyncSessionLocal
from app.db import queries as q
from app.scheduler.jobs import schedule_reminder
from sqlalchemy import select
from app.db.models import Patient

logger = logging.getLogger(__name__)


async def schedule_daily_reminders(bot: Bot):
    """Called once at startup and then daily — schedules today's reminders for all patients."""
    today = date.today()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Patient).where(Patient.is_active, Patient.telegram_id.isnot(None))
        )
        patients = result.scalars().all()

    for patient in patients:
        start = patient.start_date.date() if hasattr(patient.start_date, 'date') else patient.start_date
        day = (today - start).days + 1
        if day < 1:
            continue

        async with AsyncSessionLocal() as session:
            meds = await q.get_meds_for_day(session, patient.id, day)
            for med in meds:
                if med.reminder_hour is None:
                    continue
                run_at = datetime.combine(
                    today,
                    datetime.min.time().replace(hour=med.reminder_hour, minute=med.reminder_minute or 0)
                )
                if run_at < datetime.now():
                    continue
                log = await q.get_or_create_dose_log(session, patient.id, med.id, day, run_at)
                if log.status in ("taken", "skipped"):
                    continue
                job_id = f"daily_{patient.id}_{med.id}_{today.isoformat()}"
                schedule_reminder(
                    bot=bot,
                    telegram_id=patient.telegram_id,
                    dose_log_id=log.id,
                    med_name=med.name,
                    dose=med.dose,
                    run_at=run_at,
                    job_id=job_id
                )
        logger.info(f"Scheduled reminders for patient {patient.patient_code} day {day}")

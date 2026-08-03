import logging

from aiogram import Bot
from apscheduler.jobstores.base import JobLookupError
from sqlalchemy import select

from app import tz
from app.db import queries as q
from app.db.engine import AsyncSessionLocal
from app.db.models import Patient
from app.scheduler.jobs import schedule_reminder, scheduler

logger = logging.getLogger(__name__)

DAILY_JOB_PREFIX = "dose_"


def _purge_daily_jobs():
    """Eski 'dose_*' joblarni tozalaydi.

    Retsept almashtirilganda yoki yangi PDF yuklanganda eski retseptning
    allaqachon rejalashtirilgan eslatmalari otilib ketmasligi uchun kerak.
    Funksiya jadvalni har safar noldan quradi — idempotent.

    Diqqat: 'snooze_*' joblarga tegilmaydi (foydalanuvchi o'zi so'ragan),
    cron job id si esa ataylab boshqa prefiks bilan nomlangan.
    """
    removed = 0
    for job in scheduler.get_jobs():
        if job.id.startswith(DAILY_JOB_PREFIX):
            try:
                scheduler.remove_job(job.id)
            except JobLookupError:
                # Job shu orada o'zi otilib bo'lgan — normal holat
                logger.debug("Job allaqachon yo'q: %s", job.id)
            else:
                removed += 1
    if removed:
        logger.info("%s та эски эслатма job тозаланди", removed)


async def schedule_daily_reminders(bot: Bot):
    """Bugungi kun uchun eslatmalarni rejalashtiradi.

    FAQAT aktiv bemorlar bo'yicha ishlaydi. Har bir telegram_id uchun
    bitta aktiv retsept bo'lishi kafolatlanadi (queries.create_patient_from_pdf),
    shuning uchun eski retseptlar eslatma yubormaydi.
    """
    today = tz.today()
    now = tz.now()

    _purge_daily_jobs()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Patient).where(
                Patient.is_active.is_(True),
                Patient.telegram_id.isnot(None),
            )
        )
        patients = result.scalars().all()

    total_scheduled = 0

    for patient in patients:
        start = tz.to_local_date(patient.start_date)
        day = (today - start).days + 1
        if day < 1:
            logger.info("Бемор %s: даволаниш ҳали бошланмаган (%s)", patient.id, start)
            continue

        scheduled_for_patient = 0

        async with AsyncSessionLocal() as session:
            meds = await q.get_meds_for_day(session, patient.id, day)

            if not meds:
                logger.info("Бемор %s: %s-кунда дори йўқ", patient.id, day)
                continue

            for med in meds:
                if med.reminder_hour is None:
                    logger.warning(
                        "Бемор %s, дори '%s' (slot=%s): эслатма вақти йўқ — ўтказилди",
                        patient.id, med.name, med.time_slot,
                    )
                    continue

                run_at = tz.at(today, med.reminder_hour, med.reminder_minute or 0)
                if run_at <= now:
                    # Bugun uchun vaqti o'tib ketgan — ertaga qayta rejalashtiriladi
                    continue

                log = await q.get_or_create_dose_log(
                    session, patient.id, med.id, day, run_at
                )
                if log.status in ("taken", "skipped"):
                    continue

                job_id = f"{DAILY_JOB_PREFIX}{patient.id}_{med.id}_{today.isoformat()}"
                if schedule_reminder(
                    bot=bot,
                    telegram_id=patient.telegram_id,
                    dose_log_id=log.id,
                    med_name=med.name,
                    dose=med.dose,
                    run_at=run_at,
                    job_id=job_id,
                ):
                    scheduled_for_patient += 1

        total_scheduled += scheduled_for_patient
        logger.info(
            "Бемор %s: %s-кун учун %s та эслатма режалаштирилди",
            patient.id, day, scheduled_for_patient,
        )

    logger.info(
        "Жами: %s та бемор, %s та эслатма (%s)",
        len(patients), total_scheduled, today.isoformat(),
    )

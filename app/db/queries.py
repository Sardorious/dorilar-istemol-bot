from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.models import Patient, Medication, DoseLog, ReminderJob


async def get_patient_by_code(session: AsyncSession, code: str) -> Optional[Patient]:
    result = await session.execute(
        select(Patient).where(Patient.patient_code == code, Patient.is_active)
    )
    return result.scalar_one_or_none()


async def get_patient_by_telegram_id(session: AsyncSession, tg_id: int) -> Optional[Patient]:
    result = await session.execute(
        select(Patient).where(Patient.telegram_id == tg_id, Patient.is_active)
    )
    return result.scalar_one_or_none()


async def link_patient_telegram(session: AsyncSession, patient: Patient, tg_id: int):
    patient.telegram_id = tg_id
    await session.commit()


async def get_meds_for_day(session: AsyncSession, patient_id: int, day: int) -> List[Medication]:
    result = await session.execute(
        select(Medication).where(
            Medication.patient_id == patient_id,
            Medication.start_day <= day,
            Medication.end_day >= day
        ).order_by(Medication.reminder_hour.nullslast(), Medication.time_slot)
    )
    return result.scalars().all()


async def get_or_create_dose_log(
    session: AsyncSession,
    patient_id: int,
    medication_id: int,
    day: int,
    scheduled_time: Optional[datetime] = None
) -> DoseLog:
    result = await session.execute(
        select(DoseLog).where(
            DoseLog.patient_id == patient_id,
            DoseLog.medication_id == medication_id,
            DoseLog.treatment_day == day
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        log = DoseLog(
            patient_id=patient_id,
            medication_id=medication_id,
            treatment_day=day,
            scheduled_time=scheduled_time,
            status="pending"
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
    return log


async def mark_dose_taken(session: AsyncSession, dose_log_id: int):
    await session.execute(
        update(DoseLog)
        .where(DoseLog.id == dose_log_id)
        .values(status="taken", taken_at=datetime.utcnow())
    )
    await session.commit()


async def mark_dose_skipped(session: AsyncSession, dose_log_id: int):
    await session.execute(
        update(DoseLog)
        .where(DoseLog.id == dose_log_id)
        .values(status="skipped")
    )
    await session.commit()


async def snooze_dose(session: AsyncSession, dose_log_id: int, minutes: int) -> datetime:
    snooze_time = datetime.utcnow() + timedelta(minutes=minutes)
    await session.execute(
        update(DoseLog)
        .where(DoseLog.id == dose_log_id)
        .values(status="snoozed", snooze_until=snooze_time)
    )
    await session.commit()
    return snooze_time


async def get_day_dose_logs(
    session: AsyncSession, patient_id: int, day: int
) -> List[DoseLog]:
    result = await session.execute(
        select(DoseLog).where(
            DoseLog.patient_id == patient_id,
            DoseLog.treatment_day == day
        )
    )
    return result.scalars().all()


async def get_history(
    session: AsyncSession, patient_id: int, limit: int = 50
) -> List[DoseLog]:
    result = await session.execute(
        select(DoseLog, Medication)
        .join(Medication, DoseLog.medication_id == Medication.id)
        .where(DoseLog.patient_id == patient_id)
        .order_by(DoseLog.treatment_day.desc(), DoseLog.created_at.desc())
        .limit(limit)
    )
    return result.all()


async def create_patient(
    session: AsyncSession,
    code: str,
    full_name: str,
    start_date: datetime,
    notes: str = ""
) -> Patient:
    patient = Patient(
        patient_code=code,
        full_name=full_name,
        start_date=start_date,
        notes=notes
    )
    session.add(patient)
    await session.commit()
    await session.refresh(patient)
    return patient


async def add_medication(session: AsyncSession, **kwargs) -> Medication:
    med = Medication(**kwargs)
    session.add(med)
    await session.commit()
    await session.refresh(med)
    return med


async def save_reminder_job(
    session: AsyncSession,
    dose_log_id: int,
    telegram_id: int,
    job_id: str,
    scheduled_at: datetime
):
    job = ReminderJob(
        dose_log_id=dose_log_id,
        telegram_id=telegram_id,
        job_id=job_id,
        scheduled_at=scheduled_at
    )
    session.add(job)
    await session.commit()

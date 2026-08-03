import logging
from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app import tz
from app.db.models import Patient, Medication, DoseLog

logger = logging.getLogger(__name__)

# Vaqt oralig'i -> eslatma soati. Toshkent vaqti bo'yicha.
REMINDER_MAP = {
    "morning":          (5,  30),
    "before_breakfast": (7,  0),
    "breakfast":        (7,  30),
    "afternoon":        (13, 0),
    "before_dinner":    (17, 0),
    "dinner":           (19, 0),
    "evening":          (20, 0),
    "night":            (21, 0),
    "injection":        (9,  0),
    "im":               (19, 30),
}

# Noma'lum slot kelib qolsa dori butunlay eslatilmay qolmasin
DEFAULT_SLOT = "breakfast"


def resolve_reminder_time(slot: str) -> tuple:
    """time_slot dan (soat, daqiqa) chiqaradi.

    Noma'lum slot uchun DEFAULT_SLOT ga tushadi va warning yozadi —
    ilgari bunday dorilar jimgina eslatmasiz qolib ketardi.
    """
    if slot in REMINDER_MAP:
        return REMINDER_MAP[slot]
    logger.warning(
        "Номаълум time_slot '%s' — '%s' вақти қўлланилди", slot, DEFAULT_SLOT
    )
    return REMINDER_MAP[DEFAULT_SLOT]


async def get_active_patient(session: AsyncSession, tg_id: int) -> Optional[Patient]:
    result = await session.execute(
        select(Patient).where(
            Patient.telegram_id == tg_id,
            Patient.is_active
        ).order_by(Patient.created_at.desc())
    )
    return result.scalars().first()


async def get_all_patients(session: AsyncSession, tg_id: int) -> List[Patient]:
    """Foydalanuvchining BARCHA retseptlari — arxivdagilari ham.

    Endi bir vaqtda faqat bitta retsept aktiv bo'ladi, shuning uchun
    bu yerda is_active bo'yicha filtr QO'YILMAYDI — aks holda foydalanuvchi
    eski retseptga qayta ololmay qoladi (patients_list_keyboard aktivini
    ✅ belgisi bilan ajratib ko'rsatadi).
    """
    result = await session.execute(
        select(Patient)
        .where(Patient.telegram_id == tg_id)
        .order_by(Patient.created_at.desc())
    )
    return result.scalars().all()


async def create_patient_from_pdf(
    session: AsyncSession,
    tg_id: int,
    full_name: Optional[str],
    start_date: datetime,
    diagnosis: Optional[str],
    diet_note: Optional[str],
    daily_notes: Optional[str],
    medications: list,
) -> Patient:
    # MUHIM: yangi retsept yuklanganda eskilari o'chiriladi.
    # Aks holda scheduler barcha aktiv retseptlar bo'yicha eslatma yuboradi
    # va foydalanuvchi allaqachon tugagan kurslardan ham xabar oladi.
    deactivated = await session.execute(
        update(Patient)
        .where(Patient.telegram_id == tg_id, Patient.is_active.is_(True))
        .values(is_active=False)
    )
    if deactivated.rowcount:
        logger.info(
            "tg_id=%s: %s та эски рецепт архивга ўтказилди", tg_id, deactivated.rowcount
        )

    patient = Patient(
        telegram_id=tg_id,
        full_name=full_name,
        start_date=start_date,
        diagnosis=diagnosis,
        diet_note=diet_note,
        daily_notes=daily_notes,
        is_active=True,
    )
    session.add(patient)
    await session.flush()

    for m in medications:
        slot = m.get("time_slot") or DEFAULT_SLOT
        rh, rm = resolve_reminder_time(slot)
        med = Medication(
            patient_id=patient.id,
            name=m["name"],
            dose=m.get("dose", ""),
            note=m.get("note", ""),
            time_label=m.get("time_label", ""),
            time_slot=slot,
            start_day=m.get("start_day", 1),
            end_day=m.get("end_day", 30),
            reminder_hour=rh,
            reminder_minute=rm,
        )
        session.add(med)

    await session.commit()
    await session.refresh(patient)
    return patient


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
    scheduled_time=None,
) -> DoseLog:
    result = await session.execute(
        select(DoseLog).where(
            DoseLog.patient_id == patient_id,
            DoseLog.medication_id == medication_id,
            DoseLog.treatment_day == day
        )
    )
    log = result.scalars().first()
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
    elif scheduled_time is not None and log.scheduled_time is None:
        # Log menyudan (vaqtsiz) yaratilgan bo'lsa, rejalashtirilgan vaqtni to'ldiramiz
        log.scheduled_time = scheduled_time
        await session.commit()
        await session.refresh(log)
    return log


async def mark_dose_taken(session: AsyncSession, dose_log_id: int):
    await session.execute(
        update(DoseLog).where(DoseLog.id == dose_log_id)
        .values(status="taken", taken_at=tz.now())
    )
    await session.commit()


async def mark_dose_skipped(session: AsyncSession, dose_log_id: int):
    await session.execute(
        update(DoseLog).where(DoseLog.id == dose_log_id).values(status="skipped")
    )
    await session.commit()


async def snooze_dose(session: AsyncSession, dose_log_id: int, minutes: int) -> datetime:
    # tz.now() — scheduler.schedule_snooze bilan bir xil soat
    snooze_time = tz.now() + timedelta(minutes=minutes)
    await session.execute(
        update(DoseLog).where(DoseLog.id == dose_log_id)
        .values(status="snoozed", snooze_until=snooze_time)
    )
    await session.commit()
    return snooze_time


async def get_history(session: AsyncSession, patient_id: int, limit: int = 40):
    result = await session.execute(
        select(DoseLog, Medication)
        .join(Medication, DoseLog.medication_id == Medication.id)
        .where(DoseLog.patient_id == patient_id)
        .order_by(DoseLog.treatment_day.desc(), DoseLog.created_at.desc())
        .limit(limit)
    )
    return result.all()


async def get_all_meds(session: AsyncSession, patient_id: int) -> List[Medication]:
    result = await session.execute(
        select(Medication).where(Medication.patient_id == patient_id)
        .order_by(Medication.start_day, Medication.time_slot)
    )
    return result.scalars().all()

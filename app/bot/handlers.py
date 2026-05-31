import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, Command

from app.db.engine import AsyncSessionLocal
from app.db import queries as q
from app.bot.states import AuthStates
from app.bot.keyboards import (
    main_menu_keyboard, calendar_keyboard,
    day_meds_keyboard, dose_keyboard, snooze_keyboard
)
from app.bot.utils import get_treatment_day, build_day_summary, format_status, format_time_slot
from app.scheduler.jobs import schedule_snooze

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        patient = await q.get_patient_by_telegram_id(session, message.from_user.id)

    if patient:
        day = get_treatment_day(patient)
        await message.answer(
            f"👋 Хуш келибсиз, <b>{patient.full_name}</b>!\n\n"
            f"Бугун даволанишингизнинг <b>{day}-куни</b>.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )
    else:
        await state.set_state(AuthStates.waiting_for_code)
        await message.answer(
            "👋 Ассалому алайкум!\n\n"
            "Илтимос, сизга берилган <b>бемор кодини</b> киритинг:\n\n"
            "Масалан: <code>BEMOR-001</code>",
            parse_mode="HTML"
        )


@router.message(AuthStates.waiting_for_code)
async def process_patient_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    async with AsyncSessionLocal() as session:
        patient = await q.get_patient_by_code(session, code)
        if not patient:
            await message.answer(
                "❌ Бемор коди топилмади. Илтимос, қайтадан текшириб киритинг:"
            )
            return
        await q.link_patient_telegram(session, patient, message.from_user.id)

    await state.clear()
    day = get_treatment_day(patient)
    await message.answer(
        f"✅ Муваффақиятли уланди!\n\n"
        f"<b>{patient.full_name}</b>\n"
        f"Даволаниш бошланган кун: {patient.start_date.strftime('%d.%m.%Y')}\n"
        f"Бугун: <b>{day}-кун</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )


@router.callback_query(F.data == "today")
async def cb_today(callback: CallbackQuery):
    await callback.answer()
    async with AsyncSessionLocal() as session:
        patient = await q.get_patient_by_telegram_id(session, callback.from_user.id)
        if not patient:
            await callback.message.answer("❌ Сиз тизимда рўйхатдан ўтмадингиз. /start босинг.")
            return
        day = get_treatment_day(patient)
        meds = await q.get_meds_for_day(session, patient.id, day)
        meds_with_logs = []
        for med in meds:
            log = await q.get_or_create_dose_log(session, patient.id, med.id, day)
            meds_with_logs.append((med, log))

    text = build_day_summary(day, meds_with_logs)
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=day_meds_keyboard(meds_with_logs)
    )


@router.callback_query(F.data == "show_calendar")
async def cb_show_calendar(callback: CallbackQuery):
    await callback.answer()
    async with AsyncSessionLocal() as session:
        patient = await q.get_patient_by_telegram_id(session, callback.from_user.id)
        if not patient:
            await callback.message.answer("❌ /start босинг.")
            return
        current_day = get_treatment_day(patient)
        from sqlalchemy import select, func
        from app.db.models import Medication
        result = await session.execute(
            select(func.max(Medication.end_day)).where(Medication.patient_id == patient.id)
        )
        max_day = result.scalar() or 30

    await callback.message.answer(
        "🗓 <b>Даволаниш календари</b>\n\nКунни танланг:",
        parse_mode="HTML",
        reply_markup=calendar_keyboard(min(max_day, 150), current_day)
    )


@router.callback_query(F.data.startswith("day:"))
async def cb_day_selected(callback: CallbackQuery):
    await callback.answer()
    day = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        patient = await q.get_patient_by_telegram_id(session, callback.from_user.id)
        if not patient:
            return
        meds = await q.get_meds_for_day(session, patient.id, day)
        meds_with_logs = []
        for med in meds:
            log = await q.get_or_create_dose_log(session, patient.id, med.id, day)
            meds_with_logs.append((med, log))

    text = build_day_summary(day, meds_with_logs)
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=day_meds_keyboard(meds_with_logs)
    )


@router.callback_query(F.data.startswith("med_detail:"))
async def cb_med_detail(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":")
    med_id = int(parts[1])
    log_id = int(parts[2])

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.db.models import Medication, DoseLog
        med_res = await session.execute(select(Medication).where(Medication.id == med_id))
        med = med_res.scalar_one_or_none()
        log_res = await session.execute(select(DoseLog).where(DoseLog.id == log_id))
        log = log_res.scalar_one_or_none()

    if not med:
        await callback.answer("Топилмади", show_alert=True)
        return

    status_text = format_status(log.status if log else "pending")
    text = (
        f"💊 <b>{med.name}</b>\n\n"
        f"📋 Миқдор: {med.dose}\n"
        f"⏰ Вақт: {format_time_slot(med.time_slot)}\n"
        f"📅 Давр: {med.start_day}–{med.end_day}-кун\n"
    )
    if med.note:
        text += f"ℹ️ Изоҳ: {med.note}\n"
    text += f"\n{status_text}"

    if log and log.status in ("pending", "snoozed"):
        await callback.message.answer(text, parse_mode="HTML", reply_markup=dose_keyboard(log.id))
    else:
        await callback.message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("taken:"))
async def cb_taken(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await q.mark_dose_taken(session, log_id)
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>Истеъмол қилинди!</b>",
        parse_mode="HTML"
    )
    await callback.answer("✅ Баракалла!", show_alert=False)


@router.callback_query(F.data.startswith("skip:"))
async def cb_skip(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await q.mark_dose_skipped(session, log_id)
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ Ўтказиб юборилди.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("snooze_menu:"))
async def cb_snooze_menu(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=snooze_keyboard(log_id))
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_dose:"))
async def cb_back_to_dose(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=dose_keyboard(log_id))
    await callback.answer()


@router.callback_query(F.data.startswith("snooze:"))
async def cb_snooze(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    log_id = int(parts[1])
    minutes = int(parts[2])

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.db.models import DoseLog, Medication
        log_res = await session.execute(select(DoseLog).where(DoseLog.id == log_id))
        log = log_res.scalar_one_or_none()
        med = None
        if log:
            med_res = await session.execute(select(Medication).where(Medication.id == log.medication_id))
            med = med_res.scalar_one_or_none()
            await q.snooze_dose(session, log_id, minutes)

    if log and med:
        schedule_snooze(
            bot=bot,
            telegram_id=callback.from_user.id,
            dose_log_id=log_id,
            med_name=med.name,
            dose=med.dose,
            minutes=minutes
        )
        if minutes < 60:
            label = f"{minutes} дақиқа"
        else:
            label = f"{minutes // 60} соат"
        await callback.message.edit_text(
            f"⏰ <b>{label} дан кейин эслатаман</b>\n\n{med.name}",
            parse_mode="HTML"
        )
    await callback.answer(f"⏰ {minutes} дақиқадан кейин эслатаман")


@router.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery):
    await callback.answer()
    async with AsyncSessionLocal() as session:
        patient = await q.get_patient_by_telegram_id(session, callback.from_user.id)
        if not patient:
            return
        rows = await q.get_history(session, patient.id, limit=30)

    if not rows:
        await callback.message.answer("📋 Тарих бўш.")
        return

    lines = ["📋 <b>Охирги истеъмол тарихи</b>\n"]
    current_day = None
    for log, med in rows:
        if log.treatment_day != current_day:
            current_day = log.treatment_day
            lines.append(f"\n<b>— {current_day}-кун —</b>")
        icon = {"taken": "✅", "skipped": "❌", "snoozed": "⏰", "pending": "💊"}.get(log.status, "💊")
        taken_str = log.taken_at.strftime("%H:%M") if log.taken_at else ""
        lines.append(f"{icon} {med.name[:35]} {taken_str}")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("Асосий менью:", reply_markup=main_menu_keyboard())

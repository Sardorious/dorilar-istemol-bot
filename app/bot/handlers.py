import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramBadRequest

from app.db.engine import AsyncSessionLocal
from app.db import queries as q
from app.bot.keyboards import (
    main_menu_keyboard, calendar_keyboard,
    day_meds_keyboard, dose_keyboard, snooze_keyboard,
    patients_list_keyboard,
)
from app import tz
from app.bot.utils import get_treatment_day, build_day_summary, format_status, format_time_slot
from app.scheduler.jobs import schedule_snooze
from app.scheduler.daily import schedule_daily_reminders

logger = logging.getLogger(__name__)
router = Router()


# ── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    async with AsyncSessionLocal() as session:
        patient = await q.get_active_patient(session, message.from_user.id)

    if patient:
        day = get_treatment_day(patient)
        name_line = f"<b>{patient.full_name}</b>\n" if patient.full_name else ""
        await message.answer(
            f"👋 Хуш келибсиз!\n\n{name_line}"
            f"Бугун даволанишнинг <b>{day}-куни</b>.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )
    else:
        await message.answer(
            "👋 Ассалому алайкум!\n\n"
            "Рецепт PDF файлини юборинг — мен ундаги дориларни ўқиб, "
            "кунлик жадвал тузаман. 📄"
        )


# ── PDF qabul qilish ─────────────────────────────────────────────────────────

@router.message(F.document)
async def handle_pdf(message: Message, bot: Bot):
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
        await message.answer("❌ Фақат PDF файл юборинг.")
        return

    status_msg = await message.answer("⏳ PDF ўқилмоқда, дорилар аниқланмоқда...")

    try:
        file = await bot.get_file(doc.file_id)
        pdf_bytes = await bot.download_file(file.file_path)
        pdf_content = pdf_bytes.read() if hasattr(pdf_bytes, "read") else bytes(pdf_bytes)

        from app.pdf_parser import parse_pdf_to_medications
        data = await parse_pdf_to_medications(pdf_content)

        meds = data.get("medications", [])
        if not meds:
            await status_msg.edit_text("❌ PDF дан дорилар топилмади. Бошқа файл юборинг.")
            return

        start_date = tz.now()
        if data.get("start_date"):
            try:
                parsed = datetime.strptime(data["start_date"], "%d.%m.%Y")
                start_date = tz.at(parsed.date(), 0, 0)
            except ValueError:
                logger.warning("start_date o'qilmadi: %r", data.get("start_date"))

        notes_list = data.get("daily_notes", [])
        notes_str = "\n".join(notes_list) if notes_list else None

        async with AsyncSessionLocal() as session:
            patient = await q.create_patient_from_pdf(
                session,
                tg_id=message.from_user.id,
                full_name=data.get("patient_name"),
                start_date=start_date,
                diagnosis=data.get("diagnosis"),
                diet_note=data.get("diet_note"),
                daily_notes=notes_str,
                medications=meds,
            )

        # Yangi retsept uchun eslatmalarni DARROV rejalashtiramiz —
        # aks holda foydalanuvchi ertangi 00:05 gacha eslatma olmaydi.
        await schedule_daily_reminders(bot)

        day = get_treatment_day(patient)
        name_line = f"👤 <b>{patient.full_name}</b>\n" if patient.full_name else ""
        diag_line = f"🩺 <i>{patient.diagnosis}</i>\n\n" if patient.diagnosis else "\n"

        await status_msg.edit_text(
            f"✅ <b>{len(meds)} та дори аниқланди!</b>\n\n"
            f"{name_line}{diag_line}"
            f"Бугун <b>{day}-кун</b>.",
            parse_mode="HTML",
        )
        await message.answer("Менюдан танланг:", reply_markup=main_menu_keyboard())

    except Exception as e:
        logger.error(f"PDF parse xatosi: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ PDF ўқишда хатолик юз берди. "
            "Файл тўғри рецепт эканлигини текшириб, қайта юборинг."
        )


# ── Reply tugmalar ────────────────────────────────────────────────────────────

@router.message(F.text == "🗓 Бугунги дорилар")
async def msg_today(message: Message):
    await _show_today(message)


@router.message(F.text == "📅 Календар")
async def msg_calendar(message: Message):
    await _show_calendar(message)


@router.message(F.text == "📋 Тарих")
async def msg_history(message: Message):
    await _show_history(message)


@router.message(F.text == "🛒 Харид рўйхати")
async def msg_shopping(message: Message):
    await _show_shopping(message)


@router.message(F.text == "📂 Рецептларим")
async def msg_patients(message: Message):
    await _show_patients(message)


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("Менюдан танланг:", reply_markup=main_menu_keyboard())


# ── Ichki funksiyalar ─────────────────────────────────────────────────────────

async def _show_today(message: Message):
    async with AsyncSessionLocal() as session:
        patient = await q.get_active_patient(session, message.from_user.id)
        if not patient:
            await message.answer("❌ Аввал PDF файл юборинг.")
            return
        day = get_treatment_day(patient)
        meds = await q.get_meds_for_day(session, patient.id, day)
        meds_with_logs = []
        for med in meds:
            log = await q.get_or_create_dose_log(session, patient.id, med.id, day)
            meds_with_logs.append((med, log))

    text = build_day_summary(day, meds_with_logs)
    await message.answer(text, parse_mode="HTML", reply_markup=day_meds_keyboard(meds_with_logs))


async def _show_calendar(message: Message):
    async with AsyncSessionLocal() as session:
        patient = await q.get_active_patient(session, message.from_user.id)
        if not patient:
            await message.answer("❌ Аввал PDF файл юборинг.")
            return
        current_day = get_treatment_day(patient)
        from sqlalchemy import select, func
        from app.db.models import Medication
        result = await session.execute(
            select(func.max(Medication.end_day)).where(Medication.patient_id == patient.id)
        )
        max_day = result.scalar() or 30

    await message.answer(
        "🗓 <b>Даволаниш календари</b>\n\nКунни танланг:",
        parse_mode="HTML",
        reply_markup=calendar_keyboard(min(max_day, 150), current_day)
    )


async def _show_history(message: Message):
    async with AsyncSessionLocal() as session:
        patient = await q.get_active_patient(session, message.from_user.id)
        if not patient:
            return
        rows = await q.get_history(session, patient.id, limit=30)

    if not rows:
        await message.answer("📋 Тарих бўш.")
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

    await message.answer("\n".join(lines), parse_mode="HTML")


async def _show_patients(message: Message):
    async with AsyncSessionLocal() as session:
        patients = await q.get_all_patients(session, message.from_user.id)

    if not patients:
        await message.answer("Рецептлар йўқ. PDF юборинг.")
        return

    await message.answer(
        "📋 <b>Сизнинг рецептларингиз:</b>",
        parse_mode="HTML",
        reply_markup=patients_list_keyboard(patients)
    )


async def _show_shopping(message: Message):
    async with AsyncSessionLocal() as session:
        patient = await q.get_active_patient(session, message.from_user.id)
        if not patient:
            await message.answer("❌ Аввал PDF файл юборинг.")
            return
        from app.db.queries import get_all_meds
        meds = await get_all_meds(session, patient.id)

    if not meds:
        await message.answer("Дорилар топилмади.")
        return

    from collections import defaultdict
    grouped = defaultdict(list)
    for med in meds:
        grouped[med.name].append(med)

    injection_slots = {"injection", "im"}
    regular = {}
    injections = {}

    for name, med_list in grouped.items():
        total_days = sum(m.end_day - m.start_day + 1 for m in med_list)
        slot = med_list[0].time_slot
        dose = med_list[0].dose

        # Kunlik necha mahal aniqlash
        times_per_day = 1
        dose_lower = dose.lower()
        if any(x in dose_lower for x in ["3 мах", "3 маҳал", "*3", "3мах"]):
            times_per_day = 3
        elif any(x in dose_lower for x in ["2 мах", "2 маҳал", "*2", "2мах"]):
            times_per_day = 2

        entry = {
            "name": name,
            "dose": dose,
            "total_days": total_days,
            "times_per_day": times_per_day,
        }
        if slot in injection_slots:
            injections[name] = entry
        else:
            regular[name] = entry

    lines = ["🛒 <b>Харид рўйхати</b>\n"]

    if regular:
        lines.append("💊 <b>Дорилар:</b>")
        for item in regular.values():
            total = item["total_days"] * item["times_per_day"]
            lines.append(f"\n• <b>{item['name']}</b>")
            lines.append(f"  {item['dose']}")
            lines.append(f"  📦 Тахминан <b>{total}</b> та ({item['total_days']} кун × {item['times_per_day']} маҳал)")

    if injections:
        lines.append("\n\n💉 <b>Капельница / Уколлар:</b>")
        for item in injections.values():
            lines.append(f"\n• <b>{item['name']}</b>")
            lines.append(f"  {item['dose']}")
            lines.append(f"  📦 <b>{item['total_days']}</b> процедура")

    lines.append("\n\n⚠️ <i>Миқдорлар тахминий — дорихонада аниқлаштиринг.</i>")

    text = "\n".join(lines)
    if len(text) > 4000:
        mid = len(lines) // 2
        await message.answer("\n".join(lines[:mid]), parse_mode="HTML")
        await message.answer("\n".join(lines[mid:]), parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# ── Callback handlers ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "today")
async def cb_today(callback: CallbackQuery):
    await callback.answer()
    await _show_today(callback.message)


@router.callback_query(F.data == "show_calendar")
async def cb_show_calendar(callback: CallbackQuery):
    await callback.answer()
    await _show_calendar(callback.message)


@router.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery):
    await callback.answer()
    await _show_history(callback.message)


@router.callback_query(F.data == "my_patients")
async def cb_my_patients(callback: CallbackQuery):
    await callback.answer()
    await _show_patients(callback.message)


@router.callback_query(F.data == "shopping_list")
async def cb_shopping_list(callback: CallbackQuery):
    await callback.answer()
    await _show_shopping(callback.message)


@router.callback_query(F.data.startswith("day:"))
async def cb_day_selected(callback: CallbackQuery):
    await callback.answer()
    day = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        patient = await q.get_active_patient(session, callback.from_user.id)
        if not patient:
            return
        meds = await q.get_meds_for_day(session, patient.id, day)
        meds_with_logs = []
        for med in meds:
            log = await q.get_or_create_dose_log(session, patient.id, med.id, day)
            meds_with_logs.append((med, log))

    text = build_day_summary(day, meds_with_logs)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=day_meds_keyboard(meds_with_logs))


@router.callback_query(F.data.startswith("med_detail:"))
async def cb_med_detail(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":")
    med_id, log_id = int(parts[1]), int(parts[2])

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.db.models import Medication, DoseLog
        med = (await session.execute(select(Medication).where(Medication.id == med_id))).scalar_one_or_none()
        log = (await session.execute(select(DoseLog).where(DoseLog.id == log_id))).scalar_one_or_none()

    if not med:
        await callback.answer("Топилмади", show_alert=True)
        return

    text = (
        f"💊 <b>{med.name}</b>\n\n"
        f"📋 Миқдор: {med.dose}\n"
        f"⏰ Вақт: {format_time_slot(med.time_slot)}\n"
        f"📅 Давр: {med.start_day}–{med.end_day}-кун\n"
    )
    if med.note:
        text += f"ℹ️ Изоҳ: {med.note}\n"
    text += f"\n{format_status(log.status if log else 'pending')}"

    kb = dose_keyboard(log.id) if log and log.status in ("pending", "snoozed") else None
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


async def _append_to_message(callback: CallbackQuery, suffix: str):
    """Xabar matniga natija qo'shadi. Matn yo'q/o'zgarmagan holatlarda yiqilmaydi."""
    base = callback.message.html_text if callback.message.text else ""
    try:
        await callback.message.edit_text(base + suffix, parse_mode="HTML")
    except TelegramBadRequest as e:
        logger.warning(f"Xabarni tahrirlab bo'lmadi: {e}")
        await callback.message.answer(suffix.strip(), parse_mode="HTML")


@router.callback_query(F.data.startswith("taken:"))
async def cb_taken(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await q.mark_dose_taken(session, log_id)
    await _append_to_message(callback, "\n\n✅ <b>Истеъмол қилинди!</b>")
    await callback.answer("✅ Баракалла!")


@router.callback_query(F.data.startswith("skip:"))
async def cb_skip(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await q.mark_dose_skipped(session, log_id)
    await _append_to_message(callback, "\n\n❌ Ўтказиб юборилди.")
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
    log_id, minutes = int(parts[1]), int(parts[2])

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.db.models import DoseLog, Medication
        log = (await session.execute(select(DoseLog).where(DoseLog.id == log_id))).scalar_one_or_none()
        med = None
        if log:
            med = (await session.execute(select(Medication).where(Medication.id == log.medication_id))).scalar_one_or_none()
            await q.snooze_dose(session, log_id, minutes)

    if log and med:
        schedule_snooze(bot=bot, telegram_id=callback.from_user.id,
                        dose_log_id=log_id, med_name=med.name, dose=med.dose, minutes=minutes)
        label = f"{minutes} дақиқа" if minutes < 60 else f"{minutes // 60} соат"
        await callback.message.edit_text(
            f"⏰ <b>{label} дан кейин эслатаман</b>\n\n{med.name}", parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("switch_patient:"))
async def cb_switch_patient(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    patient_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, update
        from app.db.models import Patient
        await session.execute(
            update(Patient).where(Patient.telegram_id == callback.from_user.id).values(is_active=False)
        )
        await session.execute(
            update(Patient).where(Patient.id == patient_id).values(is_active=True)
        )
        await session.commit()
        patient = (await session.execute(select(Patient).where(Patient.id == patient_id))).scalar_one_or_none()

    # Aktiv retsept o'zgardi — eslatmalar jadvalini qayta quramiz
    await schedule_daily_reminders(bot)

    if patient:
        day = get_treatment_day(patient)
        name = patient.full_name or "Бемор"
        await callback.message.answer(
            f"✅ <b>{name}</b> — {day}-кун",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )

import logging
from collections import defaultdict
from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select, update

from app import tz
from app.bot.keyboards import (
    BTN_CALENDAR,
    BTN_HISTORY,
    BTN_PATIENTS,
    BTN_SHOPPING,
    BTN_TODAY,
    MENU_BUTTONS,
    calendar_keyboard,
    day_meds_keyboard,
    dose_keyboard,
    main_menu_keyboard,
    patients_list_keyboard,
    snooze_keyboard,
    start_date_keyboard,
)
from app.bot.states import PrescriptionSetup
from app.bot.utils import (
    build_day_summary,
    format_status,
    format_time_slot,
    get_treatment_day,
    parse_user_date,
    validate_start_date,
)
from app.db import queries as q
from app.db.engine import AsyncSessionLocal
from app.db.models import DoseLog, Medication, Patient
from app.pdf_parser import ParserUnavailableError, parse_pdf_to_medications
from app.scheduler.daily import schedule_daily_reminders
from app.scheduler.jobs import schedule_snooze

logger = logging.getLogger(__name__)
router = Router()


# ── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    # Yarim qolgan sana kiritish oqimini tozalaymiz
    await state.clear()
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
async def handle_pdf(message: Message, bot: Bot, state: FSMContext):
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
        await message.answer("❌ Фақат PDF файл юборинг.")
        return

    status_msg = await message.answer("⏳ PDF ўқилмоқда, дорилар аниқланмоқда...")

    try:
        file = await bot.get_file(doc.file_id)
        pdf_bytes = await bot.download_file(file.file_path)
        pdf_content = pdf_bytes.read() if hasattr(pdf_bytes, "read") else bytes(pdf_bytes)

        data = await parse_pdf_to_medications(pdf_content)

        meds = data.get("medications", [])
        if not meds:
            await status_msg.edit_text("❌ PDF дан дорилар топилмади. Бошқа файл юборинг.")
            return

        # Retseptda sana bo'lsa — taklif sifatida ko'rsatamiz, lekin
        # yakuniy qarorni foydalanuvchi qabul qiladi.
        hint = ""
        if data.get("start_date"):
            hint = f"\n📄 Рецептда: <b>{data['start_date']}</b>"

        await state.set_state(PrescriptionSetup.waiting_for_start_date)
        await state.update_data(pdf_data=data)

        name_line = f"👤 <b>{data.get('patient_name')}</b>\n" if data.get("patient_name") else ""
        diag = data.get("diagnosis")
        diag_line = f"🩺 <i>{diag}</i>\n" if diag else ""

        await status_msg.edit_text(
            f"✅ <b>{len(meds)} та дори аниқланди!</b>\n\n"
            f"{name_line}{diag_line}{hint}\n\n"
            f"❓ <b>Даволанишни қайси кундан бошлагансиз?</b>\n"
            f"<i>Бу 1-кун ҳисобланади.</i>",
            parse_mode="HTML",
            reply_markup=start_date_keyboard(),
        )

    except ParserUnavailableError:
        await state.clear()
        logger.exception("Таҳлил хизмати ишламаяпти")
        await status_msg.edit_text(
            "⚠️ <b>Хизмат вақтинча ишламаяпти.</b>\n\n"
            "Бу файлингиздаги муаммо эмас. Бироздан кейин қайта уриниб кўринг — "
            "муаммо давом этса, админга хабар беринг.",
            parse_mode="HTML",
        )

    except Exception as e:
        await state.clear()
        logger.exception("PDF parse xatosi: %s", e)
        await status_msg.edit_text(
            "❌ PDF ўқишда хатолик юз берди. "
            "Файл тўғри рецепт эканлигини текшириб, қайта юборинг."
        )


# ── Боshlanish kunini so'rash ────────────────────────────────────────────────

async def _create_from_state(
    message: Message, state: FSMContext, bot: Bot, start_day: date
) -> bool:
    """FSM da saqlangan PDF ma'lumotidan bemor yaratadi."""
    stored = await state.get_data()
    data = stored.get("pdf_data")
    if not data:
        await message.answer("❌ Маълумот эскирди. PDF ни қайта юборинг.")
        await state.clear()
        return False

    notes_list = data.get("daily_notes", [])
    notes_str = "\n".join(notes_list) if notes_list else None

    async with AsyncSessionLocal() as session:
        patient = await q.create_patient_from_pdf(
            session,
            tg_id=message.chat.id,
            full_name=data.get("patient_name"),
            start_date=tz.at(start_day, 0, 0),
            diagnosis=data.get("diagnosis"),
            diet_note=data.get("diet_note"),
            daily_notes=notes_str,
            medications=data.get("medications", []),
        )

    await state.clear()

    # Eslatmalarni darrov rejalashtiramiz — ertangi 00:05 ni kutmasin
    await schedule_daily_reminders(bot)

    day = get_treatment_day(patient)
    await message.answer(
        f"✅ <b>Жадвал тайёр!</b>\n\n"
        f"📅 Бошланиш: <b>{start_day.strftime('%d.%m.%Y')}</b>\n"
        f"📍 Бугун — <b>{day}-кун</b>\n\n"
        f"<i>Ўтган кунларни «📅 Календар» дан белгилашингиз мумкин.</i>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return True


@router.callback_query(
    PrescriptionSetup.waiting_for_start_date, F.data.startswith("setdate:")
)
async def cb_set_start_date(callback: CallbackQuery, bot: Bot, state: FSMContext):
    choice = callback.data.split(":")[1]

    if choice == "manual":
        await callback.answer()
        await callback.message.answer(
            "✏️ Санани <b>КК.ОО.ЙЙЙЙ</b> кўринишида ёзинг.\n"
            "<i>Масалан: 25.07.2026</i>",
            parse_mode="HTML",
        )
        return

    start_day = tz.today() - timedelta(days=int(choice))
    await callback.answer()
    await _create_from_state(callback.message, state, bot, start_day)


@router.message(
    PrescriptionSetup.waiting_for_start_date, F.text, ~F.text.in_(MENU_BUTTONS)
)
async def msg_start_date_manual(message: Message, bot: Bot, state: FSMContext):
    parsed = parse_user_date(message.text)
    if parsed is None:
        await message.answer(
            "❌ Сана тушунарсиз. <b>КК.ОО.ЙЙЙЙ</b> кўринишида ёзинг.\n"
            "<i>Масалан: 25.07.2026</i>",
            parse_mode="HTML",
        )
        return

    error = validate_start_date(parsed)
    if error:
        await message.answer(error)
        return

    await _create_from_state(message, state, bot, parsed)


# ── Reply tugmalar ────────────────────────────────────────────────────────────

@router.message(F.text == BTN_TODAY)
async def msg_today(message: Message, state: FSMContext):
    await state.clear()
    await _show_today(message)


@router.message(F.text == BTN_CALENDAR)
async def msg_calendar(message: Message, state: FSMContext):
    await state.clear()
    await _show_calendar(message)


@router.message(F.text == BTN_HISTORY)
async def msg_history(message: Message, state: FSMContext):
    await state.clear()
    await _show_history(message)


@router.message(F.text == BTN_SHOPPING)
async def msg_shopping(message: Message, state: FSMContext):
    await state.clear()
    await _show_shopping(message)


@router.message(F.text == BTN_PATIENTS)
async def msg_patients(message: Message, state: FSMContext):
    await state.clear()
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
        meds = await q.get_all_meds(session, patient.id)

    if not meds:
        await message.answer("Дорилар топилмади.")
        return

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

    # Holat қандай бўлишидан қатъи назар тугмалар кўрсатилади —
    # ўтган кунни тўлдириш ёки хато белгини тузатиш учун.
    kb = dose_keyboard(log.id, log.status) if log else None
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


# Xabar oxiridagi holat qatorini ajratuvchi belgi. Shu belgi tufayli
# holat qayta-qayta qo'shilib ketmaydi — har safar almashtiriladi.
_STATUS_SEP = "\n\n───────\n"


async def _refresh_dose_message(callback: CallbackQuery, log_id: int, status: str):
    """Xabar matnidagi holatni yangilaydi va tugmalarni qayta chizadi."""
    base = (callback.message.html_text or "").split(_STATUS_SEP)[0]
    text = f"{base}{_STATUS_SEP}{format_status(status)}"
    try:
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=dose_keyboard(log_id, status)
        )
    except TelegramBadRequest as e:
        # Matn o'zgarmagan bo'lsa Telegram xato beradi — faqat tugmalarni yangilaymiz
        logger.debug("Xabar matni tahrirlanmadi: %s", e)
        try:
            await callback.message.edit_reply_markup(
                reply_markup=dose_keyboard(log_id, status)
            )
        except TelegramBadRequest:
            pass


@router.callback_query(F.data.startswith("taken:"))
async def cb_taken(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await q.mark_dose_taken(session, log_id)
    await _refresh_dose_message(callback, log_id, "taken")
    await callback.answer("✅ Баракалла!")


@router.callback_query(F.data.startswith("skip:"))
async def cb_skip(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await q.mark_dose_skipped(session, log_id)
    await _refresh_dose_message(callback, log_id, "skipped")
    await callback.answer("❌ Ўтказиб юборилди")


@router.callback_query(F.data.startswith("unmark:"))
async def cb_unmark(callback: CallbackQuery):
    """Belgini olib tashlash — xato bosilgan bo'lsa."""
    log_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await q.mark_dose_pending(session, log_id)
    await _refresh_dose_message(callback, log_id, "pending")
    await callback.answer("↩️ Белги олиб ташланди")


@router.callback_query(F.data.startswith("snooze_menu:"))
async def cb_snooze_menu(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=snooze_keyboard(log_id))
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_dose:"))
async def cb_back_to_dose(callback: CallbackQuery):
    log_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        log = (
            await session.execute(select(DoseLog).where(DoseLog.id == log_id))
        ).scalar_one_or_none()
    status = log.status if log else "pending"
    await callback.message.edit_reply_markup(reply_markup=dose_keyboard(log_id, status))
    await callback.answer()


@router.callback_query(F.data.startswith("snooze:"))
async def cb_snooze(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    log_id, minutes = int(parts[1]), int(parts[2])

    async with AsyncSessionLocal() as session:
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


@router.callback_query(F.data == "edit_start_date")
async def cb_edit_start_date(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        patient = await q.get_active_patient(session, callback.from_user.id)

    if not patient:
        await callback.answer("Аввал PDF юборинг", show_alert=True)
        return

    current = tz.to_local_date(patient.start_date)
    await state.set_state(PrescriptionSetup.waiting_for_new_start_date)
    await state.update_data(patient_id=patient.id)
    await callback.answer()
    await callback.message.answer(
        f"📅 Ҳозирги бошланиш куни: <b>{current.strftime('%d.%m.%Y')}</b>\n\n"
        f"❓ Янги санани танланг:",
        parse_mode="HTML",
        reply_markup=start_date_keyboard(prefix="newdate"),
    )


async def _apply_new_start_date(
    message: Message, state: FSMContext, bot: Bot, start_day: date
):
    stored = await state.get_data()
    patient_id = stored.get("patient_id")
    if not patient_id:
        await message.answer("❌ Маълумот эскирди. Қайтадан уриниб кўринг.")
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        await q.set_patient_start_date(session, patient_id, tz.at(start_day, 0, 0))
        patient = (
            await session.execute(select(Patient).where(Patient.id == patient_id))
        ).scalar_one_or_none()

    await state.clear()
    await schedule_daily_reminders(bot)

    day = get_treatment_day(patient) if patient else 1
    await message.answer(
        f"✅ Бошланиш куни <b>{start_day.strftime('%d.%m.%Y')}</b> га ўзгартирилди.\n"
        f"📍 Бугун — <b>{day}-кун</b>.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(
    PrescriptionSetup.waiting_for_new_start_date, F.data.startswith("newdate:")
)
async def cb_new_start_date(callback: CallbackQuery, bot: Bot, state: FSMContext):
    choice = callback.data.split(":")[1]

    if choice == "manual":
        await callback.answer()
        await callback.message.answer(
            "✏️ Санани <b>КК.ОО.ЙЙЙЙ</b> кўринишида ёзинг.",
            parse_mode="HTML",
        )
        return

    await callback.answer()
    await _apply_new_start_date(
        callback.message, state, bot, tz.today() - timedelta(days=int(choice))
    )


@router.message(
    PrescriptionSetup.waiting_for_new_start_date, F.text, ~F.text.in_(MENU_BUTTONS)
)
async def msg_new_start_date_manual(message: Message, bot: Bot, state: FSMContext):
    parsed = parse_user_date(message.text)
    if parsed is None:
        await message.answer(
            "❌ Сана тушунарсиз. <b>КК.ОО.ЙЙЙЙ</b> кўринишида ёзинг.",
            parse_mode="HTML",
        )
        return

    error = validate_start_date(parsed)
    if error:
        await message.answer(error)
        return

    await _apply_new_start_date(message, state, bot, parsed)


@router.callback_query(F.data.startswith("switch_patient:"))
async def cb_switch_patient(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    patient_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
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

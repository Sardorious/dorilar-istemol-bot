import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import settings
from app.db.engine import AsyncSessionLocal
from app.db import queries as q
from app.bot.states import AdminStates
from app.bot.keyboards import admin_keyboard

logger = logging.getLogger(__name__)
router = Router()

TIME_SLOTS = [
    ("morning",          "Бомдод 05:30"),
    ("before_breakfast", "Нонушта олдин 07:00"),
    ("breakfast",        "Нонушта вақтида 07:30"),
    ("afternoon",        "Тушлик 13:00"),
    ("before_dinner",    "Кечки овқат олдин 17:00"),
    ("dinner",           "Кечки овқат 19:00"),
    ("evening",          "Кечқурун 20:00"),
    ("night",            "Ухлаш олдин 21:00"),
    ("injection",        "Капельница"),
    ("im",               "Мушак ичига"),
]

REMINDER_TIMES = {
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


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Рухсат йўқ.")
        return
    await message.answer("👨‍⚕️ Админ панел:", reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin_add_patient")
async def cb_add_patient(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Рухсат йўқ", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_patient_code)
    await callback.message.answer(
        "Янги бемор қўшиш:\n\n"
        "Бемор кодини киритинг (масалан: BEMOR-001):"
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_patient_code)
async def process_admin_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    async with AsyncSessionLocal() as session:
        existing = await q.get_patient_by_code(session, code)
    if existing:
        await message.answer(f"❌ '{code}' коди аллақачон мавжуд. Бошқа код киритинг:")
        return
    await state.update_data(code=code)
    await state.set_state(AdminStates.waiting_for_patient_name)
    await message.answer("Бемор тўлиқ исмини киритинг:")


@router.message(AdminStates.waiting_for_patient_name)
async def process_admin_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(AdminStates.waiting_for_start_date)
    await message.answer(
        "Даволаниш бошланиш санасини киритинг (КК.ОО.ЙЙЙЙ):\n"
        "Масалан: 01.05.2026\n\n"
        "Бугун учун «бугун» ёзинг."
    )


@router.message(AdminStates.waiting_for_start_date)
async def process_admin_date(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ("бугун", "bugun", "today"):
        start_date = datetime.now()
    else:
        try:
            start_date = datetime.strptime(text, "%d.%m.%Y")
        except ValueError:
            await message.answer("❌ Нотўғри формат. КК.ОО.ЙЙЙЙ кўринишида киритинг:")
            return
    await state.update_data(start_date=start_date)
    await state.set_state(AdminStates.waiting_for_notes)
    await message.answer("Изоҳ (ихтиёрий, ўтказиб юбориш учун «-» ёзинг):")


@router.message(AdminStates.waiting_for_notes)
async def process_admin_notes(message: Message, state: FSMContext):
    notes = "" if message.text.strip() == "-" else message.text.strip()
    data = await state.get_data()

    async with AsyncSessionLocal() as session:
        patient = await q.create_patient(
            session,
            code=data["code"],
            full_name=data["full_name"],
            start_date=data["start_date"],
            notes=notes
        )

    await state.update_data(patient_id=patient.id)
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Стандарт рецепт юклаш", callback_data=f"load_default:{patient.id}")
    builder.button(text="➕ Дори қўшиш",             callback_data=f"add_med:{patient.id}")
    builder.adjust(1)
    await message.answer(
        f"✅ Бемор яратилди!\n\n"
        f"Код: <b>{patient.patient_code}</b>\n"
        f"Исм: {patient.full_name}\n\n"
        f"Нима қилмоқчисиз?",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("load_default:"))
async def cb_load_default(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Рухсат йўқ", show_alert=True)
        return
    patient_id = int(callback.data.split(":")[1])
    await callback.answer("Юкланмоқда...", show_alert=False)

    from app.bot.default_recipe import DEFAULT_MEDS, DAILY_NOTES, DIET_NOTE, PURCHASE_NOTE, PATIENT_META
    async with AsyncSessionLocal() as session:
        count = 0
        for med_data in DEFAULT_MEDS:
            slot = med_data["time_slot"]
            rh, rm = REMINDER_TIMES.get(slot, (None, None))
            await q.add_medication(
                session,
                patient_id=patient_id,
                name=med_data["name"],
                dose=med_data["dose"],
                note=med_data.get("note", ""),
                time_label=med_data["time_label"],
                time_slot=slot,
                start_day=med_data["start_day"],
                end_day=med_data["end_day"],
                reminder_hour=rh,
                reminder_minute=rm,
            )
            count += 1

    notes_text = "\n".join(f"• {n}" for n in DAILY_NOTES)
    await callback.message.answer(
        f"✅ <b>{count} та дори юкланди!</b>\n\n"
        f"🩺 <b>Ташхис:</b>\n<i>{PATIENT_META['diagnosis']}</i>\n\n"
        f"🥗 <b>Диета:</b> {DIET_NOTE}\n\n"
        f"📋 <b>Кундалик эслатмалар:</b>\n{notes_text}\n\n"
        f"ℹ️ {PURCHASE_NOTE}",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("add_med:"))
async def cb_add_med(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Рухсат йўқ", show_alert=True)
        return
    patient_id = int(callback.data.split(":")[1])
    await state.update_data(patient_id=patient_id)
    await state.set_state(AdminStates.adding_med_name)
    await callback.message.answer("Дори номини киритинг:")
    await callback.answer()


@router.message(AdminStates.adding_med_name)
async def process_med_name(message: Message, state: FSMContext):
    await state.update_data(med_name=message.text.strip())
    await state.set_state(AdminStates.adding_med_dose)
    await message.answer("Миқдорини киритинг (масалан: 1 та, 2 капсул, 5 г):")


@router.message(AdminStates.adding_med_dose)
async def process_med_dose(message: Message, state: FSMContext):
    await state.update_data(med_dose=message.text.strip())
    await state.set_state(AdminStates.adding_med_time_slot)

    builder = InlineKeyboardBuilder()
    for slot, label in TIME_SLOTS:
        builder.button(text=label, callback_data=f"slot:{slot}")
    builder.adjust(2)
    await message.answer("Қайси вақтда?", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("slot:"), AdminStates.adding_med_time_slot)
async def process_slot(callback: CallbackQuery, state: FSMContext):
    slot = callback.data.split(":")[1]
    await state.update_data(time_slot=slot)
    await state.set_state(AdminStates.adding_med_start_day)
    await callback.message.answer("Неча-кундан бошланади? (масалан: 1):")
    await callback.answer()


@router.message(AdminStates.adding_med_start_day)
async def process_start_day(message: Message, state: FSMContext):
    try:
        start_day = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Рақам киритинг:")
        return
    await state.update_data(start_day=start_day)
    await state.set_state(AdminStates.adding_med_end_day)
    await message.answer("Неча-кунгача? (масалан: 30, ёки 365 — 1 йил):")


@router.message(AdminStates.adding_med_end_day)
async def process_end_day(message: Message, state: FSMContext):
    try:
        end_day = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Рақам киритинг:")
        return

    data = await state.get_data()
    slot = data.get("time_slot", "breakfast")
    rh, rm = REMINDER_TIMES.get(slot, (None, None))
    slot_labels = dict(TIME_SLOTS)

    async with AsyncSessionLocal() as session:
        await q.add_medication(
            session,
            patient_id=data["patient_id"],
            name=data["med_name"],
            dose=data["med_dose"],
            note="",
            time_label=slot_labels.get(slot, slot),
            time_slot=slot,
            start_day=data["start_day"],
            end_day=end_day,
            reminder_hour=rh,
            reminder_minute=rm,
        )

    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Яна дори қўшиш", callback_data=f"add_med:{data['patient_id']}")
    builder.button(text="✅ Тайёр",           callback_data="admin_done")
    builder.adjust(1)
    await message.answer(
        f"✅ <b>{data['med_name']}</b> қўшилди!",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "admin_done")
async def cb_admin_done(callback: CallbackQuery):
    await callback.message.answer("✅ Барча дориlar сақланди!", reply_markup=admin_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_list_patients")
async def cb_list_patients(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Рухсат йўқ", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.db.models import Patient
        result = await session.execute(
            select(Patient).where(Patient.is_active).order_by(Patient.created_at.desc())
        )
        patients = result.scalars().all()

    if not patients:
        await callback.message.answer("Ҳали бемор йўқ.")
        await callback.answer()
        return

    lines = ["👥 <b>Беморлар рўйхати:</b>\n"]
    for p in patients:
        linked = "🔗" if p.telegram_id else "⭕"
        lines.append(f"{linked} <code>{p.patient_code}</code> — {p.full_name}")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()

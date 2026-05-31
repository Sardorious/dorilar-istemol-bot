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
    ("morning", "Bomdod 05:30"),
    ("before_breakfast", "Nonushta oldin 07:00"),
    ("breakfast", "Nonushta vaqtida 07:30"),
    ("afternoon", "Tushlik 13:00"),
    ("before_dinner", "Kechki ovqat oldin 17:00"),
    ("dinner", "Kechki ovqat 19:00"),
    ("evening", "Kechqurun 20:00"),
    ("night", "Uxlash oldin 21:00"),
    ("injection", "Kapelnitsa"),
    ("im", "Mushak ichiga"),
]

REMINDER_TIMES = {
    "morning": (5, 30),
    "before_breakfast": (7, 0),
    "breakfast": (7, 30),
    "afternoon": (13, 0),
    "before_dinner": (17, 0),
    "dinner": (19, 0),
    "evening": (20, 0),
    "night": (21, 0),
    "injection": (9, 0),
    "im": (19, 30),
}


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Ruxsat yo'q.")
        return
    await message.answer("👨‍⚕️ Admin panel:", reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin_add_patient")
async def cb_add_patient(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_patient_code)
    await callback.message.answer(
        "Yangi bemor qo'shish:\n\n"
        "Bemor kodini kiriting (masalan: BEMOR-001):"
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_patient_code)
async def process_admin_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    async with AsyncSessionLocal() as session:
        existing = await q.get_patient_by_code(session, code)
    if existing:
        await message.answer(f"❌ '{code}' kodi allaqachon mavjud. Boshqa kod kiriting:")
        return
    await state.update_data(code=code)
    await state.set_state(AdminStates.waiting_for_patient_name)
    await message.answer("Bemor to'liq ismini kiriting:")


@router.message(AdminStates.waiting_for_patient_name)
async def process_admin_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(AdminStates.waiting_for_start_date)
    await message.answer(
        "Davolanish boshlanish sanasini kiriting (KK.OO.YYYY):\n"
        "Masalan: 01.06.2025\n\n"
        "Bugun uchun 'bugun' yozing."
    )


@router.message(AdminStates.waiting_for_start_date)
async def process_admin_date(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ("bugun", "today"):
        start_date = datetime.now()
    else:
        try:
            start_date = datetime.strptime(text, "%d.%m.%Y")
        except ValueError:
            await message.answer("❌ Noto'g'ri format. KK.OO.YYYY ko'rinishida kiriting:")
            return
    await state.update_data(start_date=start_date)
    await state.set_state(AdminStates.waiting_for_notes)
    await message.answer("Izoh (ixtiyoriy, o'tkazib yuborish uchun '-' yozing):")


@router.message(AdminStates.waiting_for_notes)
async def process_admin_notes(message: Message, state: FSMContext):
    notes = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(notes=notes)
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
    await message.answer(
        f"✅ Bemor yaratildi!\n\n"
        f"Kod: <b>{patient.patient_code}</b>\n"
        f"Ism: {patient.full_name}\n\n"
        f"Endi dorilarni qo'shish uchun /add_med_{patient.id} buyrug'ini yuboring.\n"
        f"Yoki quyidagi ko'rsatmani bajaring:",
        parse_mode="HTML"
    )
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Dori qo'shish", callback_data=f"add_med:{patient.id}")
    builder.button(text="📋 Standart resept yuklash", callback_data=f"load_default:{patient.id}")
    builder.adjust(1)
    await message.answer(
        "Nima qilmoqchisiz?",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith("load_default:"))
async def cb_load_default(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    patient_id = int(callback.data.split(":")[1])
    await callback.answer("Yuklanmoqda...", show_alert=False)

    from app.bot.default_recipe import DEFAULT_MEDS
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

    await callback.message.answer(f"✅ {count} ta dori yuklandi!")


@router.callback_query(F.data.startswith("add_med:"))
async def cb_add_med(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    patient_id = int(callback.data.split(":")[1])
    await state.update_data(patient_id=patient_id)
    await state.set_state(AdminStates.adding_med_name)
    await callback.message.answer("Dori nomini kiriting:")
    await callback.answer()


@router.message(AdminStates.adding_med_name)
async def process_med_name(message: Message, state: FSMContext):
    await state.update_data(med_name=message.text.strip())
    await state.set_state(AdminStates.adding_med_dose)
    await message.answer("Miqdorini kiriting (masalan: 1 ta, 2 kapsul, 5 g):")


@router.message(AdminStates.adding_med_dose)
async def process_med_dose(message: Message, state: FSMContext):
    await state.update_data(med_dose=message.text.strip())
    await state.set_state(AdminStates.adding_med_time_slot)

    builder = InlineKeyboardBuilder()
    for slot, label in TIME_SLOTS:
        builder.button(text=label, callback_data=f"slot:{slot}")
    builder.adjust(2)
    await message.answer("Qaysi vaqtda?", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("slot:"), AdminStates.adding_med_time_slot)
async def process_slot(callback: CallbackQuery, state: FSMContext):
    slot = callback.data.split(":")[1]
    await state.update_data(time_slot=slot)
    await state.set_state(AdminStates.adding_med_start_day)
    await callback.message.answer("Necha-kundan boshlanadi? (masalan: 1):")
    await callback.answer()


@router.message(AdminStates.adding_med_start_day)
async def process_start_day(message: Message, state: FSMContext):
    try:
        start_day = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Raqam kiriting:")
        return
    await state.update_data(start_day=start_day)
    await state.set_state(AdminStates.adding_med_end_day)
    await message.answer("Necha-kungacha? (masalan: 30, yoki 365 — 1 yil):")


@router.message(AdminStates.adding_med_end_day)
async def process_end_day(message: Message, state: FSMContext):
    try:
        end_day = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Raqam kiriting:")
        return

    data = await state.get_data()
    slot = data.get("time_slot", "breakfast")
    rh, rm = REMINDER_TIMES.get(slot, (None, None))

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.db.models import Medication
        slot_labels = dict(TIME_SLOTS)
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
    builder.button(text="➕ Yana dori qo'shish", callback_data=f"add_med:{data['patient_id']}")
    builder.button(text="✅ Tayyor", callback_data="admin_done")
    builder.adjust(1)
    await message.answer(
        f"✅ <b>{data['med_name']}</b> qo'shildi!",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "admin_done")
async def cb_admin_done(callback: CallbackQuery):
    await callback.message.answer("✅ Barcha dorilar saqlandi!", reply_markup=admin_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_list_patients")
async def cb_list_patients(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.db.models import Patient
        result = await session.execute(
            select(Patient).where(Patient.is_active == True).order_by(Patient.created_at.desc())
        )
        patients = result.scalars().all()

    if not patients:
        await callback.message.answer("Hali bemor yo'q.")
        await callback.answer()
        return

    lines = ["👥 <b>Bemorlar ro'yxati:</b>\n"]
    for p in patients:
        linked = "🔗" if p.telegram_id else "⭕"
        lines.append(f"{linked} <code>{p.patient_code}</code> — {p.full_name}")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()

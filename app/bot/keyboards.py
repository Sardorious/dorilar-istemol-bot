from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def dose_keyboard(dose_log_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Iste'mol qildim", callback_data=f"taken:{dose_log_id}")
    builder.button(text="⏰ Keyinroq", callback_data=f"snooze_menu:{dose_log_id}")
    builder.button(text="❌ O'tkazib yuborish", callback_data=f"skip:{dose_log_id}")
    builder.adjust(1)
    return builder.as_markup()


def snooze_keyboard(dose_log_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    snooze_options = [
        ("5 daqiqa", 5),
        ("10 daqiqa", 10),
        ("15 daqiqa", 15),
        ("30 daqiqa", 30),
        ("1 soat", 60),
        ("2 soat", 120),
    ]
    for label, minutes in snooze_options:
        builder.button(text=label, callback_data=f"snooze:{dose_log_id}:{minutes}")
    builder.button(text="◀️ Orqaga", callback_data=f"back_to_dose:{dose_log_id}")
    builder.adjust(3, 3, 1)
    return builder.as_markup()


def calendar_keyboard(treatment_days: int, current_day: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for day in range(1, treatment_days + 1):
        builder.button(
            text=f"{'📍' if day == current_day else ''}{day}",
            callback_data=f"day:{day}"
        )
    builder.adjust(7)
    return builder.as_markup()


def day_meds_keyboard(meds_with_logs: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for med, log in meds_with_logs:
        status_icon = {"taken": "✅", "skipped": "❌", "snoozed": "⏰", "pending": "💊"}.get(
            log.status if log else "pending", "💊"
        )
        builder.button(
            text=f"{status_icon} {med.name[:25]}",
            callback_data=f"med_detail:{med.id}:{log.id if log else 0}"
        )
    builder.button(text="📋 Tarix", callback_data="history")
    builder.button(text="🗓 Kalendar", callback_data="show_calendar")
    builder.adjust(1)
    return builder.as_markup()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗓 Bugungi dorilar", callback_data="today")
    builder.button(text="📅 Kalendar", callback_data="show_calendar")
    builder.button(text="📋 Tarix", callback_data="history")
    builder.adjust(1)
    return builder.as_markup()


def admin_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Yangi bemor qo'shish", callback_data="admin_add_patient")
    builder.button(text="📋 Bemorlar ro'yxati", callback_data="admin_list_patients")
    builder.adjust(1)
    return builder.as_markup()

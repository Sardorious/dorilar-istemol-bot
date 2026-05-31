from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def dose_keyboard(dose_log_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Истеъмол қилдим", callback_data=f"taken:{dose_log_id}")
    builder.button(text="⏰ Кейинроқ",        callback_data=f"snooze_menu:{dose_log_id}")
    builder.button(text="❌ Ўтказиб юбориш",  callback_data=f"skip:{dose_log_id}")
    builder.adjust(1)
    return builder.as_markup()


def snooze_keyboard(dose_log_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, minutes in [("5 дақиқа", 5), ("10 дақиқа", 10), ("15 дақиқа", 15),
                            ("30 дақиқа", 30), ("1 соат", 60), ("2 соат", 120)]:
        builder.button(text=label, callback_data=f"snooze:{dose_log_id}:{minutes}")
    builder.button(text="◀️ Орқага", callback_data=f"back_to_dose:{dose_log_id}")
    builder.adjust(3, 3, 1)
    return builder.as_markup()


def calendar_keyboard(treatment_days: int, current_day: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for day in range(1, treatment_days + 1):
        label = f"📍{day}" if day == current_day else str(day)
        builder.button(text=label, callback_data=f"day:{day}")
    builder.adjust(7)
    return builder.as_markup()


def day_meds_keyboard(meds_with_logs: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for med, log in meds_with_logs:
        icon = {"taken": "✅", "skipped": "❌", "snoozed": "⏰", "pending": "💊"}.get(
            log.status if log else "pending", "💊"
        )
        builder.button(
            text=f"{icon} {med.name[:28]}",
            callback_data=f"med_detail:{med.id}:{log.id if log else 0}"
        )
    builder.button(text="📋 Тарих",    callback_data="history")
    builder.button(text="🗓 Календар", callback_data="show_calendar")
    builder.adjust(1)
    return builder.as_markup()


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="🗓 Бугунги дорилар")
    builder.button(text="📅 Календар")
    builder.button(text="📋 Тарих")
    builder.button(text="🛒 Харид рўйхати")
    builder.button(text="📂 Рецептларим")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def patients_list_keyboard(patients: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in patients:
        name = p.full_name or "Номсиз рецепт"
        date_str = p.created_at.strftime("%d.%m.%Y") if p.created_at else ""
        label = f"{'✅ ' if p.is_active else ''}{name} ({date_str})"
        builder.button(text=label[:40], callback_data=f"switch_patient:{p.id}")
    builder.adjust(1)
    return builder.as_markup()

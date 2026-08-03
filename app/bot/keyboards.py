from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def dose_keyboard(dose_log_id: int, status: str = "pending") -> InlineKeyboardMarkup:
    """Doza tugmalari.

    Holat allaqachon belgilangan bo'lsa ham tugmalar ko'rsatiladi —
    foydalanuvchi xato bosgan bo'lsa yoki o'tgan kunni to'ldirayotgan
    bo'lsa belgini o'zgartira olishi kerak.
    """
    builder = InlineKeyboardBuilder()

    if status != "taken":
        builder.button(text="✅ Истеъмол қилдим", callback_data=f"taken:{dose_log_id}")
    if status in ("pending", "snoozed"):
        builder.button(text="⏰ Кейинроқ", callback_data=f"snooze_menu:{dose_log_id}")
    if status != "skipped":
        builder.button(text="❌ Ўтказиб юбориш", callback_data=f"skip:{dose_log_id}")
    if status in ("taken", "skipped"):
        builder.button(text="↩️ Белгини олиб ташлаш", callback_data=f"unmark:{dose_log_id}")

    builder.adjust(1)
    return builder.as_markup()


def start_date_keyboard(prefix: str = "setdate") -> InlineKeyboardMarkup:
    """Davolanish qaysi kundan boshlanganini so'rash."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Бугундан",       callback_data=f"{prefix}:0")
    builder.button(text="📅 Кечадан",        callback_data=f"{prefix}:1")
    builder.button(text="📅 2 кун олдин",    callback_data=f"{prefix}:2")
    builder.button(text="📅 3 кун олдин",    callback_data=f"{prefix}:3")
    builder.button(text="✏️ Бошқа сана киритаман", callback_data=f"{prefix}:manual")
    builder.adjust(2, 2, 1)
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


BTN_TODAY = "🗓 Бугунги дорилар"
BTN_CALENDAR = "📅 Календар"
BTN_HISTORY = "📋 Тарих"
BTN_SHOPPING = "🛒 Харид рўйхати"
BTN_PATIENTS = "📂 Рецептларим"

# Sana kiritish holatida bu matnlar sana deb o'qilmasligi kerak
MENU_BUTTONS = (
    BTN_TODAY,
    BTN_CALENDAR,
    BTN_HISTORY,
    BTN_SHOPPING,
    BTN_PATIENTS,
)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    for text in MENU_BUTTONS:
        builder.button(text=text)
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def patients_list_keyboard(patients: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in patients:
        name = p.full_name or "Номсиз рецепт"
        date_str = p.created_at.strftime("%d.%m.%Y") if p.created_at else ""
        label = f"{'✅ ' if p.is_active else ''}{name} ({date_str})"
        builder.button(text=label[:40], callback_data=f"switch_patient:{p.id}")
    builder.button(
        text="📅 Бошланиш кунини ўзгартириш",
        callback_data="edit_start_date",
    )
    builder.adjust(1)
    return builder.as_markup()

import re
from datetime import date, datetime

from app import tz
from app.db.models import Patient

# Ajratuvchi belgilar: nuqta, chiziqcha, slesh, probel
_SEPARATORS = re.compile(r"[\s/.\-]+")

# Bundan eski sana kiritilsa xato deb hisoblanadi
MAX_PAST_DAYS = 365


def parse_user_date(text: str) -> date | None:
    """Foydalanuvchi yozgan sanani o'qiydi. Noto'g'ri bo'lsa None.

    '25.07.2026', '25/07/2026', '25-07-2026', '25 07 2026', '25.07.26'.

    DIQQAT: strptime('%Y') 2 xonali yilni ҳам қабул қилади va '26' ni
    26-yil deb o'qiydi. Shuning uchun yil qismi qo'lda tekshiriladi.
    """
    parts = [p for p in _SEPARATORS.split(text.strip()) if p]
    if len(parts) != 3:
        return None

    day, month, year = parts
    if not (day.isdigit() and month.isdigit() and year.isdigit()):
        return None

    if len(year) == 2:
        year = f"20{year}"
    elif len(year) != 4:
        return None

    try:
        # Naive parse ataylab: bu yerda faqat kalendar sanasi kerak,
        # zona esa tz.at() da qo'shiladi.
        return datetime.strptime(f"{day}.{month}.{year}", "%d.%m.%Y").date()
    except ValueError:
        return None


def validate_start_date(value: date) -> str | None:
    """Boshlanish sanasi mantiqiymi? Xato bo'lsa sabab matnini qaytaradi."""
    today = tz.today()
    if value > today:
        return "❌ Келажакдаги сана бўлмайди. Даволаниш қачон бошланганини киритинг."
    if (today - value).days > MAX_PAST_DAYS:
        return f"❌ Сана жуда эски ({MAX_PAST_DAYS} кундан ортиқ). Текшириб қайта киритинг."
    return None


def get_treatment_day(patient: Patient) -> int:
    """Davolanishning nechanchi kuni — Toshkent sanasi bo'yicha."""
    start = tz.to_local_date(patient.start_date)
    delta = (tz.today() - start).days + 1
    return max(1, delta)


def format_time_slot(slot: str) -> str:
    slots = {
        "morning":          "🌅 Бомдод вақтида (05:30)",
        "before_breakfast": "🕖 Нонушта олдин (07:00–07:30)",
        "breakfast":        "🍽 Нонушта вақтида (07:30–08:00)",
        "afternoon":        "☀️ Тушлик вақтида (13:00)",
        "before_dinner":    "🕔 Кечки овқат олдин (17:00–18:00)",
        "dinner":           "🍲 Кечки овқат вақтида (19:00)",
        "evening":          "🌙 Кечқурун овқатдан кейин (20:00)",
        "night":            "😴 Ухлаш олдин (21:00+)",
        "injection":        "💉 Капельница (кун 1-ярмида, тук қоринга)",
        "im":               "💉 Мушак ичига (кечқурун)",
    }
    return slots.get(slot, slot)


def format_status(status: str) -> str:
    return {
        "taken":   "✅ Истеъмол қилинди",
        "skipped": "❌ Ўтказиб юборилди",
        "snoozed": "⏰ Кейинга қолдирилди",
        "pending": "💊 Кутилмоқда",
    }.get(status, status)


def build_day_summary(day: int, meds_with_logs: list) -> str:
    if not meds_with_logs:
        return f"📅 <b>{day}-кун</b>\n\nБу кунда дори йўқ."

    taken = sum(1 for _, log_item in meds_with_logs if log_item and log_item.status == "taken")
    total = len(meds_with_logs)

    lines = [f"📅 <b>{day}-кун — Дорилар рўйхати</b>\n"]
    lines.append(f"✅ {taken}/{total} истеъмол қилинди\n")

    current_slot = None
    for med, log in meds_with_logs:
        if med.time_slot != current_slot:
            current_slot = med.time_slot
            lines.append(f"\n<b>{format_time_slot(current_slot)}</b>")

        status_icon = {"taken": "✅", "skipped": "❌", "snoozed": "⏰", "pending": "💊"}.get(
            log.status if log else "pending", "💊"
        )
        lines.append(f"{status_icon} {med.name} — {med.dose}")
        if med.note:
            lines.append(f"   <i>{med.note[:100]}</i>")

    return "\n".join(lines)

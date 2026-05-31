from datetime import date
from app.db.models import Patient


def get_treatment_day(patient: Patient) -> int:
    start = patient.start_date.date() if hasattr(patient.start_date, 'date') else patient.start_date
    today = date.today()
    delta = (today - start).days + 1
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

    lines = [f"📅 <b>{day}-кун — Дориlar рўйхати</b>\n"]
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

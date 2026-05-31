from datetime import datetime, date
from app.db.models import Patient


def get_treatment_day(patient: Patient) -> int:
    start = patient.start_date.date() if hasattr(patient.start_date, 'date') else patient.start_date
    today = date.today()
    delta = (today - start).days + 1
    return max(1, delta)


def format_time_slot(slot: str) -> str:
    slots = {
        "morning": "🌅 Bomdod (05:30–07:00)",
        "before_breakfast": "🕖 Nonushta oldin (07:00–07:30)",
        "breakfast": "🍽 Nonushta vaqtida (07:30–08:00)",
        "afternoon": "☀️ Tushlik (13:00)",
        "before_dinner": "🕔 Kechki ovqat oldin (17:00–18:00)",
        "dinner": "🍲 Kechki ovqat (19:00)",
        "evening": "🌙 Kechqurun (20:00)",
        "night": "😴 Uxlash oldin (21:00+)",
        "injection": "💉 Kapelnitsa (kun 1-yarmi)",
        "im": "💉 Mushak ichiga (kechqurun)",
    }
    return slots.get(slot, slot)


def format_status(status: str) -> str:
    return {
        "taken": "✅ Iste'mol qilindi",
        "skipped": "❌ O'tkazib yuborildi",
        "snoozed": "⏰ Keyinga qoldirildi",
        "pending": "💊 Kutilmoqda",
    }.get(status, status)


def build_day_summary(day: int, meds_with_logs: list) -> str:
    if not meds_with_logs:
        return f"📅 <b>{day}-kun</b>\n\nBu kunda dori yo'q."

    taken = sum(1 for _, l in meds_with_logs if l and l.status == "taken")
    total = len(meds_with_logs)

    lines = [f"📅 <b>{day}-kun — Dorilar ro'yxati</b>\n"]
    lines.append(f"✅ {taken}/{total} iste'mol qilindi\n")

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
            lines.append(f"   <i>{med.note[:80]}</i>")

    return "\n".join(lines)

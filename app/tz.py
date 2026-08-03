"""Yagona vaqt manbai.

Loyihada vaqt FAQAT shu modul orqali olinadi.
Barcha datetime — timezone-aware (Asia/Tashkent).
"""
from datetime import datetime, date, time as dt_time
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import settings

# Zona nomi (matn). APScheduler 3.x FAQAT pytz zonalarini qabul qiladi,
# shuning uchun scheduler/trigger larga ZoneInfo emas, shu MATN uzatiladi —
# APScheduler uni o'zi pytz orqali ochadi.
TZ_NAME = settings.TZ

# O'z datetime hisob-kitoblarimiz uchun ZoneInfo. pytz dan farqli o'laroq
# datetime.combine(..., tzinfo=...) va replace(tzinfo=...) to'g'ri ishlaydi.
TZ = ZoneInfo(TZ_NAME)


def now() -> datetime:
    """Hozirgi vaqt — tz-aware, Asia/Tashkent."""
    return datetime.now(TZ)


def today() -> date:
    """Bugungi sana — Toshkent bo'yicha (server UTC bo'lsa ham to'g'ri)."""
    return now().date()


def make_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Naive datetime ni Toshkent zonasiga bog'laydi.

    DB dagi eski (naive) yozuvlar bilan ishlash uchun kerak.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def to_local_date(value) -> date:
    """datetime yoki date dan Toshkent bo'yicha sanani qaytaradi."""
    if isinstance(value, datetime):
        return make_aware(value).date()
    return value


def at(day: date, hour: int, minute: int = 0) -> datetime:
    """Berilgan kunning berilgan soatini tz-aware datetime qilib qaytaradi."""
    return datetime.combine(day, dt_time(hour=hour, minute=minute), tzinfo=TZ)

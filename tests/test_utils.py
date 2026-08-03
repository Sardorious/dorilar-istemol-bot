from datetime import datetime, timedelta, timezone

import pytest

from app import tz
from app.bot.utils import get_treatment_day, format_time_slot, format_status
from app.db.models import Patient
from app.db.queries import REMINDER_MAP, DEFAULT_SLOT, resolve_reminder_time


def make_patient(days_ago: int, aware: bool = True) -> Patient:
    p = Patient()
    start = tz.now() - timedelta(days=days_ago)
    p.start_date = start if aware else start.replace(tzinfo=None)
    return p


# ── Davolanish kuni ───────────────────────────────────────────────────────────

def test_treatment_day_first_day():
    assert get_treatment_day(make_patient(0)) == 1


def test_treatment_day_10():
    assert get_treatment_day(make_patient(9)) == 10


def test_treatment_day_handles_naive_legacy_rows():
    """DB dagi eski naive yozuvlar ham to'g'ri o'qilishi kerak."""
    assert get_treatment_day(make_patient(9, aware=False)) == 10


def test_treatment_day_never_below_one():
    p = Patient()
    p.start_date = tz.now() + timedelta(days=5)
    assert get_treatment_day(p) == 1


def test_treatment_day_uses_tashkent_date_not_utc_date():
    """Regressiya: kun raqami Toshkent sanasi bo'yicha hisoblanishi kerak.

    Toshkentda 03:00 — UTC bo'yicha hali KECHA (22:00). Ilgari kod
    date.today()/utcnow ishlatgani uchun UTC serverda kun raqami
    1 taga adashardi.
    """
    start_local = tz.at(tz.today(), 3, 0)
    # Shart haqiqatan ham UTC sanasi boshqa ekanini tasdiqlaydi
    assert start_local.astimezone(timezone.utc).date() < start_local.date()

    p = Patient()
    p.start_date = start_local
    assert tz.to_local_date(start_local) == tz.today()
    assert get_treatment_day(p) == 1


# ── tz moduli ─────────────────────────────────────────────────────────────────

def test_now_is_aware():
    assert tz.now().tzinfo is not None


def test_at_builds_aware_datetime():
    dt = tz.at(tz.today(), 7, 30)
    assert dt.tzinfo is not None
    assert (dt.hour, dt.minute) == (7, 30)


def test_at_utc_offset_is_plus_five():
    """Toshkent UTC+5 — eslatma soati aynan shu ofsetda otilishi kerak."""
    dt = tz.at(tz.today(), 7, 30)
    assert dt.utcoffset() == timedelta(hours=5)
    assert dt.astimezone(timezone.utc).hour == 2  # 07:30 Toshkent = 02:30 UTC


def test_make_aware_on_naive():
    naive = datetime(2026, 8, 3, 7, 30)
    assert tz.make_aware(naive).utcoffset() == timedelta(hours=5)


def test_make_aware_none():
    assert tz.make_aware(None) is None


def test_make_aware_keeps_instant_for_utc_input():
    utc_dt = datetime(2026, 8, 3, 2, 30, tzinfo=timezone.utc)
    local = tz.make_aware(utc_dt)
    assert local.hour == 7 and local.minute == 30


# ── time_slot -> eslatma vaqti ────────────────────────────────────────────────

@pytest.mark.parametrize("slot", list(REMINDER_MAP))
def test_every_known_slot_resolves(slot):
    hour, minute = resolve_reminder_time(slot)
    assert 0 <= hour <= 23
    assert 0 <= minute <= 59


def test_unknown_slot_falls_back_instead_of_none():
    """Ilgari noma'lum slot (None, None) qaytarardi va dori jimgina
    eslatmasiz qolib ketardi."""
    assert resolve_reminder_time("qandaydir_notogri_slot") == REMINDER_MAP[DEFAULT_SLOT]


def test_slots_match_format_time_slot_labels():
    for slot in REMINDER_MAP:
        assert format_time_slot(slot) != slot, f"'{slot}' uchun matn yo'q"


# ── Formatlash ────────────────────────────────────────────────────────────────

def test_format_time_slot_known():
    assert "Бомдод" in format_time_slot("morning")
    assert "Нонушта" in format_time_slot("breakfast")


def test_format_time_slot_unknown():
    assert format_time_slot("unknown_slot") == "unknown_slot"


def test_format_status():
    assert "✅" in format_status("taken")
    assert "❌" in format_status("skipped")
    assert "⏰" in format_status("snoozed")
    assert "💊" in format_status("pending")

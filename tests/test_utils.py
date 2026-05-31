import pytest
from app.bot.utils import get_treatment_day, format_time_slot, format_status
from app.db.models import Patient
from datetime import datetime, timedelta


def make_patient(days_ago: int) -> Patient:
    p = Patient()
    p.start_date = datetime.now() - timedelta(days=days_ago)
    return p


def test_treatment_day_first_day():
    p = make_patient(0)
    assert get_treatment_day(p) == 1


def test_treatment_day_10():
    p = make_patient(9)
    assert get_treatment_day(p) == 10


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

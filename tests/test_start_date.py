"""Boshlanish sanasi va doza belgilash tugmalari uchun testlar."""
from datetime import timedelta

import pytest

from app import tz
from app.bot.keyboards import MENU_BUTTONS, dose_keyboard, start_date_keyboard
from app.bot.utils import MAX_PAST_DAYS, parse_user_date, validate_start_date


def _buttons(markup):
    """Klaviaturadagi barcha callback_data larni ro'yxat qilib qaytaradi."""
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


# ── Sana o'qish ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text",
    [
        "25.07.2026",
        "25/07/2026",
        "25-07-2026",
        "25 07 2026",
        "  25.07.2026  ",
        "25.07.26",
    ],
)
def test_parse_user_date_accepts_common_formats(text):
    parsed = parse_user_date(text)
    assert parsed is not None
    assert (parsed.day, parsed.month, parsed.year) == (25, 7, 2026)


def test_two_digit_year_is_not_year_26():
    """Regressiya: strptime('%Y') '26' ни 26-йил деб ўқийди.

    Yil qismi qo'lda tekshirilmasa, foydalanuvchi '25.07.26' yozganda
    sana milodiy 26-yilga tushib, "juda eski" xatosi chiqardi.
    """
    parsed = parse_user_date("25.07.26")
    assert parsed.year == 2026


@pytest.mark.parametrize(
    "text",
    [
        "",
        "bugun",
        "32.07.2026",
        "25.13.2026",
        "2026-07-25",
        "salom",
        "1234",
        "25.07",
        "25.07.202",
        "25.iyul.2026",
    ],
)
def test_parse_user_date_rejects_garbage(text):
    assert parse_user_date(text) is None


# ── Sana tekshiruvi ───────────────────────────────────────────────────────────

def test_today_is_valid():
    assert validate_start_date(tz.today()) is None


def test_past_date_is_valid():
    assert validate_start_date(tz.today() - timedelta(days=10)) is None


def test_future_date_is_rejected():
    error = validate_start_date(tz.today() + timedelta(days=1))
    assert error is not None
    assert "Келажак" in error


def test_too_old_date_is_rejected():
    error = validate_start_date(tz.today() - timedelta(days=MAX_PAST_DAYS + 1))
    assert error is not None


def test_boundary_date_is_valid():
    assert validate_start_date(tz.today() - timedelta(days=MAX_PAST_DAYS)) is None


# ── Sana tanlash klaviaturasi ─────────────────────────────────────────────────

def test_start_date_keyboard_has_manual_option():
    assert "setdate:manual" in _buttons(start_date_keyboard())


def test_start_date_keyboard_offsets_are_days_back():
    data = _buttons(start_date_keyboard())
    assert "setdate:0" in data  # bugun
    assert "setdate:1" in data  # kecha


def test_start_date_keyboard_prefix_is_configurable():
    """Tahrirlash oqimi boshqa prefiks ishlatadi — callbacklar aralashmasin."""
    data = _buttons(start_date_keyboard(prefix="newdate"))
    assert all(d.startswith("newdate:") for d in data)


# ── Doza tugmalari: har qanday holatni o'zgartirish ───────────────────────────

def test_pending_dose_offers_all_actions():
    data = _buttons(dose_keyboard(7))
    assert data == ["taken:7", "snooze_menu:7", "skip:7"]


def test_taken_dose_can_be_changed():
    """Regressiya: ilgari belgilangan doza uchun tugma umuman chiqmasdi."""
    data = _buttons(dose_keyboard(7, "taken"))
    assert "unmark:7" in data
    assert "skip:7" in data
    assert "taken:7" not in data  # allaqachon shu holatda


def test_skipped_dose_can_be_changed():
    data = _buttons(dose_keyboard(7, "skipped"))
    assert "unmark:7" in data
    assert "taken:7" in data
    assert "skip:7" not in data


def test_snooze_only_offered_while_actionable():
    assert "snooze_menu:7" in _buttons(dose_keyboard(7, "snoozed"))
    assert "snooze_menu:7" not in _buttons(dose_keyboard(7, "taken"))


def test_every_status_leaves_at_least_one_action():
    for status in ("pending", "snoozed", "taken", "skipped"):
        assert _buttons(dose_keyboard(1, status)), f"'{status}' uchun тугма йўқ"


# ── Menyu tugmalari ───────────────────────────────────────────────────────────

def test_menu_buttons_are_not_parsable_as_dates():
    """Menyu tugmasi sana deb o'qilib qolmasligi kerak."""
    for text in MENU_BUTTONS:
        assert parse_user_date(text) is None

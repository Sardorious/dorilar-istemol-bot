"""Eslatma rejalashtirish mantiqi uchun regressiya testlari.

Bu yerda tekshiriladigan asosiy nosozliklar:
  1. naive datetime + UTC server -> 5 soatlik siljish
  2. o'tib ketgan vaqtga job qo'yish -> restartda "portlash"
  3. eski/almashtirilgan retsept joblari o'chmasligi
"""
from datetime import timedelta, timezone

import pytest

from app import tz
from app.scheduler.jobs import scheduler, schedule_reminder
from app.scheduler.daily import DAILY_JOB_PREFIX, _purge_daily_jobs


@pytest.fixture(autouse=True)
def clean_scheduler():
    scheduler.remove_all_jobs()
    yield
    scheduler.remove_all_jobs()


def _add(job_id: str, run_at):
    return schedule_reminder(
        bot=None,
        telegram_id=1,
        dose_log_id=1,
        med_name="Test",
        dose="1 ta",
        run_at=run_at,
        job_id=job_id,
    )


# ── 1. Vaqt zonasi ────────────────────────────────────────────────────────────

def test_scheduler_timezone_is_tashkent():
    assert str(scheduler.timezone) == "Asia/Tashkent"


def test_scheduler_timezone_is_pytz_compatible():
    """APScheduler 3.x ZoneInfo ni qabul qilmaydi ('Only timezones from the
    pytz library are supported'). Scheduler qurila olganining o'zi shuni
    tasdiqlaydi, lekin ochiq tekshirib qo'yamiz."""
    assert hasattr(scheduler.timezone, "localize")


def test_job_fires_at_tashkent_wall_clock():
    """07:30 dori aynan 07:30 Toshkentda = 02:30 UTC da otilishi kerak."""
    run_at = tz.at(tz.today() + timedelta(days=1), 7, 30)
    assert _add(f"{DAILY_JOB_PREFIX}tz_check", run_at) is True

    job = scheduler.get_job(f"{DAILY_JOB_PREFIX}tz_check")
    fire_at = job.trigger.run_date
    assert fire_at.astimezone(tz.TZ).hour == 7
    assert fire_at.astimezone(tz.TZ).minute == 30
    assert fire_at.astimezone(timezone.utc).hour == 2


# ── 2. O'tib ketgan vaqt ──────────────────────────────────────────────────────

def test_past_time_is_not_scheduled():
    """Restartda o'tib ketgan eslatmalar qayta otilmasligi kerak."""
    past = tz.now() - timedelta(hours=3)
    assert _add(f"{DAILY_JOB_PREFIX}past", past) is False
    assert scheduler.get_job(f"{DAILY_JOB_PREFIX}past") is None


def test_future_time_is_scheduled():
    future = tz.now() + timedelta(hours=3)
    assert _add(f"{DAILY_JOB_PREFIX}future", future) is True
    assert scheduler.get_job(f"{DAILY_JOB_PREFIX}future") is not None


def test_naive_run_at_is_treated_as_tashkent():
    """Naive datetime kelib qolsa ham UTC deb emas, Toshkent deb o'qiladi."""
    naive = (tz.now() + timedelta(hours=2)).replace(tzinfo=None)
    assert _add(f"{DAILY_JOB_PREFIX}naive", naive) is True
    job = scheduler.get_job(f"{DAILY_JOB_PREFIX}naive")
    assert job.trigger.run_date.utcoffset() == timedelta(hours=5)


# ── 3. Eski joblarni tozalash ─────────────────────────────────────────────────

def test_purge_removes_dose_jobs():
    _add(f"{DAILY_JOB_PREFIX}1_1_x", tz.now() + timedelta(hours=1))
    _add(f"{DAILY_JOB_PREFIX}2_2_x", tz.now() + timedelta(hours=2))
    _purge_daily_jobs()
    assert scheduler.get_jobs() == []


def test_purge_keeps_snooze_jobs():
    """Foydalanuvchi o'zi so'ragan snooze o'chib ketmasligi kerak."""
    _add("snooze_5_123", tz.now() + timedelta(minutes=30))
    _add(f"{DAILY_JOB_PREFIX}1_1_x", tz.now() + timedelta(hours=1))
    _purge_daily_jobs()
    remaining = [j.id for j in scheduler.get_jobs()]
    assert remaining == ["snooze_5_123"]


def test_purge_keeps_the_cron_job():
    """Regressiya: cron job id si 'dose_' bilan boshlanmasligi shart,
    aks holda tozalash uni ham o'chirib, bot butunlay eslatmay qoladi."""
    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        lambda: None,
        trigger=CronTrigger(hour=0, minute=5, timezone=tz.TZ_NAME),
        id="cron_daily_scheduler",
    )
    _add(f"{DAILY_JOB_PREFIX}1_1_x", tz.now() + timedelta(hours=1))
    _purge_daily_jobs()
    assert [j.id for j in scheduler.get_jobs()] == ["cron_daily_scheduler"]

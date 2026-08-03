"""Test muhiti.

app.config.Settings import paytida yaratiladi va BOT_TOKEN / ANTHROPIC_API_KEY
ni talab qiladi. Testlarda haqiqiy kalitlar kerak emas — shu yerda
soxta qiymatlar o'rnatiladi (app paketi import qilinishidan OLDIN).
"""
import os

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TZ", "Asia/Tashkent")

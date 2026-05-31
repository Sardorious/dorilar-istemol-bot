# Dorilar Iste'mol Bot 💊

Telegram bot — bemorlar o'z dori jadvalini ko'radi va eslatmalar oladi.

## Arxitektura

```
app/
├── main.py              # Bot ishga tushirish
├── config.py            # Settings (env vars)
├── bot/
│   ├── handlers.py      # Bemor handlerlari
│   ├── admin.py         # Admin panel
│   ├── keyboards.py     # Inline tugmalar
│   ├── states.py        # FSM states
│   ├── utils.py         # Yordamchi funksiyalar
│   └── default_recipe.py # Standart resept
├── db/
│   ├── models.py        # SQLAlchemy modellari
│   ├── engine.py        # DB ulanish
│   └── queries.py       # DB so'rovlar
└── scheduler/
    ├── jobs.py          # APScheduler eslatmalar
    └── daily.py         # Kunlik eslatma rejalashtirish
```

## Ishga tushirish (local)

```bash
cp .env.example .env
# .env ni to'ldiring

docker compose up -d
```

## VPS ga o'rnatish

```bash
# 1. VPS da bir marta:
bash scripts/setup_vps.sh

# 2. .env ni to'ldiring:
nano /opt/dorilar-bot/.env

# 3. Ishga tushiring:
cd /opt/dorilar-bot && docker compose up -d
```

## GitHub Secrets (CI/CD uchun)

| Secret | Tavsif |
|--------|--------|
| `VPS_HOST` | VPS IP manzili |
| `VPS_USER` | SSH foydalanuvchi (odatda `root`) |
| `VPS_SSH_KEY` | SSH private key |
| `VPS_PORT` | SSH port (odatda `22`) |
| `BOT_TOKEN` | Telegram bot token (@BotFather dan) |
| `ADMIN_IDS` | Admin Telegram IDlari (vergul bilan) |

## Bot buyruqlari

- `/start` — Ro'yxatdan o'tish yoki asosiy menyu
- `/menu` — Asosiy menyu
- `/admin` — Admin panel (faqat adminlar)

## Admin panel imkoniyatlari

- Yangi bemor qo'shish (kod, ism, boshlanish sanasi)
- Standart resept yuklash (1 tugma bilan)
- Dorilarni qo'lda qo'shish
- Bemorlar ro'yxatini ko'rish

## Bemor funksiyalari

- Bemor ID orqali ulash
- Kunlik kalendar (150 kun)
- Har kun dorilar ro'yxati vaqt bo'yicha
- Iste'mol qilindi / Keyinroq / O'tkazib yuborish
- Snooze: 5, 10, 15, 30 daqiqa, 1, 2 soat
- Iste'mol tarixi

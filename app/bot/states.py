"""FSM holatlari."""
from aiogram.fsm.state import State, StatesGroup


class PrescriptionSetup(StatesGroup):
    """Retsept yuklangandan keyin boshlanish kunini so'rash."""

    # Yangi retsept: PDF o'qildi, endi boshlanish kuni kutilmoqda
    waiting_for_start_date = State()

    # Mavjud retseptning boshlanish kunini tahrirlash
    waiting_for_new_start_date = State()

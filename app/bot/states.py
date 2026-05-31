from aiogram.fsm.state import State, StatesGroup


class AuthStates(StatesGroup):
    waiting_for_code = State()


class AdminStates(StatesGroup):
    waiting_for_patient_code = State()
    waiting_for_patient_name = State()
    waiting_for_start_date = State()
    waiting_for_notes = State()
    adding_med_name = State()
    adding_med_dose = State()
    adding_med_time_slot = State()
    adding_med_start_day = State()
    adding_med_end_day = State()
    adding_med_reminder_time = State()

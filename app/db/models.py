from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from app import tz


class Base(DeclarativeBase):
    pass


# DIQQAT: SQLite DateTime ustuni tz offset ni saqlamaydi — yozuvlar
# Toshkent devor-soati bo'yicha naive holda tushadi. Shuning uchun
# o'qishda HAR DOIM tz.make_aware(...) orqali qaytadan bog'lanadi.


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(200), nullable=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    start_date = Column(DateTime, nullable=False, default=tz.now)
    diagnosis = Column(Text, nullable=True)
    diet_note = Column(Text, nullable=True)
    daily_notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=tz.now)

    medications = relationship("Medication", back_populates="patient", cascade="all, delete-orphan")
    dose_logs = relationship("DoseLog", back_populates="patient", cascade="all, delete-orphan")


class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    name = Column(String(500), nullable=False)
    dose = Column(String(500), nullable=False)
    note = Column(Text, nullable=True)
    time_label = Column(String(200), nullable=False)
    time_slot = Column(String(50), nullable=False)
    start_day = Column(Integer, nullable=False, default=1)
    end_day = Column(Integer, nullable=False, default=30)
    reminder_hour = Column(Integer, nullable=True)
    reminder_minute = Column(Integer, nullable=True)

    patient = relationship("Patient", back_populates="medications")
    dose_logs = relationship("DoseLog", back_populates="medication", cascade="all, delete-orphan")


class DoseLog(Base):
    __tablename__ = "dose_logs"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    medication_id = Column(Integer, ForeignKey("medications.id"), nullable=False)
    treatment_day = Column(Integer, nullable=False)
    scheduled_time = Column(DateTime, nullable=True)
    taken_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    snooze_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=tz.now)

    patient = relationship("Patient", back_populates="dose_logs")
    medication = relationship("Medication", back_populates="dose_logs")

    __table_args__ = (
        # Bitta dori + bitta kun uchun faqat bitta yozuv bo'lsin
        UniqueConstraint(
            "patient_id", "medication_id", "treatment_day",
            name="uq_dose_log_patient_med_day",
        ),
        Index("ix_dose_logs_patient_day", "patient_id", "treatment_day"),
    )

from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean,
    DateTime, ForeignKey, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(200), nullable=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    start_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    diagnosis = Column(Text, nullable=True)
    diet_note = Column(Text, nullable=True)
    daily_notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="dose_logs")
    medication = relationship("Medication", back_populates="dose_logs")

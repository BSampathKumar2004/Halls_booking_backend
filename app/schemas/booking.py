from pydantic import BaseModel
from datetime import date, time

from app.models.enums import BookingStatus, PaymentStatus, PaymentMode


# ==================================================
# BASE (COMMON FIELDS)
# ==================================================
class BookingBase(BaseModel):
    hall_id: int
    start_date: date
    end_date: date
    start_time: time
    end_time: time


# ==================================================
# CREATE BOOKING (INPUT)
# ==================================================
class BookingCreate(BookingBase):
    payment_mode: PaymentMode = PaymentMode.VENUE
    # 👆 only "online" or "venue" allowed


# ==================================================
# BOOKING RESPONSE (OUTPUT)
# ==================================================
class BookingOut(BookingBase):
    id: int

    status: BookingStatus                # 🔒 ENUM
    payment_mode: PaymentMode            # 🔒 ENUM
    payment_status: PaymentStatus        # 🔒 ENUM

    total_price: float

    booked_by_name: str
    booked_by_email: str

    model_config = {"from_attributes": True}

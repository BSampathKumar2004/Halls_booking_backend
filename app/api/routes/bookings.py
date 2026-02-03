from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, date

from app.db.session import SessionLocal
from app.models.booking import Booking
from app.models.hall import Hall
from app.schemas.booking import BookingCreate, BookingOut
from app.utils.razorpay_client import razorpay_client
from app.core.logging_config import get_logger
from app.core.dependencies import get_current_principal

router = APIRouter(prefix="/bookings", tags=["Bookings"])
logger = get_logger()


# ---------------------------------------------------------------------
# DB SESSION
# ---------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------
# DOUBLE BOOKING CHECK
# ---------------------------------------------------------------------
def has_conflict(db: Session, hall_id: int, start_date, end_date, start_time, end_time):
    conflict = db.query(Booking.id).filter(
        Booking.hall_id == hall_id,
        Booking.status == "booked",

        Booking.start_date <= end_date,
        Booking.end_date >= start_date,

        or_(
            Booking.start_date != Booking.end_date,
            start_date != end_date,

            and_(
                Booking.start_date == Booking.end_date,
                start_date == end_date,
                Booking.start_time < end_time,
                Booking.end_time > start_time
            )
        )
    ).first()

    return conflict is not None


# ---------------------------------------------------------------------
# PRICE CALCULATION
# ---------------------------------------------------------------------
def calculate_price(hall: Hall, start_date, end_date, start_time, end_time):
    # Same-day booking
    if start_date == end_date:
        hours = (
            (end_time.hour + end_time.minute / 60)
            - (start_time.hour + start_time.minute / 60)
        )

        if hours <= 0:
            raise HTTPException(status_code=400, detail="Invalid booking duration")

        total = hours * hall.price_per_hour
        if start_date.weekday() >= 5:
            total *= hall.weekend_price_multiplier

        return round(total + hall.security_deposit, 2)

    # Multi-day booking
    total = 0

    start_hours = 24 - (start_time.hour + start_time.minute / 60)
    total += start_hours * hall.price_per_hour

    full_days = (end_date - start_date).days - 1
    for i in range(full_days):
        weekday = (start_date + timedelta(days=i + 1)).weekday()
        rate = hall.price_per_day
        if weekday >= 5:
            rate *= hall.weekend_price_multiplier
        total += rate

    end_hours = end_time.hour + end_time.minute / 60
    total += end_hours * hall.price_per_hour

    if end_date.weekday() >= 5:
        total *= hall.weekend_price_multiplier

    return round(total + hall.security_deposit, 2)


# ---------------------------------------------------------------------
# CREATE BOOKING (USER ONLY)
# ---------------------------------------------------------------------
@router.post("/", response_model=dict)
def create_booking(
    data: BookingCreate,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    user, role = principal

    if role != "user":
        raise HTTPException(status_code=403, detail="Only users can book halls")

    hall = db.query(Hall).filter(
        Hall.id == data.hall_id,
        Hall.deleted == False
    ).first()
    if not hall:
        raise HTTPException(status_code=404, detail="Hall not found")

    now = datetime.now()

    # ---- DATE VALIDATIONS ----
    if data.start_date < date.today():
        raise HTTPException(status_code=400, detail="Cannot book past dates")

    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="End date cannot be before start date")

    # ---- TIME VALIDATIONS ----
    if data.start_date == date.today() and data.start_time <= now.time():
        raise HTTPException(status_code=400, detail="Start time must be in the future")

    if data.start_date == data.end_date and data.end_time <= data.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    # ---- DOUBLE BOOKING CHECK ----
    if has_conflict(
        db,
        data.hall_id,
        data.start_date,
        data.end_date,
        data.start_time,
        data.end_time,
    ):
        raise HTTPException(
            status_code=400,
            detail="Hall already booked for this time range"
        )

    # ---- PRICE ----
    total_price = calculate_price(
        hall,
        data.start_date,
        data.end_date,
        data.start_time,
        data.end_time,
    )

    booking = Booking(
        user_id=user.id,
        hall_id=data.hall_id,
        start_date=data.start_date,
        end_date=data.end_date,
        start_time=data.start_time,
        end_time=data.end_time,
        status="booked",
        total_price=total_price,
        payment_mode=data.payment_mode,
        payment_status="pending",
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    logger.bind(log_type="booking").info(
        f"Booking Created | User={user.email} | Hall={booking.hall_id}"
    )

    # ---- ONLINE PAYMENT ----
    if data.payment_mode == "online":
        rp_order = razorpay_client.order.create({
            "amount": int(total_price * 100),
            "currency": "INR",
            "receipt": f"booking_{booking.id}"
        })

        booking.razorpay_order_id = rp_order["id"]
        db.commit()

        return {
            "message": "Proceed with online payment",
            "booking_id": booking.id,
            "total_price": total_price,
            "razorpay_order_id": rp_order["id"],
            "razorpay_key_id": razorpay_client.auth[0],
        }

    return {
        "message": "Booking created. Pay at venue.",
        "booking_id": booking.id,
        "total_price": total_price,
        "payment_status": "pending",
    }


# ---------------------------------------------------------------------
# VERIFY PAYMENT
# ---------------------------------------------------------------------
@router.post("/verify-payment")
def verify_payment(
    booking_id: int,
    razorpay_payment_id: str,
    razorpay_order_id: str,
    razorpay_signature: str,
    db: Session = Depends(get_db),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.payment_status == "success":
        return {"message": "Payment already verified"}

    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
    except Exception:
        booking.payment_status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    booking.payment_status = "success"
    booking.razorpay_payment_id = razorpay_payment_id
    booking.razorpay_signature = razorpay_signature
    db.commit()

    return {"message": "Payment verified successfully"}


# ---------------------------------------------------------------------
# USER — MY BOOKINGS
# ---------------------------------------------------------------------
@router.get("/my", response_model=list[BookingOut])
def my_bookings(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    user, role = principal

    if role != "user":
        raise HTTPException(status_code=403, detail="Users only")

    bookings = db.query(Booking).filter(
        Booking.user_id == user.id
    ).all()

    return [
        BookingOut(
            id=b.id,
            hall_id=b.hall_id,
            start_date=b.start_date,
            end_date=b.end_date,
            start_time=b.start_time,
            end_time=b.end_time,
            status=b.status,
            total_price=b.total_price,
            booked_by_name=user.name,
            booked_by_email=user.email,
        )
        for b in bookings
    ]


# ---------------------------------------------------------------------
# CANCEL BOOKING
# ---------------------------------------------------------------------
@router.delete("/{booking_id}")
def cancel_booking(
    booking_id: int,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    user, role = principal

    if role != "user":
        raise HTTPException(status_code=403, detail="Users only")

    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.user_id == user.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.status = "cancelled"
    db.commit()

    return {"message": "Booking cancelled successfully"}

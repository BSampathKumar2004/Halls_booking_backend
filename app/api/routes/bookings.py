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
from app.models.enums import BookingStatus, PaymentStatus, PaymentMode

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
# DOUBLE BOOKING CHECK (OLD LOGIC, ENUM SAFE)
# ---------------------------------------------------------------------
def has_conflict(db: Session, hall_id: int, start_date, end_date, start_time, end_time):
    bookings = db.query(Booking).filter(
        Booking.hall_id == hall_id,
        Booking.status == BookingStatus.BOOKED.value,
        Booking.start_date <= end_date,
        Booking.end_date >= start_date,
    ).all()

    for b in bookings:

        # Case 1: Fully inside multi-day booking
        if b.start_date < start_date < b.end_date:
            return True

        # Case 2: Same-day overlap
        if start_date == end_date == b.start_date == b.end_date:
            if b.start_time < end_time and b.end_time > start_time:
                return True

        # Case 3: Booking starts on existing booking's start day
        if start_date == b.start_date and b.start_date != b.end_date:
            if b.start_time < end_time:
                return True

        # Case 4: Booking ends on existing booking's end day
        if end_date == b.end_date and b.start_date != b.end_date:
            if b.end_time > start_time:
                return True

        # Case 5: Fully covered day
        if start_date < b.start_date and end_date > b.end_date:
            return True

    return False

# ---------------------------------------------------------------------
# PRICE CALCULATION (FIXED & CORRECT)
# ---------------------------------------------------------------------
def calculate_price(hall: Hall, start_date, end_date, start_time, end_time):
    total = 0.0
    current = start_date

    while current <= end_date:
        is_weekend = current.weekday() >= 5
        multiplier = hall.weekend_price_multiplier if is_weekend else 1

        # SAME DAY
        if start_date == end_date:
            hours = (
                (end_time.hour + end_time.minute / 60)
                - (start_time.hour + start_time.minute / 60)
            )
            if hours <= 0:
                raise HTTPException(status_code=400, detail="Invalid booking duration")

            total += hours * hall.price_per_hour * multiplier
            break

        # FIRST DAY
        if current == start_date:
            hours = 24 - (start_time.hour + start_time.minute / 60)
            total += hours * hall.price_per_hour * multiplier

        # LAST DAY
        elif current == end_date:
            hours = end_time.hour + end_time.minute / 60
            total += hours * hall.price_per_hour * multiplier

        # FULL DAY
        else:
            total += hall.price_per_day * multiplier

        current += timedelta(days=1)

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

    if data.start_date < date.today():
        raise HTTPException(status_code=400, detail="Cannot book past dates")

    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="End date cannot be before start date")

    if data.start_date == date.today() and data.start_time <= now.time():
        raise HTTPException(status_code=400, detail="Start time must be in the future")

    if data.start_date == data.end_date and data.end_time <= data.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    if has_conflict(
        db,
        data.hall_id,
        data.start_date,
        data.end_date,
        data.start_time,
        data.end_time,
    ):
        raise HTTPException(status_code=400, detail="Hall already booked for this time range")

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
        status=BookingStatus.BOOKED.value,
        total_price=total_price,
        payment_mode=data.payment_mode.value,
        payment_status=PaymentStatus.PENDING.value,
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    logger.info(f"Booking Created | User={user.email} | Hall={booking.hall_id}")

    if data.payment_mode == PaymentMode.ONLINE:
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
        "payment_status": PaymentStatus.PENDING.value,
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

    if booking.payment_status == PaymentStatus.SUCCESS.value:
        return {"message": "Payment already verified"}

    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
    except Exception:
        booking.payment_status = PaymentStatus.FAILED.value
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    booking.payment_status = PaymentStatus.SUCCESS.value
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
            payment_mode=b.payment_mode,
            payment_status=b.payment_status,
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

    booking.status = BookingStatus.CANCELLED.value
    db.commit()

    return {"message": "Booking cancelled successfully"}


# =====================================================================
# AVAILABLE DATES
# =====================================================================
@router.get("/hall/{hall_id}/available-dates")
def available_dates(hall_id: int, month: str, db: Session = Depends(get_db)):

    try:
        year, month_num = map(int, month.split("-"))
        start_date = date(year, month_num, 1)
        end_date = (
            date(year + month_num // 12, (month_num % 12) + 1, 1)
            - timedelta(days=1)
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid month format (YYYY-MM)")

    bookings = db.query(Booking).filter(
        Booking.hall_id == hall_id,
        Booking.status == BookingStatus.BOOKED.value,
        Booking.start_date <= end_date,
        Booking.end_date >= start_date,
    ).all()

    booked = set()

    for b in bookings:
        d = max(b.start_date, start_date)
        last = min(b.end_date, end_date)
        while d <= last:
            booked.add(d)
            d += timedelta(days=1)

    all_days = [
        start_date + timedelta(days=i)
        for i in range((end_date - start_date).days + 1)
    ]

    available = [d.isoformat() for d in all_days if d not in booked]

    return {"hall_id": hall_id, "month": month, "available_dates": available}


# =====================================================================
# AVAILABLE TIME SLOTS
# =====================================================================
@router.get("/hall/{hall_id}/available-slots")
def available_slots(hall_id: int, date_str: str, db: Session = Depends(get_db)):

    try:
        target_date = date.fromisoformat(date_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")

    bookings = db.query(Booking).filter(
        Booking.hall_id == hall_id,
        Booking.status == BookingStatus.BOOKED.value,
        Booking.start_date <= target_date,
        Booking.end_date >= target_date,
    ).all()

    if not bookings:
        return {
            "hall_id": hall_id,
            "date": date_str,
            "available_slots": [{"start": "00:00", "end": "23:59"}],
        }

    blocked = []

    for b in bookings:
        if b.start_date < target_date < b.end_date:
            blocked.append(("00:00", "23:59"))
        elif target_date == b.start_date and b.start_date != b.end_date:
            blocked.append((b.start_time.strftime("%H:%M"), "23:59"))
        elif target_date == b.end_date and b.start_date != b.end_date:
            blocked.append(("00:00", b.end_time.strftime("%H:%M")))
        elif b.start_date == b.end_date == target_date:
            blocked.append((b.start_time.strftime("%H:%M"), b.end_time.strftime("%H:%M")))

    if ("00:00", "23:59") in blocked:
        return {"hall_id": hall_id, "date": date_str, "available_slots": []}

    blocked.sort()

    def to_min(t):
        return int(t[:2]) * 60 + int(t[3:])

    merged = []
    s, e = blocked[0]

    for cs, ce in blocked[1:]:
        if to_min(cs) <= to_min(e):
            e = max(e, ce)
        else:
            merged.append((s, e))
            s, e = cs, ce

    merged.append((s, e))

    available = []
    last = "00:00"

    for s, e in merged:
        if to_min(s) > to_min(last):
            available.append({"start": last, "end": s})
        last = e

    if last != "23:59":
        available.append({"start": last, "end": "23:59"})

    return {"hall_id": hall_id, "date": date_str, "available_slots": available}


# =====================================================================
# MULTI-HALL CALENDAR
# =====================================================================
@router.get("/calendar")
def multi_hall_calendar(month: str, db: Session = Depends(get_db)):

    try:
        year, month_num = map(int, month.split("-"))
        start_date = date(year, month_num, 1)
        end_date = (
            date(year + month_num // 12, (month_num % 12) + 1, 1)
            - timedelta(days=1)
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid month format")

    halls = db.query(Hall).filter(Hall.deleted == False).all()
    hall_map = {h.id: set() for h in halls}

    bookings = db.query(Booking).filter(
        Booking.status == BookingStatus.BOOKED.value,
        Booking.start_date <= end_date,
        Booking.end_date >= start_date,
    ).all()

    for b in bookings:
        d = max(b.start_date, start_date)
        last = min(b.end_date, end_date)
        while d <= last:
            hall_map[b.hall_id].add(d.isoformat())
            d += timedelta(days=1)

    return {
        "month": month,
        "halls": [
            {"hall_id": hid, "booked_dates": sorted(list(days))}
            for hid, days in hall_map.items()
        ]
    }

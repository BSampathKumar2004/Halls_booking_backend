from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, date

from app.db.session import SessionLocal
from app.models.booking import Booking
from app.models.user import User
from app.models.admin import Admin
from app.models.hall import Hall
from app.schemas.booking import BookingCreate, BookingOut
from app.core.auth_utils import decode_token
from app.utils.razorpay_client import razorpay_client
from app.core.logging_config import get_logger

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
# AUTH RESOLUTION
# ---------------------------------------------------------------------
def resolve_token_user(token: str, db: Session):
    payload = decode_token(token)
    email = payload["sub"]
    role = payload["role"]

    if role == "admin":
        admin = db.query(Admin).filter(Admin.email == email).first()
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        return admin, "admin"

    if role == "user":
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user, "user"

    raise HTTPException(status_code=401, detail="Invalid role")


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
# CREATE BOOKING
# ---------------------------------------------------------------------
@router.post("/", response_model=dict)
def create_booking(data: BookingCreate, token: str, db: Session = Depends(get_db)):
    user, role = resolve_token_user(token, db)
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

    if data.end_date < date.today():
        raise HTTPException(status_code=400, detail="End date cannot be in the past")

    # ---- TIME VALIDATIONS ----
    if data.start_date == date.today():
        if data.start_time <= now.time():
            raise HTTPException(
                status_code=400,
                detail="Start time must be in the future"
            )

    if data.start_date == data.end_date and data.end_time <= data.start_time:
        raise HTTPException(
            status_code=400,
            detail="End time must be after start time"
        )

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

    logger.info(
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

    # ✅ IDEMPOTENCY CHECK
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
def my_bookings(token: str, db: Session = Depends(get_db)):
    user, _ = resolve_token_user(token, db)

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
def cancel_booking(booking_id: int, token: str, db: Session = Depends(get_db)):
    user, _ = resolve_token_user(token, db)

    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.user_id == user.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.status = "cancelled"
    db.commit()

    return {"message": "Booking cancelled successfully"}


# ---------------------------------------------------------------------
# ADMIN — BOOKINGS OF OWN HALL (ENHANCED)
# ---------------------------------------------------------------------
@router.get("/admin/hall/{hall_id}")
def admin_hall_bookings(hall_id: int, token: str, db: Session = Depends(get_db)):
    admin, role = resolve_token_user(token, db)

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    hall = db.query(Hall).filter(
        Hall.id == hall_id,
        Hall.deleted == False
    ).first()

    if not hall:
        raise HTTPException(status_code=404, detail="Hall not found")

    # Ownership check
    if hall.admin_id != admin.id:
        raise HTTPException(status_code=403, detail="You do not own this hall")

    bookings = (
        db.query(Booking)
        .filter(Booking.hall_id == hall_id)
        .order_by(Booking.start_date.desc())
        .all()
    )

    response = []

    for b in bookings:
        response.append({
            "booking_id": b.id,
            "hall_id": b.hall_id,

            # ---- DATE & TIME ----
            "start_date": b.start_date,
            "end_date": b.end_date,
            "start_time": b.start_time,
            "end_time": b.end_time,

            # ---- BOOKING STATUS ----
            "booking_status": b.status,  # booked / cancelled

            # ---- PAYMENT INFO ----
            "payment_mode": b.payment_mode,
            "payment_status": b.payment_status,   # pending / success / failed
            "is_paid": True if b.payment_status == "success" else False,

            # ---- REFUND (future-proof) ----
            "is_refunded": getattr(b, "refund_status", None) == "success",

            # ---- USER INFO ----
            "booked_by": {
                "user_id": b.user.id,
                "name": b.user.name,
                "email": b.user.email,
            },

            # ---- CANCELLATION INFO ----
            "cancelled_by": (
                "user" if b.status == "cancelled" else None
            ),

            # ---- AMOUNT ----
            "total_price": b.total_price,
        })

    return response


# =====================================================================
# AVAILABLE DATES
# =====================================================================
@router.get("/hall/{hall_id}/available-dates")
def available_dates(hall_id: int, month: str, db: Session = Depends(get_db)):

    try:
        year, month_num = map(int, month.split("-"))
        start_date = date(year, month_num, 1)
        end_date = (date(year + month_num // 12, (month_num % 12) + 1, 1)
                    - timedelta(days=1))
    except:
        raise HTTPException(status_code=400, detail="Invalid month format")

    bookings = db.query(Booking).filter(
        Booking.hall_id == hall_id,
        Booking.status == "booked",
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

    all_days = [start_date + timedelta(days=i)
                for i in range((end_date - start_date).days + 1)]

    available = [d.isoformat() for d in all_days if d not in booked]

    return {"hall_id": hall_id, "month": month, "available_dates": available}


# =====================================================================
# AVAILABLE TIME SLOTS
# =====================================================================
@router.get("/hall/{hall_id}/available-slots")
def available_slots(hall_id: int, date_str: str, db: Session = Depends(get_db)):
    try:
        target_date = date.fromisoformat(date_str)
    except:
        raise HTTPException(status_code=400, detail="Invalid date format")

    bookings = db.query(Booking).filter(
        Booking.hall_id == hall_id,
        Booking.status == "booked",
        Booking.start_date <= target_date,
        Booking.end_date >= target_date,
    ).all()

    if not bookings:
        return {"hall_id": hall_id, "date": date_str,
                "available_slots": [{"start": "00:00", "end": "23:59"}]}

    blocked = []

    for b in bookings:
        if b.start_date < target_date < b.end_date:
            blocked.append(("00:00", "23:59"))
            continue
        if target_date == b.start_date and b.start_date != b.end_date:
            blocked.append((b.start_time.strftime("%H:%M"), "23:59"))
            continue
        if target_date == b.end_date and b.start_date != b.end_date:
            blocked.append(("00:00", b.end_time.strftime("%H:%M")))
            continue
        if b.start_date == b.end_date == target_date:
            blocked.append((b.start_time.strftime("%H:%M"),
                            b.end_time.strftime("%H:%M")))

    if any(a == "00:00" and b == "23:59" for a, b in blocked):
        return {"hall_id": hall_id, "date": date_str, "available_slots": []}

    blocked.sort()
    merged = []
    start, end = blocked[0]

    def to_min(t):
        return int(t[:2]) * 60 + int(t[3:])

    for s, e in blocked[1:]:
        if to_min(s) <= to_min(end):
            end = max(end, e)
        else:
            merged.append((start, end))
            start, end = s, e

    merged.append((start, end))

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
        end_date = (date(year + month_num // 12, (month_num % 12) + 1, 1)
                    - timedelta(days=1))
    except:
        raise HTTPException(status_code=400, detail="Invalid month format")

    halls = db.query(Hall).filter(Hall.deleted == False).all()
    hall_map = {h.id: [] for h in halls}

    bookings = db.query(Booking).filter(
        Booking.status == "booked",
        Booking.start_date <= end_date,
        Booking.end_date >= start_date,
    ).all()

    for b in bookings:
        d = max(b.start_date, start_date)
        last = min(b.end_date, end_date)
        while d <= last:
            hall_map[b.hall_id].append(d.isoformat())
            d += timedelta(days=1)

    return {
        "month": month,
        "halls": [
            {"hall_id": hid, "booked_dates": sorted(list(set(days)))}
            for hid, days in hall_map.items()
        ]
    }

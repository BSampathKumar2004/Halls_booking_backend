from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.db.session import SessionLocal
from app.models.booking import Booking
from app.models.hall import Hall
from app.core.auth_utils import decode_token
from app.core.logging_config import get_logger

router = APIRouter(prefix="/admin-analytics", tags=["Admin Analytics"])
logger = get_logger()


# ---------------- DB SESSION ----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- ADMIN VALIDATION ----------------
def require_admin(token: str, db: Session):
    payload = decode_token(token)
    if payload["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return payload["sub"]


# =====================================================================
# 1. TOTAL REVENUE (ALL TIME)
# =====================================================================
@router.get("/revenue/total")
def total_revenue(token: str, db: Session = Depends(get_db)):
    require_admin(token, db)

    total = db.query(func.sum(Booking.total_price)).filter(
        Booking.payment_status == "success"
    ).scalar()

    total = float(total or 0)

    logger.bind(log_type="admin").info(f"Admin checked total revenue → {total}")

    return {"total_revenue": total}


# =====================================================================
# 2. MONTHLY REVENUE
# =====================================================================
@router.get("/revenue/monthly")
def monthly_revenue(token: str, year: int, db: Session = Depends(get_db)):
    require_admin(token, db)

    results = (
        db.query(
            func.extract("month", Booking.start_date).label("month"),
            func.sum(Booking.total_price).label("revenue"),
        )
        .filter(
            func.extract("year", Booking.start_date) == year,
            Booking.payment_status == "success",
        )
        .group_by(func.extract("month", Booking.start_date))
        .order_by("month")
        .all()
    )

    monthly_data = [
        {"month": int(r.month), "revenue": float(r.revenue or 0)} for r in results
    ]

    logger.bind(log_type="admin").info(f"Admin checked monthly revenue for {year}")

    return {"year": year, "monthly_revenue": monthly_data}


# =====================================================================
# 3. REVENUE PER HALL
# =====================================================================
@router.get("/revenue/halls")
def revenue_per_hall(token: str, db: Session = Depends(get_db)):
    require_admin(token, db)

    results = (
        db.query(
            Hall.id,
            Hall.name,
            func.sum(Booking.total_price).label("revenue"),
        )
        .join(Booking, Booking.hall_id == Hall.id)
        .filter(Booking.payment_status == "success")
        .group_by(Hall.id)
        .order_by(func.sum(Booking.total_price).desc())
        .all()
    )

    data = [
        {"hall_id": r.id, "hall_name": r.name, "revenue": float(r.revenue or 0)}
        for r in results
    ]

    logger.bind(log_type="admin").info("Admin checked revenue per hall")

    return data


# =====================================================================
# 4. BOOKING COUNT PER HALL
# =====================================================================
@router.get("/bookings/hall-count")
def booking_count_per_hall(token: str, db: Session = Depends(get_db)):
    require_admin(token, db)

    results = (
        db.query(
            Hall.id,
            Hall.name,
            func.count(Booking.id).label("booking_count"),
        )
        .join(Booking, Booking.hall_id == Hall.id)
        .group_by(Hall.id)
        .order_by(func.count(Booking.id).desc())
        .all()
    )

    data = [
        {"hall_id": r.id, "hall_name": r.name, "booking_count": r.booking_count}
        for r in results
    ]

    logger.bind(log_type="admin").info("Admin checked booking count per hall")

    return data


# =====================================================================
# 5. PAYMENT MODE STATISTICS
# =====================================================================
@router.get("/payments/stats")
def payment_stats(token: str, db: Session = Depends(get_db)):
    require_admin(token, db)

    online = (
        db.query(func.count(Booking.id))
        .filter(Booking.payment_mode == "online", Booking.payment_status == "success")
        .scalar()
    )

    cash = (
        db.query(func.count(Booking.id))
        .filter(Booking.payment_mode == "venue", Booking.payment_status == "pending")
        .scalar()
    )

    failed_online = (
        db.query(func.count(Booking.id))
        .filter(Booking.payment_mode == "online", Booking.payment_status == "failed")
        .scalar()
    )

    logger.bind(log_type="admin").info("Admin checked payment stats")

    return {
        "online_payments": online or 0,
        "cash_payments": cash or 0,
        "failed_online_payments": failed_online or 0,
    }

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import SessionLocal
from app.models.booking import Booking
from app.models.hall import Hall
from app.core.logging_config import get_logger
from app.core.dependencies import get_current_principal

router = APIRouter(prefix="/admin-analytics", tags=["Admin Analytics"])
logger = get_logger()


# ---------------- DB SESSION ----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================================
# 1. TOTAL REVENUE (ALL TIME) – ADMIN ONLY
# =====================================================================
@router.get("/revenue/total")
def total_revenue(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    admin, role = principal

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    total = db.query(func.sum(Booking.total_price)).filter(
        Booking.payment_status == "success"
    ).scalar()

    total = float(total or 0)

    logger.bind(log_type="admin").info(
        f"Admin checked total revenue → {total}"
    )

    return {"total_revenue": total}


# =====================================================================
# 2. MONTHLY REVENUE – ADMIN ONLY
# =====================================================================
@router.get("/revenue/monthly")
def monthly_revenue(
    year: int,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    admin, role = principal

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

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
        {"month": int(r.month), "revenue": float(r.revenue or 0)}
        for r in results
    ]

    logger.bind(log_type="admin").info(
        f"Admin checked monthly revenue for {year}"
    )

    return {"year": year, "monthly_revenue": monthly_data}


# =====================================================================
# 3. REVENUE PER HALL – ADMIN ONLY
# =====================================================================
@router.get("/revenue/halls")
def revenue_per_hall(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    admin, role = principal

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

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
        {
            "hall_id": r.id,
            "hall_name": r.name,
            "revenue": float(r.revenue or 0)
        }
        for r in results
    ]

    logger.bind(log_type="admin").info(
        "Admin checked revenue per hall"
    )

    return data


# =====================================================================
# 4. BOOKING COUNT PER HALL – ADMIN ONLY
# =====================================================================
@router.get("/bookings/hall-count")
def booking_count_per_hall(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    admin, role = principal

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

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
        {
            "hall_id": r.id,
            "hall_name": r.name,
            "booking_count": r.booking_count
        }
        for r in results
    ]

    logger.bind(log_type="admin").info(
        "Admin checked booking count per hall"
    )

    return data


# =====================================================================
# 5. PAYMENT MODE STATISTICS – ADMIN ONLY
# =====================================================================
@router.get("/payments/stats")
def payment_stats(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    admin, role = principal

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    online = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.payment_mode == "online",
            Booking.payment_status == "success"
        )
        .scalar()
    )

    cash = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.payment_mode == "venue",
            Booking.payment_status == "pending"
        )
        .scalar()
    )

    failed_online = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.payment_mode == "online",
            Booking.payment_status == "failed"
        )
        .scalar()
    )

    logger.bind(log_type="admin").info(
        "Admin checked payment stats"
    )

    return {
        "online_payments": online or 0,
        "cash_payments": cash or 0,
        "failed_online_payments": failed_online or 0,
    }

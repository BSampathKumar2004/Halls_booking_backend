from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from app.db.session import SessionLocal
from app.models.hall import Hall
from app.models.user import User
from app.models.booking import Booking
from app.core.dependencies import get_current_principal

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------- DB SESSION ----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================================================
# ADMIN DASHBOARD STATS
# ==================================================
@router.get("/stats")
def admin_stats(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    admin, role = principal

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    total_halls = db.query(Hall).filter(Hall.deleted == False).count()
    total_users = db.query(User).count()
    total_bookings = db.query(Booking).count()

    today = date.today()
    today_bookings = db.query(Booking).filter(
        Booking.start_date <= today,
        Booking.end_date >= today
    ).count()

    return {
        "total_halls": total_halls,
        "total_users": total_users,
        "total_bookings": total_bookings,
        "today_bookings": today_bookings,
    }

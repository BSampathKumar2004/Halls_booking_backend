from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func
from datetime import date

from app.db.session import SessionLocal
from app.models.hall import Hall
from app.models.hall_amenities import HallAmenity
from app.models.amenities import Amenity
from app.models.hall_image import HallImage
from app.models.booking import Booking
from app.schemas.hall import HallCreate, HallOut
from app.core.auth_utils import decode_token
from app.models.admin import Admin

router = APIRouter(prefix="/halls", tags=["Halls"])


# --------------------------------------------------
# DB Session
# --------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# Admin validation + return admin object
# --------------------------------------------------
def require_admin(token: str, db: Session):
    payload = decode_token(token)

    if payload["role"] != "admin":
        raise HTTPException(status_code=401, detail="Admins only")

    admin = db.query(Admin).filter(Admin.email == payload["sub"]).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    return admin


# =====================================================================
# CREATE HALL  (Admin Only)
# =====================================================================
@router.post("/", response_model=HallOut)
def create_hall(data: HallCreate, token: str, db: Session = Depends(get_db)):
    admin = require_admin(token, db)

    hall = Hall(
        name=data.name,
        description=data.description,
        capacity=data.capacity,
        address=data.address,
        location=data.location,
        price_per_hour=data.price_per_hour,
        price_per_day=data.price_per_day,
        weekend_price_multiplier=data.weekend_price_multiplier,
        security_deposit=data.security_deposit,
        admin_id=admin.id,    # <-- Important: Ownership assigned
        deleted=False
    )

    db.add(hall)
    db.commit()
    db.refresh(hall)

    # Add amenities
    if data.amenity_ids:
        for aid in data.amenity_ids:
            if not db.query(Amenity).filter(Amenity.id == aid).first():
                raise HTTPException(status_code=404, detail=f"Amenity ID {aid} not found")
            db.add(HallAmenity(hall_id=hall.id, amenity_id=aid))

        db.commit()

    hall.amenities = (
        db.query(Amenity)
        .join(HallAmenity)
        .filter(HallAmenity.hall_id == hall.id)
        .all()
    )

    return hall


# =====================================================================
# EDIT HALL  (Admin Only + Ownership Check)
# =====================================================================
@router.put("/{hall_id}", response_model=HallOut)
def edit_hall(hall_id: int, data: HallCreate, token: str, db: Session = Depends(get_db)):
    admin = require_admin(token, db)

    hall = db.query(Hall).filter(Hall.id == hall_id, Hall.deleted == False).first()
    if not hall:
        raise HTTPException(status_code=404, detail="Hall not found")

    # Ownership check
    if hall.admin_id != admin.id:
        raise HTTPException(status_code=403, detail="You do not own this hall")

    # Update fields
    hall.name = data.name
    hall.description = data.description
    hall.capacity = data.capacity
    hall.address = data.address
    hall.location = data.location
    hall.price_per_hour = data.price_per_hour
    hall.price_per_day = data.price_per_day
    hall.weekend_price_multiplier = data.weekend_price_multiplier
    hall.security_deposit = data.security_deposit

    db.commit()

    # Update amenities
    db.query(HallAmenity).filter(HallAmenity.hall_id == hall.id).delete()
    if data.amenity_ids:
        for aid in data.amenity_ids:
            db.add(HallAmenity(hall_id=hall.id, amenity_id=aid))
    db.commit()

    hall.amenities = (
        db.query(Amenity)
        .join(HallAmenity)
        .filter(HallAmenity.hall_id == hall.id)
        .all()
    )

    return hall


# =====================================================================
# DELETE HALL  (Soft delete + Ownership Check)
# =====================================================================
@router.delete("/{hall_id}")
def delete_hall(hall_id: int, token: str, db: Session = Depends(get_db)):
    admin = require_admin(token, db)

    hall = db.query(Hall).filter(Hall.id == hall_id, Hall.deleted == False).first()
    if not hall:
        raise HTTPException(status_code=404, detail="Hall not found")

    # Ownership check
    if hall.admin_id != admin.id:
        raise HTTPException(status_code=403, detail="You do not own this hall")

    hall.deleted = True
    db.commit()

    return {"message": "Hall deleted successfully"}


# =====================================================================
# LIST HALLS (Normal user / Guest)
# =====================================================================
@router.get("/", response_model=list[HallOut])
def list_halls(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    halls = (
        db.query(Hall)
        .options(joinedload(Hall.amenities))
        .filter(Hall.deleted == False)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return halls


# =====================================================================
# SEARCH BY NAME
# =====================================================================
@router.get("/search/name", response_model=list[HallOut])
def search_by_name(q: str, db: Session = Depends(get_db)):
    halls = (
        db.query(Hall)
        .filter(Hall.deleted == False)
        .filter(Hall.name.ilike(f"%{q}%"))
        .all()
    )
    return halls


# =====================================================================
# FILTER BY LOCATION
# =====================================================================
@router.get("/filter/location", response_model=list[HallOut])
def filter_by_location(location: str, db: Session = Depends(get_db)):
    halls = (
        db.query(Hall)
        .filter(Hall.deleted == False)
        .filter(Hall.location.ilike(f"%{location}%"))
        .all()
    )
    return halls


# =====================================================================
# SORT BY PRICE
# =====================================================================
@router.get("/sort/price", response_model=list[HallOut])
def sort_by_price(order: str = "asc", db: Session = Depends(get_db)):
    halls = (
        db.query(Hall)
        .filter(Hall.deleted == False)
        .order_by(Hall.price_per_day.asc() if order == "asc" else Hall.price_per_day.desc())
        .all()
    )
    return halls


# =====================================================================
# SORT BY CAPACITY
# =====================================================================
@router.get("/sort/capacity", response_model=list[HallOut])
def sort_by_capacity(order: str = "asc", db: Session = Depends(get_db)):
    halls = (
        db.query(Hall)
        .filter(Hall.deleted == False)
        .order_by(Hall.capacity.asc() if order == "asc" else Hall.capacity.desc())
        .all()
    )
    return halls


# =====================================================================
# FILTER BY AMENITIES
# =====================================================================
@router.get("/filter/amenities", response_model=list[HallOut])
def filter_by_amenities(amenities: str, db: Session = Depends(get_db)):
    names = [a.strip() for a in amenities.split(",")]

    halls = (
        db.query(Hall)
        .join(HallAmenity)
        .join(Amenity)
        .filter(Amenity.name.in_(names))
        .group_by(Hall.id)
        .having(func.count(Hall.id) >= len(names))
        .all()
    )

    return halls


# =====================================================================
# FILTER BY DATE AVAILABILITY
# =====================================================================
@router.get("/filter/available", response_model=list[HallOut])
def filter_by_availability(date_str: str, db: Session = Depends(get_db)):

    try:
        target_date = date.fromisoformat(date_str)
    except:
        raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD)")

    halls = (
        db.query(Hall)
        .filter(Hall.deleted == False)
        .filter(
            ~Hall.bookings.any(
                and_(
                    Booking.status == "booked",
                    Booking.start_date <= target_date,
                    Booking.end_date >= target_date
                )
            )
        )
        .all()
    )

    return halls


# =====================================================================
# HALL DETAILS
# =====================================================================
@router.get("/{hall_id}", response_model=HallOut)
def get_hall(hall_id: int, db: Session = Depends(get_db)):
    hall = (
        db.query(Hall)
        .filter(Hall.id == hall_id, Hall.deleted == False)
        .first()
    )

    if not hall:
        raise HTTPException(status_code=404, detail="Hall not found")

    hall.images = db.query(HallImage).filter(HallImage.hall_id == hall_id).all()

    return hall

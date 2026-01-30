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

# 🔥 Redis helpers
from app.core.redis import get_cache, set_cache, delete_cache

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
        admin_id=admin.id,
        deleted=False
    )

    db.add(hall)
    db.commit()
    db.refresh(hall)

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

    # 🧹 Clear cache
    delete_cache("halls:*")

    return hall


# =====================================================================
# EDIT HALL
# =====================================================================
@router.put("/{hall_id}", response_model=HallOut)
def edit_hall(hall_id: int, data: HallCreate, token: str, db: Session = Depends(get_db)):
    admin = require_admin(token, db)

    hall = db.query(Hall).filter(Hall.id == hall_id, Hall.deleted == False).first()
    if not hall:
        raise HTTPException(status_code=404, detail="Hall not found")

    if hall.admin_id != admin.id:
        raise HTTPException(status_code=403, detail="You do not own this hall")

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

    # 🧹 Clear cache
    delete_cache(f"hall:{hall_id}")
    delete_cache("halls:*")

    return hall


# =====================================================================
# DELETE HALL
# =====================================================================
@router.delete("/{hall_id}")
def delete_hall(hall_id: int, token: str, db: Session = Depends(get_db)):
    admin = require_admin(token, db)

    hall = db.query(Hall).filter(Hall.id == hall_id, Hall.deleted == False).first()
    if not hall:
        raise HTTPException(status_code=404, detail="Hall not found")

    if hall.admin_id != admin.id:
        raise HTTPException(status_code=403, detail="You do not own this hall")

    hall.deleted = True
    db.commit()

    # 🧹 Clear cache
    delete_cache(f"hall:{hall_id}")
    delete_cache("halls:*")

    return {"message": "Hall deleted successfully"}


# =====================================================================
# LIST HALLS (CACHED)
# =====================================================================
@router.get("/", response_model=list[HallOut])
def list_halls(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):

    cache_key = f"halls:page={page}:limit={limit}"

    cached = get_cache(cache_key)
    if cached:
        return cached

    halls = (
        db.query(Hall)
        .options(joinedload(Hall.amenities))
        .filter(Hall.deleted == False)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    halls_data = [
        HallOut.model_validate(h).model_dump(mode="json")
        for h in halls
    ]

    set_cache(cache_key, halls_data, ttl=60)

    return halls_data


# =====================================================================
# SEARCH BY NAME (CACHED)
# =====================================================================
@router.get("/search/name", response_model=list[HallOut])
def search_by_name(q: str, db: Session = Depends(get_db)):

    cache_key = f"halls:search:name:{q.lower()}"

    cached = get_cache(cache_key)
    if cached:
        return cached

    halls = (
        db.query(Hall)
        .options(joinedload(Hall.amenities))
        .filter(Hall.deleted == False)
        .filter(Hall.name.ilike(f"%{q}%"))
        .all()
    )

    # ✅ ORM → Pydantic → dict
    halls_data = [
        HallOut.model_validate(h).model_dump(mode="json")
        for h in halls
    ]

    set_cache(cache_key, halls_data, ttl=30)

    return halls_data


# =====================================================================
# FILTER BY LOCATION (CACHED)
# =====================================================================
@router.get("/filter/location", response_model=list[HallOut])
def filter_by_location(location: str, db: Session = Depends(get_db)):

    cache_key = f"halls:filter:location:{location.lower()}"

    cached = get_cache(cache_key)
    if cached:
        return cached

    halls = (
        db.query(Hall)
        .options(joinedload(Hall.amenities))
        .filter(Hall.deleted == False)
        .filter(Hall.location.ilike(f"%{location}%"))
        .all()
    )

    # ✅ ORM → Pydantic → dict
    halls_data = [
        HallOut.model_validate(h).model_dump(mode="json")
        for h in halls
    ]

    set_cache(cache_key, halls_data, ttl=30)

    return halls_data


# =====================================================================
# HALL DETAILS (CACHED)
# =====================================================================
@router.get("/{hall_id}", response_model=HallOut)
def get_hall(hall_id: int, db: Session = Depends(get_db)):

    cache_key = f"hall:{hall_id}"

    cached = get_cache(cache_key)
    if cached:
        return cached

    hall = (
        db.query(Hall)
        .options(joinedload(Hall.amenities))
        .filter(Hall.id == hall_id, Hall.deleted == False)
        .first()
    )

    if not hall:
        raise HTTPException(status_code=404, detail="Hall not found")

    hall.images = db.query(HallImage).filter(
        HallImage.hall_id == hall_id
    ).all()

    # ✅ Convert ORM → Pydantic → dict
    hall_data = HallOut.model_validate(hall).model_dump()

    set_cache(cache_key, hall_data, ttl=120)

    return hall_data
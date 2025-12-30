from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt
import os

from app.db.session import SessionLocal
from app.models.user import User
from app.models.admin import Admin
from app.models.hall import Hall
from app.schemas.user import UserOut
from app.schemas.admin import AdminOut
from app.schemas.hall import HallOut

router = APIRouter(prefix="/admin-panel", tags=["Admin Panel"])


# --------------------------------------------------
# DB SESSION
# --------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# ADMIN VALIDATION
# --------------------------------------------------
def validate_admin(token: str, db: Session) -> Admin:
    try:
        payload = jwt.decode(
            token,
            os.getenv("JWT_SECRET"),
            algorithms=[os.getenv("JWT_ALGORITHM")]
        )

        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admins only")

        email = payload.get("sub")

        admin = db.query(Admin).filter(Admin.email == email).first()
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")

        return admin

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ==================================================
# GET ALL USERS (ADMIN)
# ==================================================
@router.get("/users", response_model=list[UserOut])
def get_all_users(token: str, db: Session = Depends(get_db)):
    validate_admin(token, db)
    return db.query(User).all()


# ==================================================
# GET ALL ADMINS
# ==================================================
@router.get("/admins", response_model=list[AdminOut])
def get_all_admins(token: str, db: Session = Depends(get_db)):
    validate_admin(token, db)
    return db.query(Admin).all()


# ==================================================
# GET ONLY LOGGED-IN ADMIN'S HALLS ✅
# ==================================================
@router.get("/halls", response_model=list[HallOut])
def get_all_halls(token: str, db: Session = Depends(get_db)):
    admin = validate_admin(token, db)

    halls = (
        db.query(Hall)
        .filter(
            Hall.deleted == False,
            Hall.admin_id == admin.id
        )
        .all()
    )

    return halls

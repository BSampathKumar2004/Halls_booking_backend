from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.models.admin import Admin
from app.models.hall import Hall
from app.schemas.user import UserOut
from app.schemas.admin import AdminOut
from app.schemas.hall import HallOut
from app.core.dependencies import get_current_principal

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


# ==================================================
# GET ALL USERS (ADMIN ONLY)
# ==================================================
@router.get("/users", response_model=list[UserOut])
def get_all_users(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    admin, role = principal

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    return db.query(User).all()


# ==================================================
# GET ALL ADMINS (ADMIN ONLY)
# ==================================================
@router.get("/admins", response_model=list[AdminOut])
def get_all_admins(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    admin, role = principal

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    return db.query(Admin).all()


# ==================================================
# GET ONLY LOGGED-IN ADMIN'S HALLS ✅ (ADMIN ONLY)
# ==================================================
@router.get("/halls", response_model=list[HallOut])
def get_all_halls(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    admin, role = principal

    if role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    halls = (
        db.query(Hall)
        .filter(
            Hall.deleted == False,
            Hall.admin_id == admin.id
        )
        .all()
    )

    return halls

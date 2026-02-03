from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.core.auth_utils import decode_token
from app.models.user import User
from app.models.admin import Admin

security = HTTPBearer()  # 👈 THIS IS THE KEY FIX


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials  # Extract JWT token

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

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid role"
    )

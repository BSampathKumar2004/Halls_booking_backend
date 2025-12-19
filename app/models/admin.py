from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.db.session import Base


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # NEW — relationship: Admin → Halls they own
    halls = relationship(
        "Hall",
        back_populates="admin",
        cascade="all, delete"
    )

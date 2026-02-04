from sqlalchemy import Column, Integer, String, Date, Time, Float, ForeignKey
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.models.enums import BookingStatus, PaymentStatus, PaymentMode


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"))
    hall_id = Column(Integer, ForeignKey("halls.id"))

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # 🔒 ENUM-AWARE FIELDS (still stored as string in DB)
    status = Column(
        String,
        nullable=False,
        default=BookingStatus.BOOKED.value
    )

    payment_mode = Column(
        String,
        nullable=False,
        default=PaymentMode.VENUE.value
    )

    payment_status = Column(
        String,
        nullable=False,
        default=PaymentStatus.PENDING.value
    )

    total_price = Column(Float, nullable=False)

    # Razorpay
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)
    razorpay_signature = Column(String, nullable=True)

    user = relationship("User")
    hall = relationship("Hall", back_populates="bookings")

from enum import Enum


class BookingStatus(str, Enum):
    BOOKED = "booked"
    CANCELLED = "cancelled"
    # future ready
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"  # future ready


class PaymentMode(str, Enum):
    ONLINE = "online"
    VENUE = "venue"

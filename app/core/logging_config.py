from loguru import logger
import os

LOG_DIR = "logs"

# Create folder if missing
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Remove default handler
logger.remove()

# General application log
logger.add(
    f"{LOG_DIR}/app.log",
    rotation="1 week",
    retention="4 weeks",
    level="INFO",
    enqueue=True,
    format="{time} | {level} | {message}"
)

# Booking logs
logger.add(
    f"{LOG_DIR}/bookings.log",
    rotation="1 week",
    retention="4 weeks",
    level="INFO",
    enqueue=True,
    filter=lambda record: record["extra"].get("log_type") == "booking",
    format="{time} | {level} | {message}"
)

# Payment logs
logger.add(
    f"{LOG_DIR}/payments.log",
    rotation="1 week",
    retention="4 weeks",
    level="INFO",
    enqueue=True,
    filter=lambda record: record["extra"].get("log_type") == "payment",
    format="{time} | {level} | {message}"
)

# Admin activity logs
logger.add(
    f"{LOG_DIR}/admin.log",
    rotation="1 week",
    retention="4 weeks",
    level="INFO",
    enqueue=True,
    filter=lambda record: record["extra"].get("log_type") == "admin",
    format="{time} | {level} | {message}"
)

# Error logs
logger.add(
    f"{LOG_DIR}/errors.log",
    rotation="1 week",
    retention="8 weeks",
    level="ERROR",
    enqueue=True,
)

def get_logger():
    return logger

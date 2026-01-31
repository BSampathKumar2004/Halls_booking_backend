from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.routes import auth, halls, hall_images, bookings, amenities
from app.api.routes.admin_panel import router as admin_panel_router
from app.api.routes import admin_analytics

from app.db.session import SessionLocal
from app.core.redis import redis_client

# ⭐ Import logging system
from app.core.logging_config import get_logger

logger = get_logger()

app = FastAPI(
    title="Hall Booking API",
    version="1.0.0",
    description="API for Hall Booking, Amenities, Users & Admin Management"
)

# --------------------------------------------------
# Request Logging Middleware
# --------------------------------------------------
@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"REQUEST: {request.method} {request.url}")

    try:
        response = await call_next(request)
        logger.info(f"RESPONSE: {response.status_code} {request.url}")
        return response

    except Exception as e:
        logger.error(f"ERROR: {request.url} -> {str(e)}")
        raise e


# --------------------------------------------------
# CORS (Frontend access)
# --------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 🔒 Restrict later for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# Routers
# --------------------------------------------------
app.include_router(auth.router)
app.include_router(halls.router)
app.include_router(amenities.router)
app.include_router(hall_images.router)
app.include_router(bookings.router)
app.include_router(admin_panel_router)
app.include_router(admin_analytics.router)

# --------------------------------------------------
# Root endpoint
# --------------------------------------------------
@app.get("/", tags=["Root"])
def root():
    return {"message": "Backend running successfully"}


# --------------------------------------------------
# DB session for health check
# --------------------------------------------------
def get_db_health():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# Health Check Endpoint
# --------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db_health)):
    health_status = {
        "status": "ok",
        "database": "unknown",
        "redis": "unknown"
    }

    # ✅ Database check
    try:
        db.execute(text("SELECT 1"))
        health_status["database"] = "ok"
    except Exception:
        health_status["database"] = "down"
        health_status["status"] = "error"

    # ✅ Redis check (optional, non-blocking)
    try:
        if redis_client:
            redis_client.ping()
            health_status["redis"] = "ok"
        else:
            health_status["redis"] = "not_configured"
    except Exception:
        health_status["redis"] = "down"

    # ❌ If DB is down → return 500
    if health_status["database"] != "ok":
        raise HTTPException(status_code=500, detail=health_status)

    return health_status

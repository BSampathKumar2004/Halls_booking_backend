from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, halls, hall_images, bookings, amenities
from app.api.routes.admin_panel import router as admin_panel_router

# ⭐ Import logging system
from app.core.logging_config import get_logger
from app.api.routes import admin_analytics

logger = get_logger()

app = FastAPI(
    title="Hall Booking API",
    version="1.0.0",
    description="API for Hall Booking, Amenities, Users & Admin Management"
)

# ⭐ Request Logging Middleware
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


# ⭐ CORS (important for frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Can restrict later for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- ROUTERS REGISTER ORDER MATTERS --------
app.include_router(auth.router)
app.include_router(halls.router)
app.include_router(amenities.router)
app.include_router(hall_images.router)
app.include_router(bookings.router)
app.include_router(admin_panel_router)
app.include_router(admin_analytics.router)

@app.get("/", tags=["Root"])
def root():
    return {"message": "Backend running successfully"}

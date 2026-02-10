Hall Booking Backend API

A production-ready backend for managing hall listings, bookings, payments, and admin operations, built using FastAPI, PostgreSQL, SQLAlchemy, JWT authentication, and Razorpay.

🚀 Features
👤 Authentication & Authorization

User & Admin registration/login
JWT-based authentication
Role-based access control (user, admin)
Secure Authorization: Bearer <token> header usage

🏢 Hall Management (Admin)
Create, edit, delete halls
Add pricing (hour/day), weekend multipliers, security deposit
Assign amenities
Upload hall images (Cloudinary)
Soft delete support

📅 Booking System (User)
Create bookings (hour-based / multi-day)
Prevent double bookings (time-slot aware)
View personal bookings
Cancel bookings

💰 Pricing Engine
Hour-based pricing
Day-based pricing for multi-day bookings
Weekend price multiplier
Security deposit support
Real-world pricing rules (full-day vs hourly)

💳 Payments (Razorpay)
Online payment order creation
Payment verification
Payment status tracking
Venue payment support

📊 Admin Analytics
Total revenue
Monthly revenue
Revenue per hall
Booking count per hall
Payment statistics

⚡ Performance & Infra
Redis caching for read-heavy APIs
Docker & Docker Compose setup
Alembic migrations
Railway / Cloud-ready deployment

🧱 Tech Stack
Layer	Technology
Backend	-- FastAPI
ORM -- SQLAlchemy
Database --	PostgreSQL
Auth -- JWT (HTTP Bearer)
Payments -- Razorpay
Cache	-- Redis
Images -- Cloudinary
Migrations --	Alembic
Deployment --	Docker, Railway

📁 Project Structure
app/
├── api/
│   └── routes/
│       ├── auth.py
│       ├── halls.py
│       ├── bookings.py
│       ├── amenities.py
│       ├── hall_images.py
│       ├── admin.py
│       └── admin_analytics.py
│
├── core/
│   ├── auth_utils.py
│   ├── dependencies.py
│   ├── security.py
│   ├── redis.py
│   └── logging_config.py
│
├── db/
│   ├── base.py
│   ├── session.py
│   └── migrations/
│
├── models/
│   ├── user.py
│   ├── admin.py
│   ├── hall.py
│   ├── booking.py
│   ├── amenities.py
│   └── enums.py
│
├── schemas/
│   ├── user.py
│   ├── admin.py
│   ├── hall.py
│   └── booking.py
│
├── utils/
│   ├── pricing.py
│   ├── razorpay_client.py
│   └── cloudinary_utils.py
│
├── main.py
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
└── requirements.txt

🔐 Authentication Guide
✅ Backend expects JWT in headers only
Authorization: Bearer <JWT_TOKEN>
❌ Tokens in request body or query params are not accepted.
Swagger UI
Paste only the token value
Swagger auto-adds Bearer
Frontend
Must manually add Bearer prefix
📦 Environment Variables (.env)
DATABASE_URL=postgresql://postgres:password@postgres:5432/hall_booking
REDIS_URL=redis://redis:6379

JWT_SECRET=your_secret_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

CLOUDINARY_CLOUD_NAME=xxxx
CLOUDINARY_API_KEY=xxxx
CLOUDINARY_API_SECRET=xxxx

RAZORPAY_KEY_ID=xxxx
RAZORPAY_KEY_SECRET=xxxx
RAZORPAY_CURRENCY=INR

🐳 Running Locally (Docker)
docker-compose up -d --build


Run migrations:
docker exec -it <backend_container> alembic upgrade head

📖 API Documentation
Once running, open:
/docs
Example:

http://localhost:8000/docs

🧮 Pricing Logic Summary
Scenario	Calculation
Same-day booking	Hour-based pricing
Multi-day, same start & end time	Full-day pricing
Mixed (partial days)	Hour + day combination
Weekend	Multiplier applied
Security deposit	Added separately

🧠 Design Decisions
JWT auth via headers only (industry standard)
Enums for booking/payment statuses (data integrity)
Redis caching for scalability
Soft delete for halls
Separation of concerns (routes / services / utils)

🔮 Future Enhancements
Refund workflows
Booking approval system
Admin role hierarchy
Dynamic pricing rules
Notification system


Author

Sampath Kumar
Backend Developer

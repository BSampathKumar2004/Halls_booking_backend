from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
from dotenv import load_dotenv

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

# -----------------------------
# Import SQLAlchemy Base + Models
# -----------------------------
from app.db.session import Base
from app.models.admin import Admin
from app.models.user import User
from app.models.hall import Hall
from app.models.hall_image import HallImage
from app.models.booking import Booking
from app.models.amenities import Amenity
from app.models.hall_amenities import HallAmenity

# -----------------------------
# Alembic Configuration
# -----------------------------
config = context.config

# -----------------------------
# Inject DATABASE_URL from .env
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable not found!")

config.set_main_option("sqlalchemy.url", DATABASE_URL)

# -----------------------------
# Setup logging (Optional)
# -----------------------------
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -----------------------------
# Metadata for autogenerate
# -----------------------------
target_metadata = Base.metadata


# ===============================================================
# OFFLINE MIGRATIONS
# ===============================================================
def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ===============================================================
# ONLINE MIGRATIONS
# ===============================================================
def run_migrations_online():
    """Run migrations in 'online' mode."""
    
    from sqlalchemy import create_engine

    DATABASE_URL = config.get_main_option("sqlalchemy.url")

    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ===============================================================
# EXECUTION MODE (online/offline)
# ===============================================================
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

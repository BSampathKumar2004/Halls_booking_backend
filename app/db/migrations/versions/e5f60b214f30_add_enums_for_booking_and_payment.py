from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e5f60b214f30"
down_revision = "0ea7aa1e7f0a"
branch_labels = None
depends_on = None


def upgrade():
    # 1️⃣ Create ENUM types
    booking_status_enum = sa.Enum(
        "booked",
        "cancelled",
        "completed",
        "no_show",
        name="bookingstatus"
    )

    payment_status_enum = sa.Enum(
        "pending",
        "success",
        "failed",
        "refunded",
        name="paymentstatus"
    )

    payment_mode_enum = sa.Enum(
        "online",
        "venue",
        name="paymentmode"
    )

    booking_status_enum.create(op.get_bind(), checkfirst=True)
    payment_status_enum.create(op.get_bind(), checkfirst=True)
    payment_mode_enum.create(op.get_bind(), checkfirst=True)

    # 2️⃣ Alter columns → ENUM (safe cast)
    op.execute(
        """
        ALTER TABLE bookings
        ALTER COLUMN status TYPE bookingstatus
        USING status::bookingstatus
        """
    )

    op.execute(
        """
        ALTER TABLE bookings
        ALTER COLUMN payment_status TYPE paymentstatus
        USING payment_status::paymentstatus
        """
    )

    op.execute(
        """
        ALTER TABLE bookings
        ALTER COLUMN payment_mode TYPE paymentmode
        USING payment_mode::paymentmode
        """
    )

    # 3️⃣ Set server defaults
    op.alter_column(
        "bookings",
        "status",
        server_default="booked",
        nullable=False
    )

    op.alter_column(
        "bookings",
        "payment_status",
        server_default="pending",
        nullable=False
    )

    op.alter_column(
        "bookings",
        "payment_mode",
        server_default="venue",
        nullable=False
    )


def downgrade():
    # 1️⃣ Convert ENUM → STRING
    op.execute(
        "ALTER TABLE bookings ALTER COLUMN status TYPE VARCHAR"
    )
    op.execute(
        "ALTER TABLE bookings ALTER COLUMN payment_status TYPE VARCHAR"
    )
    op.execute(
        "ALTER TABLE bookings ALTER COLUMN payment_mode TYPE VARCHAR"
    )

    # 2️⃣ Drop ENUM types
    op.execute("DROP TYPE bookingstatus")
    op.execute("DROP TYPE paymentstatus")
    op.execute("DROP TYPE paymentmode")


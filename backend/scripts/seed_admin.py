"""Seed the first admin user.

Run ONCE after `alembic upgrade head`:
    python scripts/seed_admin.py

Creates: admin@example.com / admin123
Change these before using in any real environment.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

# Make sure we can import from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.auth.password_service import hash_password
from src.infrastructure.db.session import get_engine
from src.infrastructure.db.tables import users_table


async def main() -> None:
    email = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
    password = os.getenv("SEED_ADMIN_PASSWORD", "admin123")

    async with get_engine().connect() as conn:
        # Check if admin already exists
        import sqlalchemy as sa
        result = await conn.execute(
            sa.select(users_table.c.id).where(users_table.c.email == email)
        )
        if result.fetchone():
            print(f"Admin already exists: {email}")
            return

        await conn.execute(
            users_table.insert().values(
                id=uuid4(),
                email=email,
                hashed_password=hash_password(password),
                role="admin",
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await conn.commit()

    print(f"✅ Admin user created")
    print(f"   Email:    {email}")
    print(f"   Password: {password}")
    print(f"\nChange these immediately in a real environment!")


asyncio.run(main())

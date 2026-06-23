"""User domain entity — authentication and RBAC."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field

from src.domain.enums.user_role import UserRole
from src.domain.errors.domain_errors import AuthorizationError


class User(BaseModel):
    """Represents an authenticated platform user.

    Password hashing is handled exclusively in infrastructure/auth layer.
    This entity stores the hashed password — never plaintext.
    """

    model_config = {"frozen": False}

    id: UUID = Field(default_factory=uuid4)
    email: EmailStr = Field(..., description="Unique user email address")
    hashed_password: str = Field(..., description="bcrypt hashed password — never plaintext")
    role: UserRole = Field(default=UserRole.VIEWER)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def require_role(self, minimum_role: UserRole) -> None:
        """Assert this user has at least the required role.

        Role hierarchy: VIEWER < ANALYST < ADMIN

        Args:
            minimum_role: The minimum role required for the operation.

        Raises:
            AuthorizationError: If the user's role is below the required level.
        """
        _hierarchy = {
            UserRole.VIEWER: 0,
            UserRole.ANALYST: 1,
            UserRole.ADMIN: 2,
        }
        if _hierarchy[self.role] < _hierarchy[minimum_role]:
            raise AuthorizationError(
                f"User {self.id} with role '{self.role}' lacks permission. "
                f"Required: '{minimum_role}'.",
                code="INSUFFICIENT_ROLE",
            )

    def deactivate(self) -> None:
        """Deactivate this user account."""
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)

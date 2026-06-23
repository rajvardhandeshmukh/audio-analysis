"""JWT and RBAC authentication service.

Rule 5-variant: Only this module calls PyJWT. No jwt imports elsewhere.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from src.domain.enums.user_role import UserRole
from src.domain.errors.domain_errors import AuthenticationError, AuthorizationError, TokenExpiredError
from src.infrastructure.config.settings import get_auth_settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class JWTService:
    """Manages JWT token creation and validation with RBAC role enforcement."""

    def __init__(self, secret: str, algorithm: str, expire_minutes: int) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes

    @classmethod
    def from_settings(cls) -> "JWTService":
        cfg = get_auth_settings()
        return cls(cfg.jwt_secret_key, cfg.jwt_algorithm, cfg.jwt_expire_minutes)

    def create_token(self, user_id: UUID, role: UserRole) -> str:
        """Issue a signed JWT with user_id and role claims.

        Args:
            user_id: Subject claim.
            role: User role embedded in payload.

        Returns:
            Signed JWT string.
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "role": role.value,
            "iat": now,
            "exp": now + timedelta(minutes=self._expire_minutes),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode_token(self, token: str) -> dict:  # type: ignore[type-arg]
        """Decode and validate a JWT token.

        Args:
            token: Bearer token string (without 'Bearer ' prefix).

        Returns:
            Decoded payload dict.

        Raises:
            TokenExpiredError: If the token has expired.
            AuthenticationError: If the token is invalid.
        """
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["sub", "role", "exp"]},
            )
            return payload
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired. Please re-authenticate.") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"Invalid token: {exc}") from exc

    def require_role(self, payload: dict, minimum_role: UserRole) -> None:  # type: ignore[type-arg]
        """Assert that the token role meets the minimum required role.

        Role hierarchy: ADMIN > ANALYST > VIEWER

        Args:
            payload: Decoded token payload.
            minimum_role: Minimum required role.

        Raises:
            AuthorizationError: If the user role is insufficient.
        """
        _HIERARCHY = {
            UserRole.VIEWER: 0,
            UserRole.ANALYST: 1,
            UserRole.ADMIN: 2,
        }
        token_role = UserRole(payload.get("role", "viewer"))
        if _HIERARCHY.get(token_role, -1) < _HIERARCHY.get(minimum_role, 99):
            raise AuthorizationError(
                f"Role '{token_role.value}' is insufficient. "
                f"Required: '{minimum_role.value}' or higher."
            )

    def get_user_id(self, payload: dict) -> UUID:  # type: ignore[type-arg]
        return UUID(payload["sub"])

    def get_role(self, payload: dict) -> UserRole:  # type: ignore[type-arg]
        return UserRole(payload["role"])

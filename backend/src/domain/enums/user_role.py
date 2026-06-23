"""User role enumeration for RBAC."""

from enum import StrEnum


class UserRole(StrEnum):
    """RBAC roles with increasing privilege levels.

    Privilege order: VIEWER < ANALYST < ADMIN
    """

    VIEWER = "viewer"    # Read-only: view jobs, transcripts, reports
    ANALYST = "analyst"  # Read + trigger reruns, add sources
    ADMIN = "admin"      # Full access: user management, system config

"""Unified API response envelope and pagination schema.

All endpoints return ApiResponse[T] — consistent contract for SolidJS integration.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard API response envelope.

    Success:  {"success": true,  "data": <T>,   "error": null}
    Error:    {"success": false, "data": null,   "error": {"code": ..., "message": ...}}
    """

    success: bool
    data: T | None = None
    error: "ApiError | None" = None

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        return cls(success=True, data=data, error=None)

    @classmethod
    def fail(cls, code: str, message: str) -> "ApiResponse[None]":
        return cls(success=False, data=None, error=ApiError(code=code, message=message))


class ApiError(BaseModel):
    code: str
    message: str


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool = Field(default=False)

    @classmethod
    def of(cls, items: list[T], total: int, limit: int, offset: int) -> "PaginatedResponse[T]":
        return cls(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + len(items)) < total,
        )

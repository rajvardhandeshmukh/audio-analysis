"""Auth routes — register and login.

POST /api/v1/auth/register  (admin only — users are not self-registered)
POST /api/v1/auth/login
POST /api/v1/auth/refresh   (future)
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from src.domain.enums.user_role import UserRole
from src.domain.errors.domain_errors import AuthenticationError
from src.infrastructure.auth.jwt_service import JWTService
from src.infrastructure.auth.password_service import hash_password, verify_password
from src.infrastructure.container import RepositoryContainer
from src.presentation.api.dependencies import (
    get_jwt_service,
    get_repos,
    require_role,
)
from src.presentation.api.response import ApiResponse
from src.domain.entities.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─── Request / Response schemas ───────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole = UserRole.VIEWER


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=ApiResponse[TokenResponse],
    status_code=201,
    summary="Create a new user (admin only)",
)
async def register(
    body: RegisterRequest,
    repos: RepositoryContainer = Depends(get_repos),
    payload: dict = Depends(require_role(UserRole.ADMIN)),  # type: ignore[type-arg]
    jwt_service: JWTService = Depends(get_jwt_service),
) -> ApiResponse[TokenResponse]:
    user = User(
        email=str(body.email),
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    saved = await repos.user.create(user)
    token = jwt_service.create_token(saved.id, saved.role)
    return ApiResponse.ok(TokenResponse(access_token=token, role=saved.role.value))


@router.post(
    "/login",
    response_model=ApiResponse[TokenResponse],
    summary="Obtain JWT access token",
)
async def login(
    body: LoginRequest,
    repos: RepositoryContainer = Depends(get_repos),
    jwt_service: JWTService = Depends(get_jwt_service),
) -> ApiResponse[TokenResponse]:
    user = await repos.user.get_by_email(str(body.email))
    if not user or not verify_password(body.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password.")
    token = jwt_service.create_token(user.id, user.role)
    return ApiResponse.ok(TokenResponse(access_token=token, role=user.role.value))

"""Authentication and Role-Based Access Control (RBAC) for R4 API."""

from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger("api_auth")


class Role(StrEnum):
    """System authorization roles."""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class AuthenticatedUser(BaseModel):
    """Authenticated client identity."""
    api_key_masked: str
    role: Role
    name: str


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)


async def get_current_user(
    api_key: Annotated[str | None, Security(api_key_header)] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_auth)] = None,
) -> AuthenticatedUser:
    """Extract and validate credentials from X-API-Key header or Bearer token."""
    if not settings.auth_enabled:
        return AuthenticatedUser(
            api_key_masked="***DEV***",
            role=Role.ADMIN,
            name="Development Default User",
        )

    token = None
    if api_key:
        token = api_key.strip()
    elif bearer and bearer.credentials:
        token = bearer.credentials.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API authentication credentials. Provide 'X-API-Key' header or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Match token to configured roles using constant-time comparison (FL-04 & FL-12)
    import secrets

    if secrets.compare_digest(token, settings.api_key_admin):
        logger.info(f"Authenticated user as ADMIN via API key prefix: {token[:4]}...")
        return AuthenticatedUser(
            api_key_masked=f"{token[:4]}...{token[-4:]}" if len(token) >= 8 else "***",
            role=Role.ADMIN,
            name="System Administrator",
        )
    elif secrets.compare_digest(token, settings.api_key_operator):
        logger.info(f"Authenticated user as OPERATOR via API key prefix: {token[:4]}...")
        return AuthenticatedUser(
            api_key_masked=f"{token[:4]}...{token[-4:]}" if len(token) >= 8 else "***",
            role=Role.OPERATOR,
            name="Forecasting Operator",
        )
    elif secrets.compare_digest(token, settings.api_key_viewer):
        logger.info(f"Authenticated user as VIEWER via API key prefix: {token[:4]}...")
        return AuthenticatedUser(
            api_key_masked=f"{token[:4]}...{token[-4:]}" if len(token) >= 8 else "***",
            role=Role.VIEWER,
            name="Read-Only Analyst",
        )

    logger.warning("Authentication failure: Invalid API token presented.")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API authentication token.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def require_role(allowed_roles: list[Role]):
    """Dependency factory checking that the authenticated user possesses an allowed role."""
    async def role_checker(user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> AuthenticatedUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: User role '{user.role.value}' does not have sufficient permissions. Allowed: {[r.value for r in allowed_roles]}",
            )
        return user

    return role_checker


# Role dependencies
require_admin = require_role([Role.ADMIN])
require_operator = require_role([Role.ADMIN, Role.OPERATOR])
require_viewer = require_role([Role.ADMIN, Role.OPERATOR, Role.VIEWER])

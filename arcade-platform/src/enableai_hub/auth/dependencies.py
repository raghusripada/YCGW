# src/enableai_hub/auth/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
import uuid # For UUID type hint if user_id is UUID

from enableai_hub.core.database import get_db_session
from enableai_hub.auth.token_manager import decode_platform_access_token
from enableai_hub.auth.user_manager import get_user # Assuming get_user fetches by ID
from enableai_hub.auth.models import User # SQLAlchemy User model

oauth2_scheme_platform_user = OAuth2PasswordBearer(tokenUrl="/oauth/login/platform-token")

async def get_current_active_platform_user(
    token: str = Depends(oauth2_scheme_platform_user),
    db: AsyncSession = Depends(get_db_session)
) -> User:
    """
    FastAPI dependency to get the current authenticated and active platform user from a JWT.
    Raises HTTPException 401 if authentication fails or user is inactive.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id_from_token = decode_platform_access_token(token)
    if user_id_from_token is None:
        raise credentials_exception

    user = await get_user(db_session=db, user_id=user_id_from_token)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    return user

from fastapi.security.api_key import APIKeyHeader
from fastapi import Security
from enableai_hub.auth.apikey_manager import verify_api_key

api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_user_from_api_key(
    api_key_value: Optional[str] = Security(api_key_header_scheme),
    db: AsyncSession = Depends(get_db_session)
) -> Optional[User]:
    """
    FastAPI dependency to get a user from an API key.
    Returns User if valid and active key, else None.
    """
    if not api_key_value:
        return None

    user = await verify_api_key(db_session=db, provided_key_value=api_key_value)
    if user:
        return user
    return None

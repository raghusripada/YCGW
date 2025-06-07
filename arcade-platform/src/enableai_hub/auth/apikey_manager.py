# src/enableai_hub/auth/apikey_manager.py
import secrets
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone # Added timezone
import uuid

from enableai_hub.auth.models import APIKey, User
# Assuming get_password_hash and verify_password from user_manager can be used for API keys as well.
from enableai_hub.auth.user_manager import get_password_hash, verify_password

API_KEY_LENGTH = 32

async def create_api_key(
    db_session: AsyncSession, user: User, name: Optional[str] = None
) -> Tuple[str, APIKey]:
    """
    Generates a new API key for a user.
    The plaintext key is shown ONCE. Its hash is stored.
    """
    plaintext_key = f"eai_{secrets.token_urlsafe(API_KEY_LENGTH)}"

    hashed_key_value = get_password_hash(plaintext_key)

    db_apikey = APIKey(
        hashed_key=hashed_key_value,
        user_id=user.id,
        name=name,
        is_active=True
    )
    db_session.add(db_apikey)
    await db_session.flush()
    await db_session.refresh(db_apikey)
    return plaintext_key, db_apikey

async def verify_api_key(db_session: AsyncSession, provided_key_value: str) -> Optional[User]:
    """
    Verifies an API key. If valid and active, returns the associated User.
    Otherwise, returns None.
    This version iterates through active keys and uses passlib.verify.
    NOTE: This is INEFFICIENT for a large number of keys.
    A production system should use a prefixed key and lookup by prefix,
    then verify the secret part, or use a direct hash lookup if the DB supports it well.
    """
    stmt = select(APIKey).where(APIKey.is_active == True)
    result = await db_session.execute(stmt)
    active_keys = result.scalars().all()

    for db_key in active_keys:
        if verify_password(provided_key_value, db_key.hashed_key): # Re-using verify_password
            if db_key.expires_at and db_key.expires_at.replace(tzinfo=None) < datetime.utcnow():
                continue # Key expired

            db_key.last_used_at = datetime.now(timezone.utc)
            db_session.add(db_key)
            # No await db_session.flush() here to avoid IO if not strictly necessary before returning user

            user_stmt = select(User).where(User.id == db_key.user_id, User.is_active == True)
            user_result = await db_session.execute(user_stmt)
            user = user_result.scalars().first()
            return user

    return None

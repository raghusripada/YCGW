# src/enableai_hub/auth/token_manager.py
from datetime import datetime, timedelta, timezone # Added timezone
from typing import Optional, Dict, Any
import uuid

from jose import JWTError, jwt
from pydantic import BaseModel

from enableai_hub.core.config import AppSettings
from enableai_hub.auth.models import User # SQLAlchemy User model

settings = AppSettings() # Load settings to get secret key, algorithm, expiry

class TokenData(BaseModel):
    # Pydantic model for data contained within the token (e.g., subject)
    sub: Optional[str] = None # Subject (user identifier, e.g., email or user_id as string)

def create_platform_access_token(
    user: User, expires_delta_minutes: Optional[int] = None
) -> str:
    """
    Generates a JWT access token for a platform user.
    """
    if expires_delta_minutes is not None:
        expires_on = datetime.now(timezone.utc) + timedelta(minutes=expires_delta_minutes)
    else:
        expires_on = datetime.now(timezone.utc) + timedelta(minutes=settings.auth.access_token_expire_minutes)

    to_encode: Dict[str, Any] = {
        "exp": expires_on,
        "sub": str(user.id), # Use user's UUID ID as the subject, converted to string
        # Add other claims if needed, e.g., "email": user.email, "type": "access"
        "token_type": "platform_user_access_token" # Custom claim for token type
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.auth.jwt_secret_key.get_secret_value(),
        algorithm=settings.auth.jwt_algorithm
    )
    return encoded_jwt

def decode_platform_access_token(token: str) -> Optional[uuid.UUID]:
    """
    Decodes a platform JWT access token.
    Returns the user_id (as UUID) if valid, else None.
    """
    try:
        payload = jwt.decode(
            token,
            settings.auth.jwt_secret_key.get_secret_value(),
            algorithms=[settings.auth.jwt_algorithm],
            options={"verify_aud": False} # No audience check for this simple token yet
        )
        # Check for custom token type if implemented during encoding
        if payload.get("token_type") != "platform_user_access_token":
            print("Token type mismatch.")
            return None

        subject = payload.get("sub")
        if subject is None:
            print("Subject (user ID) not found in token.")
            return None
        return uuid.UUID(subject) # Convert stringified UUID back to UUID object
    except JWTError as e:
        print(f"JWT Error: {e}")
        return None
    except ValueError: # For UUID conversion error
        print("Invalid UUID format in token subject.")
        return None

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, Dict, List, Any
import uuid # For user_id type
import time # For expires_at timestamp handling
import httpx # For making HTTP calls
import json # For parsing JSON error responses

from arcade_platform.core.config import AppSettings
from arcade_platform.auth.models import UserExternalToken # SQLAlchemy model

# Initialize Fernet with the key from settings
try:
    settings = AppSettings()
    # Ensure the key is bytes for Fernet
    fernet_key_bytes = settings.external_token_fernet_key.get_secret_value().encode('utf-8')
    if len(fernet_key_bytes) * 3 // 4 - fernet_key_bytes.count(b'=') != 32: # Basic base64 length check for 32 bytes key
         print(f"Warning: Fernet key from settings might not be a valid 32-byte base64 encoded key. Length: {len(fernet_key_bytes)}")
    fernet_cipher = Fernet(fernet_key_bytes)
except Exception as e:
    print(f"CRITICAL ERROR: Could not initialize Fernet for token encryption: {e}")
    raise RuntimeError(f"Failed to initialize Fernet cipher: {e}. Check EXTERNAL_TOKEN_FERNET_KEY in your environment.")


def encrypt_token(token: str) -> str:
    """Encrypts a token string using Fernet."""
    if not token:
        return fernet_cipher.encrypt("".encode('utf-8')).decode('utf-8')
    return fernet_cipher.encrypt(token.encode('utf-8')).decode('utf-8')

def decrypt_token(encrypted_token: str) -> Optional[str]:
    """Decrypts a token string using Fernet. Returns None if decryption fails."""
    if not encrypted_token:
        return None
    try:
        return fernet_cipher.decrypt(encrypted_token.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        print("Error: Failed to decrypt token. It might be invalid, corrupted, or using a different key.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during token decryption: {e}")
        return None

async def store_external_token(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    provider_name: str,
    access_token: str,
    expires_in: Optional[int],
    scopes: Optional[List[str]],
    refresh_token: Optional[str] = None,
) -> UserExternalToken:
    """
    Saves or updates an encrypted external OAuth token for a user and provider.
    'expires_in' is the lifetime of the access token in seconds from now.
    """
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token is not None else None # Encrypt if provided, else None

    current_time = int(time.time())
    calculated_expires_at = (current_time + expires_in) if expires_in is not None else None

    stmt = select(UserExternalToken).where(
        UserExternalToken.user_id == user_id,
        UserExternalToken.provider_name == provider_name
    )
    result = await db_session.execute(stmt)
    existing_token_record = result.scalars().first()

    if existing_token_record:
        existing_token_record.encrypted_access_token = encrypted_access
        if refresh_token is not None: # A new refresh token value was explicitly passed (could be empty string or new token)
            existing_token_record.encrypted_refresh_token = encrypted_refresh
        # If refresh_token is None (not passed), the existing one is preserved.

        existing_token_record.expires_at = calculated_expires_at
        existing_token_record.scopes = scopes if scopes is not None else existing_token_record.scopes
        token_record = existing_token_record
    else:
        token_record = UserExternalToken(
            user_id=user_id,
            provider_name=provider_name,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh, # This will be None if refresh_token was None
            expires_at=calculated_expires_at,
            scopes=scopes if scopes is not None else []
        )
        db_session.add(token_record)

    await db_session.flush()
    await db_session.refresh(token_record)
    return token_record

async def get_active_external_token(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    provider_name: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieves an active (not expired) and decrypted external access token.
    Returns a dict with token details or None if not found/expired and unrefreshable.
    """
    stmt = select(UserExternalToken).where(
        UserExternalToken.user_id == user_id,
        UserExternalToken.provider_name == provider_name
    )
    result = await db_session.execute(stmt)
    token_record = result.scalars().first()

    if not token_record:
        return None

    if token_record.expires_at is not None and token_record.expires_at < (int(time.time()) + 60):
        print(f"Token for {provider_name} for user {user_id} has expired or is about to expire.")
        refreshed_token_info = await refresh_external_token_if_needed(db_session, token_record)
        return refreshed_token_info

    decrypted_access_token = decrypt_token(token_record.encrypted_access_token)
    if not decrypted_access_token:
        return None

    return {
        "access_token": decrypted_access_token,
        "provider_name": token_record.provider_name,
        "scopes": token_record.scopes,
        "expires_at": token_record.expires_at,
    }

async def refresh_external_token_if_needed(
    db_session: AsyncSession,
    token_record: UserExternalToken
) -> Optional[Dict[str, Any]]:
    """
    Attempts to refresh an expired or soon-to-expire external token using its refresh token.
    If successful, it updates the stored tokens and returns the new active token info.
    Returns None if refresh fails or is not possible.
    """
    print(f"[TokenManager] Attempting to refresh token for provider '{token_record.provider_name}' for user '{token_record.user_id}'.")

    decrypted_refresh_token = None
    if token_record.encrypted_refresh_token:
        decrypted_refresh_token = decrypt_token(token_record.encrypted_refresh_token)

    if not decrypted_refresh_token:
        print(f"[TokenManager] No refresh token available or decryption failed for {token_record.provider_name}, user {token_record.user_id}. Cannot refresh.")
        return None

    current_settings = AppSettings()
    provider_config = current_settings.auth.providers.get(token_record.provider_name)

    if not provider_config or not provider_config.token_url or not provider_config.client_id or not provider_config.client_secret:
        print(f"[TokenManager] Missing OAuth provider configuration for '{token_record.provider_name}' to refresh token.")
        return None

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": decrypted_refresh_token,
        "client_id": provider_config.client_id,
        "client_secret": provider_config.client_secret.get_secret_value(),
    }

    try:
        async with httpx.AsyncClient() as client:
            print(f"[TokenManager] Requesting new token from {provider_config.token_url} for {token_record.provider_name}")
            response = await client.post(str(provider_config.token_url), data=payload)
            response.raise_for_status()
            new_token_data = response.json()
            print(f"[TokenManager] Token refresh successful for {token_record.provider_name}. New token data received.")

        if "access_token" not in new_token_data:
            print(f"[TokenManager] 'access_token' not found in refresh response for {token_record.provider_name}.")
            return None

        new_access_token = new_token_data["access_token"]
        new_expires_in = new_token_data.get("expires_in")
        new_refresh_token = new_token_data.get("refresh_token")

        new_scopes_str = new_token_data.get("scope")
        final_scopes = token_record.scopes
        if new_scopes_str:
            final_scopes = new_scopes_str.split(" ")
        elif isinstance(new_scopes_str, list):
            final_scopes = new_scopes_str

        updated_token_record = await store_external_token(
            db_session=db_session,
            user_id=token_record.user_id,
            provider_name=token_record.provider_name,
            access_token=new_access_token,
            expires_in=new_expires_in,
            scopes=final_scopes,
            refresh_token=new_refresh_token
        )

        decrypted_new_access_token = decrypt_token(updated_token_record.encrypted_access_token)
        if not decrypted_new_access_token:
            print(f"[TokenManager] CRITICAL: Failed to decrypt newly stored access token for {token_record.provider_name}.")
            return None

        return {
            "access_token": decrypted_new_access_token,
            "provider_name": updated_token_record.provider_name,
            "scopes": updated_token_record.scopes,
            "expires_at": updated_token_record.expires_at,
        }

    except httpx.HTTPStatusError as e:
        print(f"[TokenManager] HTTP error while refreshing token for {token_record.provider_name}: {e.response.status_code} - {e.response.text}")
        if e.response.status_code in [400, 401]:
            try:
                error_details = e.response.json()
                if error_details.get("error") == "invalid_grant":
                    print(f"[TokenManager] Refresh token for {token_record.provider_name} is invalid or revoked. Clearing stored refresh token.")
                    token_record.encrypted_refresh_token = None
                    db_session.add(token_record)
                    # await db_session.commit() # Handled by session dependency
            except json.JSONDecodeError:
                pass
        return None
    except Exception as e:
        print(f"[TokenManager] Unexpected error during token refresh for {token_record.provider_name}: {e}")
        import traceback; traceback.print_exc();
        return None

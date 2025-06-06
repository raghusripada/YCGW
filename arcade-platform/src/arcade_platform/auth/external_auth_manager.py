from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, Dict, List, Any
import uuid # For user_id type
import time # For expires_at timestamp handling

from arcade_platform.core.config import AppSettings
from arcade_platform.auth.models import UserExternalToken # SQLAlchemy model

# Initialize Fernet with the key from settings
try:
    settings = AppSettings()
    # Ensure the key is bytes for Fernet
    fernet_key_bytes = settings.external_token_fernet_key.get_secret_value().encode('utf-8')
    if len(fernet_key_bytes) * 3 // 4 - fernet_key_bytes.count(b'=') != 32: # Basic base64 length check for 32 bytes key
         # This check might not be perfect for all base64 strings but is a sanity check.
         # Fernet itself will validate the key format.
         print(f"Warning: Fernet key from settings might not be a valid 32-byte base64 encoded key. Length: {len(fernet_key_bytes)}")
    fernet_cipher = Fernet(fernet_key_bytes)
except Exception as e:
    print(f"CRITICAL ERROR: Could not initialize Fernet for token encryption: {e}")
    # This is a critical failure. Depending on app design, might want to prevent startup.
    raise RuntimeError(f"Failed to initialize Fernet cipher: {e}. Check EXTERNAL_TOKEN_FERNET_KEY in your environment.")


def encrypt_token(token: str) -> str:
    """Encrypts a token string using Fernet."""
    if not token: # Avoid encrypting empty or None strings if they are not valid tokens
        # Fernet would encrypt an empty string, but it might indicate an issue upstream.
        # Depending on requirements, either raise an error or return a specific marker/None.
        # For now, let's treat an empty string as something that can be encrypted.
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
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

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
        # Only update refresh token if a new one is provided.
        # If refresh_token is None in input, keep the old one unless explicitly clearing.
        if refresh_token is not None: # A new refresh token (even if empty string) was provided
            existing_token_record.encrypted_refresh_token = encrypted_refresh
        # If refresh_token is not provided (is None), the existing one is preserved.

        existing_token_record.expires_at = calculated_expires_at
        existing_token_record.scopes = scopes if scopes is not None else existing_token_record.scopes
        token_record = existing_token_record
    else:
        token_record = UserExternalToken(
            user_id=user_id,
            provider_name=provider_name,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            expires_at=calculated_expires_at,
            scopes=scopes if scopes is not None else []
        )
        db_session.add(token_record)

    await db_session.flush() # Ensure IDs or defaults are populated before refresh
    await db_session.refresh(token_record) # Refresh to get all fields from DB
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

    # Check if token is expired or about to expire (e.g., within next 60 seconds)
    if token_record.expires_at is not None and token_record.expires_at < (int(time.time()) + 60):
        print(f"Token for {provider_name} for user {user_id} has expired or is about to expire.")
        # Attempt to refresh the token
        refreshed_token_info = await refresh_external_token_if_needed(db_session, token_record)
        # If refresh_external_token_if_needed returns the new token info (already decrypted and structured)
        return refreshed_token_info

    decrypted_access_token = decrypt_token(token_record.encrypted_access_token)
    if not decrypted_access_token: # Decryption failed
        return None

    return {
        "access_token": decrypted_access_token,
        "provider_name": token_record.provider_name,
        "scopes": token_record.scopes,
        "expires_at": token_record.expires_at,
        # Optionally, include decrypted refresh token if needed by caller, but be cautious
        # "refresh_token": decrypt_token(token_record.encrypted_refresh_token) if token_record.encrypted_refresh_token else None,
    }

async def refresh_external_token_if_needed(
    db_session: AsyncSession,
    token_record: UserExternalToken
) -> Optional[Dict[str, Any]]:
    """
    STUB: Attempts to refresh an external token using its refresh token.
    If successful, it updates the stored tokens and returns the new active token info.
    """
    print(f"[STUB] Attempting to refresh token for provider '{token_record.provider_name}' for user '{token_record.user_id}'.")

    decrypted_refresh_token = None
    if token_record.encrypted_refresh_token:
        decrypted_refresh_token = decrypt_token(token_record.encrypted_refresh_token)

    if not decrypted_refresh_token:
        print(f"No refresh token available or decryption failed for {token_record.provider_name}, user {token_record.user_id}. Cannot refresh.")
        return None

    # --- TODO: Implement actual refresh logic using httpx ---
    # This section remains a placeholder for actual HTTP calls to the provider.
    # Example structure:
    # global_settings = AppSettings() # Access global settings instance
    # provider_configs = global_settings.auth.providers
    # provider_config = provider_configs.get(token_record.provider_name)
    # if not provider_config or not provider_config.token_url or not provider_config.client_id or not provider_config.client_secret:
    #     print(f"Missing provider config for {token_record.provider_name} to refresh token.")
    #     return None
    #
    # import httpx # Make sure httpx is imported
    # data = {
    #     "grant_type": "refresh_token",
    #     "refresh_token": decrypted_refresh_token,
    #     "client_id": provider_config.client_id,
    #     "client_secret": provider_config.client_secret.get_secret_value(),
    #     # "scope": " ".join(token_record.scopes) # Optional: some providers might want scopes
    # }
    # try:
    #     async with httpx.AsyncClient() as client:
    #         response = await client.post(str(provider_config.token_url), data=data)
    #     response.raise_for_status() # Raise HTTPStatusError for bad responses (4xx or 5xx)
    #     new_token_data = response.json()
    #
    #     # Store the new token(s) - note that some providers might not return a new refresh token
    #     updated_token_record = await store_external_token(
    #         db_session, token_record.user_id, token_record.provider_name,
    #         new_token_data["access_token"],
    #         new_token_data.get("expires_in"),
    #         new_token_data.get("scope", "").split(" ") if new_token_data.get("scope") else token_record.scopes,
    #         new_token_data.get("refresh_token") # This might be None, store_external_token handles it
    #     )
    #     # Return the new active token info, similar to get_active_external_token structure
    #     return {
    #         "access_token": decrypt_token(updated_token_record.encrypted_access_token),
    #         "provider_name": updated_token_record.provider_name,
    #         "scopes": updated_token_record.scopes,
    #         "expires_at": updated_token_record.expires_at,
    #     }
    # except httpx.HTTPStatusError as e:
    #     print(f"HTTP error while refreshing token for {token_record.provider_name}: {e.response.status_code} - {e.response.text}")
    #     # Optionally, if refresh token is rejected (e.g. invalid_grant), mark it as unusable
    #     # or delete the token_record from DB to force re-authentication.
    #     return None
    # except Exception as e:
    #     print(f"Unexpected error during token refresh for {token_record.provider_name}: {e}")
    #     return None

    print("[STUB] Token refresh logic not yet fully implemented. Returning None.")
    return None
